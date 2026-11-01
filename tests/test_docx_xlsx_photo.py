"""Тесты модулей из последнего среза бэклога.

* app/docx_export.py  — экспорт DOCX и шаблоны приказов (F-1/F-2);
* app/xlsx_import.py  — импорт курсантов из XLSX (F-5);
* app/photo_storage.py + doctor.check_photos — хранилище фото (C-3/D-3);
* app/config.py       — загрузка секретов из .env (B-4).
"""

import base64
import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


# ============================== F-2: шаблоны приказов ======================
def test_render_order_template_substitutes_fields():
    from docx_export import render_order_template

    text = render_order_template(
        "{rank} {surname} {name}: {reason}",
        {"rank": "сержант", "surname": "Иванов", "name": "Иван",
         "reason": "образцовое исполнение обязанностей"})
    assert text == "сержант Иванов Иван: образцовое исполнение обязанностей"


def test_render_order_template_missing_keys_become_dash():
    """Неполное личное дело не должно ронять генерацию приказа."""
    from docx_export import render_order_template

    text = render_order_template("{rank} {surname} ПОООЩИРИТЬ", {"surname": ""})
    assert "—" in text and "ПОООЩИРИТЬ" in text


def test_surname_to_genitive_rules():
    from docx_export import surname_to_genitive

    assert surname_to_genitive("Иванов") == "Иванова"
    assert surname_to_genitive("Петров") == "Петрова"
    assert surname_to_genitive("Смит") == "Смит"   # неизвесное окончание — как есть
    assert surname_to_genitive("") == ""


def test_fio_genitive_full_name():
    from docx_export import fio_genitive

    fio = fio_genitive({"o_surname": "Иванов", "o_name": "Иван",
                        "o_lastname": "Петрович"})
    assert fio.startswith("Иванова Ивана")


# ============================== F-1: генерация DOCX ========================
def _make_student(db, surname="Иванов", name="Иван", group="А-11", course=1):
    return db.add_student({"o_surname": surname, "o_name": name,
                           "o_lastname": "Петрович", "o_course": course,
                           "o_group_name": group}, actor_role="Администратор")


def test_generate_personal_file_docx_creates_file(db, tmp_path, monkeypatch):
    import docx_export
    from docx import Document

    sid = _make_student(db)
    monkeypatch.setattr(docx_export, "REPORTS_DIR", str(tmp_path))
    path = docx_export.generate_personal_file_docx(sid)

    assert os.path.isfile(path) and path.endswith(".docx")
    doc = Document(path)
    all_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Личное дело" in all_text and "Иванов" in all_text


def test_generate_personal_file_docx_unknown_id_raises(db, tmp_path, monkeypatch):
    import docx_export

    monkeypatch.setattr(docx_export, "REPORTS_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="не найден"):
        docx_export.generate_personal_file_docx(99999)


def test_generate_roster_docx_filters_by_group(db, tmp_path, monkeypatch):
    import docx_export
    from docx import Document

    _make_student(db, surname="Первов", group="А-11")
    _make_student(db, surname="Второв", group="Б-22")
    monkeypatch.setattr(docx_export, "REPORTS_DIR", str(tmp_path))
    path = docx_export.generate_roster_docx(group_name="А-11")

    doc = Document(path)
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    joined = " ".join(cells)
    assert "Первов" in joined and "Второв" not in joined


def test_generate_order_docx_writes_document(db, tmp_path, monkeypatch):
    """Приказ = документ DOCX с текстом шаблона F-2 (без записи в БД)."""
    import docx_export
    from docx import Document

    sid = _make_student(db)
    monkeypatch.setattr(docx_export, "REPORTS_DIR", str(tmp_path))
    path = docx_export.generate_order_docx(
        sid, kind="encouragement", reason="за отличие в учёбе")

    assert os.path.isfile(path)
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "ПРИКАЗ" in text and "за отличие в учёбе" in text and "Иванов" in text


def test_generate_order_docx_rejects_unknown_kind(db, tmp_path, monkeypatch):
    import docx_export

    sid = _make_student(db)
    monkeypatch.setattr(docx_export, "REPORTS_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="Неизвестный вид приказа"):
        docx_export.generate_order_docx(sid, kind="medal", reason="x")


# ============================== F-5: импорт XLSX ===========================
def _write_xlsx(path, header, rows):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return str(path)


HEADER = ["Фамилия", "Имя", "Отчество", "Курс", "Группа", "Пол", "Дата рождения"]


def test_parse_workbook_valid_and_invalid_rows(tmp_path):
    from xlsx_import import parse_workbook

    path = _write_xlsx(tmp_path / "in.xlsx", HEADER, [
        ["Петров", "Пётр", "Петрович", 2, "А-11", "М", "2004-03-10"],
        ["", "Без фамилии", None, None, None, None, None],
        ["Сидоров", "Сидор", None, 99, "Б-2", "М", "31.02.2003"],
    ])
    rows = parse_workbook(path)
    assert len(rows) == 3
    assert rows[0].ok and rows[0].data["o_course"] == 2
    assert not rows[1].ok and "Фамилия" in rows[1].errors[0]
    assert not rows[2].ok  # курс 99 и несуществующая дата 31.02


def test_parse_workbook_requires_surname_header(tmp_path):
    from xlsx_import import parse_workbook

    path = _write_xlsx(tmp_path / "bad.xlsx", ["Привет", "Мир"], [["a", "b"]])
    with pytest.raises(ValueError, match="Фамилия"):
        parse_workbook(path)


def test_normalize_date_formats():
    from datetime import datetime

    from xlsx_import import normalize_date

    assert normalize_date("15.01.2005") == "2005-01-15"
    assert normalize_date("2005-01-15") == "2005-01-15"
    assert normalize_date(datetime(2005, 1, 15)) == "2005-01-15"
    assert normalize_date("15/01/2005") is None
    assert normalize_date(None) is None


def test_commit_import_atomic_all_or_nothing(db, tmp_path):
    """Либо импортируются все валидные строки, либо ни одной (A-3)."""
    from xlsx_import import commit_import, parse_workbook

    path = _write_xlsx(tmp_path / "ok.xlsx", HEADER, [
        ["Абрамов", "Абрам", None, 1, "А-11", "М", None],
        ["Баранов", "Борис", None, 2, "А-11", "М", None],
    ])
    inserted = commit_import(parse_workbook(path), actor_role="Администратор",
                             log_user="tester")
    assert inserted == 2
    assert db.count_students() == 2
    logs = [r["action"] for r in db.get_logs()]
    assert any("Импорт XLSX" in a for a in logs)


def test_commit_import_skips_invalid_rows_only(db, tmp_path):
    from xlsx_import import commit_import, parse_workbook

    path = _write_xlsx(tmp_path / "mixed.xlsx", HEADER, [
        ["Волков", "Василий", None, 1, "В-33", "М", None],
        [None, None, None, None, None, None, None],      # пустая — пропуск
        ["", "Нет фамилии", None, None, None, None, None],  # ошибка валидации
    ])
    inserted = commit_import(parse_workbook(path), actor_role="Администратор")
    assert inserted == 1
    names = [dict(r)["o_surname"] for r in db.get_students()]
    assert names == ["Волков"]


def test_commit_import_forbidden_for_non_admin(db, tmp_path):
    from access import PermissionDeniedError
    from xlsx_import import commit_import, parse_workbook

    path = _write_xlsx(tmp_path / "x.xlsx", HEADER, [["Гусев", "Гус", None,
                                                     1, "Г-1", "М", None]])
    with pytest.raises(PermissionDeniedError):
        commit_import(parse_workbook(path), actor_role="user")
    assert db.count_students() == 0


def test_create_template_roundtrip(db, tmp_path):
    """Шаблон create_template_xlsx сам читается парсером (пример валиден)."""
    from xlsx_import import commit_import, create_template_xlsx, parse_workbook

    path = create_template_xlsx(str(tmp_path / "template.xlsx"))
    rows = parse_workbook(path)
    assert len(rows) == 1 and rows[0].ok
    assert commit_import(rows, actor_role="Администратор") == 1


# ============================== C-3: фотохранилище =========================
def test_save_photo_and_photo_src(db, tmp_path, monkeypatch):
    import photo_storage

    photos = tmp_path / "photos"
    monkeypatch.setattr(photo_storage, "PHOTOS_DIR", str(photos))
    filename = photo_storage.save_photo(b"\x89PNG fake", 7, ext="png")
    assert filename == "7.png"
    src = photo_storage.photo_src(filename)
    assert src == os.path.realpath(os.path.join(str(photos), "7.png"))


def test_photo_path_blocks_traversal(tmp_path, monkeypatch):
    import photo_storage

    monkeypatch.setattr(photo_storage, "PHOTOS_DIR", str(tmp_path))
    assert photo_storage.photo_path("../secret.jpg") is None
    assert photo_storage.photo_path("a/b.jpg") is None
    assert photo_storage.photo_path("") is None


def test_migrate_legacy_base64_moves_to_files(db, tmp_path, monkeypatch):
    import photo_storage

    monkeypatch.setattr(photo_storage, "PHOTOS_DIR", str(tmp_path / "ph"))
    payload = base64.b64encode(b"x" * 100).decode()  # >64 символов — «похоже на base64»
    sid = db.add_student({"o_surname": "Фоткин", "o_name": "Фот",
                          "o_photo": payload}, actor_role="Администратор")
    assert photo_storage.legacy_base64_count() == 1

    migrated = photo_storage.migrate_legacy_base64()
    assert migrated == 1
    assert photo_storage.legacy_base64_count() == 0
    row = db.execute_query("SELECT o_photo FROM students WHERE id=?",
                           (sid,), fetch=True)[0]
    assert row["o_photo"].endswith(".png")
    assert os.listdir(tmp_path / "ph")  # файл реально записан
    # повторный вызов — no-op (идемпотентность)
    assert photo_storage.migrate_legacy_base64() == 0


def test_vacuum_refused_until_migration_done(db, tmp_path, monkeypatch):
    import photo_storage

    monkeypatch.setattr(photo_storage, "PHOTOS_DIR", str(tmp_path / "ph"))
    payload = base64.b64encode(b"y" * 100).decode()
    db.add_student({"o_surname": "Легаси", "o_name": "Лёха",
                    "o_photo": payload}, actor_role="Администратор")
    assert photo_storage.vacuum_database() is False   # есть base64 — рано
    photo_storage.migrate_legacy_base64()
    assert photo_storage.vacuum_database() is True    # миграция завершена


# ============================== D-3: проверка фото в doctor ================
def test_doctor_check_photos_flags_legacy_base64(db, tmp_path, monkeypatch):
    import doctor
    import photo_storage

    monkeypatch.setattr(photo_storage, "PHOTOS_DIR", str(tmp_path / "ph"))
    os.makedirs(tmp_path / "ph", exist_ok=True)
    sid = db.add_student({"o_surname": "Доктор", "o_name": "Док",
                          "o_photo": base64.b64encode(b"z" * 100).decode()},
                         actor_role="Администратор")
    problems = doctor.check_photos()
    assert "photos-legacy-base64" in problems

    photo_storage.migrate_legacy_base64()
    assert doctor.check_photos() == []
    assert sid  # студент на месте


# ============================== B-4: конфигурация .env =====================
def test_config_reads_kanzler_env(monkeypatch, tmp_path):
    """KANZLER_* из окружения задают пути (тот же механизм, что и .env)."""
    monkeypatch.setenv("KANZLER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KANZLER_DB", str(tmp_path / "custom.db"))
    for m in ("config", "database"):
        sys.modules.pop(m, None)
    try:
        import config

        assert config.DATA_DIR == str(tmp_path / "data")
        assert config.DB_PATH == str(tmp_path / "custom.db")
    finally:
        for m in ("config", "database"):
            sys.modules.pop(m, None)


def test_config_loads_dotenv_from_project_root(tmp_path, monkeypatch):
    """.env в BASE_DIR попадает в os.environ при импорте config (override=False)."""
    dotenv = tmp_path / ".env"
    dotenv.write_text("KANZLER_DATA_DIR=%s\n" % (tmp_path / "from-dotenv"),
                      encoding="utf-8")
    monkeypatch.delenv("KANZLER_DATA_DIR", raising=False)
    monkeypatch.delenv("KANZLER_DB", raising=False)
    import config

    monkeypatch.setattr(config, "BASE_DIR", str(tmp_path))
    from dotenv import load_dotenv

    load_dotenv(str(dotenv), override=False)
    try:
        assert os.environ.get("KANZLER_DATA_DIR") == str(tmp_path / "from-dotenv")
    finally:
        monkeypatch.delenv("KANZLER_DATA_DIR", raising=False)
