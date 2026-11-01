"""Импорт курсантов из XLSX (BACKLOG F-5).

Массовое заведение контингента: файл Excel → валидация построчно →
предпросмотр (список ``ImportRow`` с ошибками) → пакетная вставка одной
транзакцией (``database.transaction()``, A-3): либо импортируются все
корректные строки, либо ни одной.

Формат листа: первая строка — заголовки колонок. Обязательные колонки:
«Фамилия», «Имя». Необязательные: «Отчество», «Курс», «Группа», «Пол»,
«Дата рождения» (dd.mm.yyyy или yyyy-mm-dd). Лишние колонки игнорируются,
пустые строки пропускаются.

Шаблон для заполнения можно выгрузить функцией ``create_template_xlsx``.

Вставка выполняется прямым INSERT в транзакционном соединении (не через
add_student: тот открывает собственное соединение и не участвует в общей
транзакции). Права проверяются на уровне вызывающего слоя (B-1), как и
для остальных мутаторов — параметр ``actor_role`` обязателен.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from access import require_role

# Заголовок колонки → имя поля students. Порядок = порядок в шаблоне.
COLUMN_MAP = {
    "Фамилия": "o_surname",
    "Имя": "o_name",
    "Отчество": "o_lastname",
    "Курс": "o_course",
    "Группа": "o_group_name",
    "Пол": "o_gender",
    "Дата рождения": "o_date_of_birth",
}
REQUIRED_FIELDS = ("o_surname", "o_name")

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$|^(\d{2})\.(\d{2})\.(\d{4})$")


@dataclass
class ImportRow:
    """Одна строка предпросмотра импорта: данные + список ошибок."""

    line_no: int                      # номер строки в файле (1-based, с заголовком)
    data: dict = field(default_factory=dict)   # поле students -> значение
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def normalize_date(value) -> str | None:
    """Приводит дату из ячейки к 'YYYY-MM-DD'; None, если распознать нельзя."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    m = _DATE_RE.match(s)
    if m:
        if m.group(1):  # yyyy-mm-dd
            y, mo, d = m.group(1), m.group(2), m.group(3)
        else:           # dd.mm.yyyy
            d, mo, y = m.group(4), m.group(5), m.group(6)
        try:
            datetime(int(y), int(mo), int(d))
            return f"{y}-{mo}-{d}"
        except ValueError:
            return None
    return None


def validate_row(line_no: int, raw: dict) -> ImportRow:
    """Проверяет одну строку файла; возвращает ImportRow с ошибками/данными."""
    row = ImportRow(line_no=line_no)
    for header, fld in COLUMN_MAP.items():
        val = raw.get(header)
        if val is None:
            continue
        if isinstance(val, str):
            val = val.strip()
        if val == "" or val is None:
            continue
        row.data[fld] = val

    for fld in REQUIRED_FIELDS:
        if not str(row.data.get(fld, "")).strip():
            label = next(h for h, f_ in COLUMN_MAP.items() if f_ == fld)
            row.errors.append(f"Не заполнено обязательное поле «{label}»")

    course = row.data.get("o_course")
    if course is not None:
        try:
            c = int(float(course))
            if not 1 <= c <= 6:
                raise ValueError
            row.data["o_course"] = c
        except (TypeError, ValueError):
            row.errors.append(f"Некорректный курс: {course!r} (ожидается 1..6)")

    dob = row.data.get("o_date_of_birth")
    if dob is not None:
        norm = normalize_date(dob)
        if norm is None:
            row.errors.append(f"Некорректная дата рождения: {dob!r}")
        else:
            row.data["o_date_of_birth"] = norm
    return row


def parse_workbook(filepath: str) -> list[ImportRow]:
    """Читает первый лист XLSX и возвращает список валидированных строк.

    Бросает ValueError, если заголовки не распознаны (нет колонки «Фамилия»).
    """
    import openpyxl

    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration:
            raise ValueError("Файл пуст: нет строки заголовков") from None
        headers = [str(h).strip() if h is not None else "" for h in header]
        if "Фамилия" not in headers:
            raise ValueError(
                "Не распознаны заголовки: обязательна колонка «Фамилия» "
                f"(в файле: {headers!r}). Используйте шаблон create_template_xlsx()."
            )
        result = []
        for idx, values in enumerate(rows_iter, start=2):
            raw = {}
            for col_name, value in zip(headers, values):
                if col_name in COLUMN_MAP:
                    raw[col_name] = value
            if all(v is None or str(v).strip() == "" for v in values):
                continue  # полностью пустая строка — пропускаем без ошибки
            result.append(validate_row(idx, raw))
        return result
    finally:
        wb.close()


_INSERT_SQL = (
    "INSERT INTO students (o_surname, o_name, o_lastname, o_course, "
    "o_group_name, o_gender, o_date_of_birth) VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_ORDER = ("o_surname", "o_name", "o_lastname", "o_course",
                 "o_group_name", "o_gender", "o_date_of_birth")


def commit_import(rows: list[ImportRow], actor_role=None, log_user: str = "system") -> int:
    """Пакетная вставка корректных строк одной транзакцией (A-3).

    Вставляются только строки без ошибок; при любой ошибке СУБД откатывается
    ВЕСЬ пакет. Возвращает число вставленных записей. Если нет ни одной
    валидной строки — 0 (транзакция не открывается).
    """
    require_role(actor_role, action="import_students_xlsx")
    valid = [r for r in rows if r.ok and r.data]
    if not valid:
        return 0
    from cache import invalidate
    from database import log_action, transaction

    with transaction() as conn:
        for r in valid:
            params = tuple(r.data.get(f) for f in _INSERT_ORDER)
            conn.execute(_INSERT_SQL, params)
        log_action(log_user, f"Импорт XLSX: добавлено {len(valid)} курсантов")
    invalidate("students")  # C-4: справочник групп изменился
    return len(valid)


def create_template_xlsx(filepath: str) -> str:
    """Создаёт пустой шаблон импорта (заголовки + пример). Возвращает путь."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Контингент"
    ws.append(list(COLUMN_MAP.keys()))
    ws.append(["Иванов", "Иван", "Иванович", 1, "А-11", "М", "2005-01-15"])
    wb.save(filepath)
    return filepath
