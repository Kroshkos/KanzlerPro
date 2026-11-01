"""Экспорт в DOCX: личное дело, ведомость баллов и приказы (BACKLOG F-1/F-2).

Модуль генерирует документы формата Word (OOXML) через python-docx:

* ``generate_personal_file_docx`` — личное дело курсанта (аналог
  personal_file_pdf.py, но редактируемый документ для ведомства);
* ``generate_roster_docx``      — ведомость/список личного состава;
* ``render_order_template``     — чистый шаблон приказа (автоподстановка
  данных курсанта в текст с плейсхолдерами ``{field}`` — BACKLOG F-2);
* ``generate_order_docx``       — приказ о поощрении/взыскании.

Документооборот military-стиля: поля плейсхолдеров берутся из записи
``students`` (ФИО в родительном падеже собирается из o_surname/o_name/
o_lastname), звание/должность — из колонок личного дела.

Функции, обращающиеся к БД, импортируют ``database`` лениво — как в
report_generator.py: это позволяет тестировать чистые функции шаблонов
без инициализации базы.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime

from config import REPORTS_DIR

# --- Шаблоны приказов (F-2) ------------------------------------------------
# Плейсхолдеры заполняются из dict курсанта функцией render_order_template.
ORDER_TEMPLATE_ENCOURAGEMENT = (
    "За добросовестное исполнение служебных обязанностей, высокие показатели "
    "в боевой подготовке и проявленную инициативу "
    "{rank} {group} {surname} {name} {lastname} ПОООЩИРИТЬ.\n"
    "{encouragement_type}: {reason}."
)

ORDER_TEMPLATE_PENALTY = (
    "За нарушение служебной дисциплины, выразившееся в следующем: {reason}, "
    "{rank} {group} {surname} {name} {lastname} ОБЪЯВИТЬ {penalty_type}."
)

_SURNAME_TO_GENITIVE = [
    # Правила родительного падежа по окончанию. Порядок важен: более
    # длинные суффиксы проверяются раньше коротких.
    # Женские формы на -а/-я: Иванова -> Ивановой, Петровна -> Петровны.
    ("ова", "овой"), ("ева", "евой"), ("ская", "ской"),
    ("а", "ы"), ("я", "и"),
    # Мужские фамилии на согласный: Иванов -> Иванова, Петров -> Петрова.
    ("ов", "ова"), ("ев", "ева"), ("ёв", "ёва"),
    ("ин", "ина"), ("ын", "ына"),
    ("ский", "ского"), ("цкой", "цкого"), ("ской", "ского"),
    ("ий", "ого"), ("ый", "ого"), ("ой", "ого"),
]

# Минимальная длина слова для «дополнительных» правил склонения имён и
# отчеств («Иван», «Петрович»). Короткие заимствованные фамилии вида
# «Смит» (4 буквы) русскими окончаниями не распознаются и остаются
# несклоняемыми.
_MIN_DECLINABLE_LEN = 5

def _is_female_stem(s: str) -> bool:
    """Эвристика: мужские слова на -ов/-ев/-ин — явные мужские формы.

    Остальные слова на -а/-я в контексте ФИО курсантов склоняются по
    женскому типу (Иванова -> Ивановой).
    """
    lowered = s.lower()
    if lowered.endswith(("ов", "ев", "ёв", "ин", "ын")):
        return False
    return lowered.endswith(("а", "я"))


def surname_to_genitive(word: str) -> str:
    """Родительный падеж ФИО-слова по окончанию (эвристика для типичных случаев).

    Мужские фамилии на согласный склоняются («Иванов» → «Иванова»), женские
    на -а/-я — по женскому типу («Иванова» → «Ивановой»). Заимствованные
    короткие фамилии вида «Смит» и слова на шипящий остаются как есть.
    """
    s = (word or "").strip()
    if not s:
        return ""
    lowered = s.lower()
    female = _is_female_stem(s)
    for suffix, repl in _SURNAME_TO_GENITIVE:
        if lowered.endswith(suffix):
            # Для слов на -а/-я берём только женские правила (мужские
            # окончания вида -ов/-ин в конце женской фамилии — часть корня:
            # «Иванова» склоняется как «Ивановой», а не «Ивановаина»).
            if female and suffix in ("ов", "ев", "ёв", "ин", "ын", "ский",
                                     "цкой", "ской", "ий", "ый", "ой"):
                continue
            return s[: len(s) - len(suffix)] + repl
    # Имена и отчества вне таблиц фамилий («Иван», «Петрович»): мужские
    # слова на согласный (кроме шипящих ж/ш/ч/щ) получают окончание -а.
    if not female and lowered[-1] in "бвгдзклмнпрстфх":
        return s + "а"
    # Отчества на -ич («Петрович») тоже склоняются, хотя оканчиваются на ч.
    if not female and lowered.endswith("ич"):
        return s + "а"
    return s


def _slug(name: str) -> str:
    """Имя файла из названия документа: кириллица/пробелы → безопасная строка."""
    slug = re.sub(r"[^A-Za-zА-Яа-я0-9]+", "_", name).strip("_")
    return slug or "document"


def ensure_output_dir() -> str:
    d = os.path.join(REPORTS_DIR, "docx")
    os.makedirs(d, exist_ok=True)
    return d


def _fmt_date(value) -> str:
    """Дата в человекочитаемом виде; пустое/некорректное → «—»."""
    if value is None or value == "":
        return "—"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d.%m.%Y")
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%Y %H:%M:%S"):
        try:
            return datetime.strptime(s[: len(fmt) + 4], fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return s


# --- Чистый шаблонизатор приказов (F-2) ------------------------------------
def render_order_template(template: str, data: dict) -> str:
    """Подставляет поля курсанта в шаблон приказа.

    Поддерживает плейсхолдеры ``{key}``; отсутствующие ключи заменяются на
    «—», а не падают KeyError (документ должен генерироваться по неполным
    личным делам). Ключ ``fio_in_genitive`` — ФИО в родительном падеже
    («Иванова Ивана Ивановича»), вычисляется автоматически.
    """
    ctx = {k: ("" if v is None else str(v)) for k, v in data.items()}
    # Короткие имена плейсхолдеров — алиасы колонок students (o_surname и
    # т.п.), чтобы шаблоны приказов работали с сырой строкой курсанта.
    for alias, column in (("surname", "o_surname"), ("name", "o_name"),
                          ("lastname", "o_lastname"), ("group", "o_group_name"),
                          ("course", "o_course")):
        if not ctx.get(alias) and ctx.get(column):
            ctx[alias] = ctx[column]
    ctx.setdefault("fio_in_genitive", fio_genitive(ctx))

    def _sub(m: re.Match) -> str:
        val = ctx.get(m.group(1), "").strip()
        return val if val else "—"

    return re.sub(r"\{([a-z_0-9]+)\}", _sub, template)


def fio_genitive(data: dict) -> str:
    """«Фамилия Имя Отчество» в родительном падеже для текста приказа."""
    parts = [
        surname_to_genitive(data.get("o_surname", "")),
        surname_to_genitive(data.get("o_name", "")),
        surname_to_genitive(data.get("o_lastname", "")),
    ]
    return " ".join(p for p in parts if p)


# --- Помощники БД (ленивые импорты, как в report_generator) -----------------
def _student_row(student_id: int) -> dict:
    from database import execute_query

    rows = execute_query("SELECT * FROM students WHERE id = ?", (student_id,), fetch=True)
    if not rows:
        raise ValueError(f"Курсант id={student_id} не найден")
    return dict(rows[0])


def _new_document():
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError as e:  # pragma: no cover - зависимость в requirements.txt
        raise RuntimeError("Для экспорта DOCX установите python-docx") from e
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    return doc


def _save(doc, name: str) -> str:
    path = os.path.join(ensure_output_dir(), f"{_slug(name)}.docx")
    doc.save(path)
    return path


# --- Личное дело (F-1) ------------------------------------------------------
# Секции карточки: (заголовок раздела, [(подпись, колонка students), ...])
_PERSONAL_SECTIONS = [
    ("Общие сведения", [
        ("Фамилия", "o_surname"), ("Имя", "o_name"), ("Отчество", "o_lastname"),
        ("Курс", "o_course"), ("Группа", "o_group_name"),
        ("Дата рождения", "o_date_of_birth"), ("Место рождения", "o_place_of_birth"),
        ("Гражданство", "o_citizenship"), ("Национальность", "o_nationality"),
        ("Семейное положение", "o_marital_status"),
        ("Адрес проживания", "kontact_residential_address"),
        ("Телефон", "kontact_number"), ("E-mail", "kontact_email"),
    ]),
    ("Военный билет", [
        ("Личный номер", "ld_vb_personal_number"),
        ("Звание", "ld_vb_rank_rank"),
        ("Должность", "ld_vb_post_assigned"),
        ("Дата контракта", "ld_vb_contract_date"),
        ("Срок контракта", "ld_vb_contract_term"),
        ("Период службы", "ld_vb_period_of_service"),
    ]),
    ("Образование", [
        ("Уровень", "ld_education_level"),
        ("Заведение", "ld_education_name_given"),
        ("Квалификация", "ld_education_qualification"),
        ("Специальность", "ld_education_specialization"),
    ]),
]


def generate_personal_file_docx(student_id: int) -> str:
    """Личное дело курсанта в DOCX; возвращает путь к файлу в data/reports/docx."""
    s = _student_row(student_id)
    doc = _new_document()
    doc.add_heading(
        f"Личное дело: {s.get('o_surname', '')} {s.get('o_name', '')} {s.get('o_lastname', '')}".strip(),
        level=1,
    )
    for title, fields in _PERSONAL_SECTIONS:
        doc.add_heading(title, level=2)
        table = doc.add_table(rows=0, cols=2)
        table.style = "Light Grid Accent 1"
        for label, col in fields:
            row = table.add_row().cells
            row[0].text = label
            row[1].text = _fmt_date(s.get(col)) if "date" in col else str(s.get(col) or "—")

    from database import get_encouragements_by_student, get_penalties_by_student

    for title, rows in (
        ("Поощрения", get_encouragements_by_student(student_id) or []),
        ("Взыскания", get_penalties_by_student(student_id) or []),
    ):
        doc.add_heading(title, level=2)
        if not rows:
            doc.add_paragraph("Нет записей.")
            continue
        table = doc.add_table(rows=1, cols=3)
        table.style = "Light Grid Accent 1"
        hdr = table.rows[0].cells
        hdr[0].text = "Вид"
        hdr[1].text = "Основание"
        hdr[2].text = "Дата"
        for r in rows:
            cells = table.add_row().cells
            key = "encouragement_type" if title == "Поощрения" else "penalty_type"
            cells[0].text = str(dict(r).get(key, ""))
            cells[1].text = str(dict(r).get("reason", ""))
            cells[2].text = _fmt_date(dict(r).get("date_obj"))

    doc.add_paragraph(f"Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    return _save(doc, f"ЛД_{s.get('o_surname', '')}_{student_id}")


# --- Ведомость личного состава (F-1) ----------------------------------------
def generate_roster_docx(group_name: str | None = None, course: int | None = None) -> str:
    """Ведомость списка курсантов (опционально фильтр группа/курс)."""
    from database import get_students

    rows = get_students(group_name=group_name, course=course) or []
    doc = _new_document()
    subtitle = ", ".join(x for x in (
        f"группа {group_name}" if group_name else "",
        f"курс {course}" if course is not None else "",
    ) if x)
    doc.add_heading("Ведомость личного состава" + (f" ({subtitle})" if subtitle else ""), level=1)
    table = doc.add_table(rows=1, cols=5)
    table.style = "Light Grid Accent 1"
    for i, h in enumerate(("№", "Фамилия", "Имя", "Отчество", "Группа")):
        table.rows[0].cells[i].text = h
    for n, r in enumerate(rows, 1):
        cells = table.add_row().cells
        d = dict(r)
        cells[0].text = str(n)
        cells[1].text = str(d.get("o_surname") or "")
        cells[2].text = str(d.get("o_name") or "")
        cells[3].text = str(d.get("o_lastname") or "")
        cells[4].text = str(d.get("o_group_name") or "")
    doc.add_paragraph(f"Всего: {len(rows)}. Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    return _save(doc, "Ведомость_личного_состава")


# --- Приказ о поощрении/взыскании (F-1 + F-2) --------------------------------
def generate_order_docx(student_id: int, kind: str, reason: str,
                        issued_by: str = "", order_number: str = "",
                        date_obj: str | None = None) -> str:
    """Формирует DOCX-приказ; kind: 'encouragement' | 'penalty'.

    Текст собирается из шаблона F-2 с автоподстановкой данных курсанта,
    запись одновременно фиксируется в БД (add_encouragement/add_penalty) —
    приказ и учёт идут одним шагом, как требует делопроизводство.
    """
    if kind not in ("encouragement", "penalty"):
        raise ValueError(f"Неизвестный вид приказа: {kind!r}")
    s = _student_row(student_id)
    template = ORDER_TEMPLATE_ENCOURAGEMENT if kind == "encouragement" else ORDER_TEMPLATE_PENALTY
    text = render_order_template(template, {
        **s,
        "rank": s.get("ld_vb_rank_rank") or "рядовой",
        "group": f"группы {s.get('o_group_name')}" if s.get("o_group_name") else "",
        "reason": reason,
        "encouragement_type": "награждение",
        "penalty_type": "выговор",
    })

    doc = _new_document()
    doc.add_heading("ПРИКАЗ" + (f" № {order_number}" if order_number else ""), level=1)
    doc.add_paragraph(f"от {_fmt_date(date_obj or datetime.now().strftime('%d.%m.%Y'))}")
    doc.add_paragraph(text)
    if issued_by:
        doc.add_paragraph(f"Инициатор: {issued_by}")
    name = f"Приказ_{'поощрение' if kind == 'encouragement' else 'взыскание'}_{s.get('o_surname', '')}_{student_id}"
    return _save(doc, name)
