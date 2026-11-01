"""Тесты файлового фотохранилища и каскадного удаления курсанта.

Закрывают находки аудита: (а) base64-фото в БД раздували SELECT *, теперь
в o_photo лежит имя файла; (б) delete_student должен чистить связанные записи.
"""

import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


@pytest.fixture()
def photo_env(tmp_path, monkeypatch):
    """Чистая БД + отдельный каталог фото."""
    monkeypatch.setenv("KANZLER_DB", str(tmp_path / "p.db"))
    monkeypatch.setenv("KANZLER_DATA_DIR", str(tmp_path))
    for mod in ("config", "database", "repositories", "photo_storage"):
        sys.modules.pop(mod, None)
    import database
    database.init_db()
    import photo_storage
    import repositories as repo
    yield database, photo_storage, repo
    for mod in ("config", "database", "repositories", "photo_storage"):
        sys.modules.pop(mod, None)


def test_save_photo_writes_file_not_base64(photo_env):
    _db, ps, repo = photo_env
    sid = repo.add_student({"o_surname": "А", "o_name": "Б", "o_lastname": "В"})
    name = ps.save_photo(b"\xff\xd8fakejpeg", sid, "jpg")
    assert name == f"{sid}.jpg"
    repo.update_student_fields(sid, {"o_photo": name})
    cols = repo.get_student_columns()
    row = repo.get_student_full(sid)
    assert row[cols.index("o_photo")] == name
    assert os.path.exists(ps.photo_path(name))


def test_photo_src_backwards_compatible_with_base64(photo_env):
    _db, ps, _repo = photo_env
    import base64
    # Реалистичное фото-base64: >=64 символов (порог looks_like_base64).
    b64 = base64.b64encode(b"\xff\xd8" + b"old-photo-bytes" * 10).decode()
    assert ps.looks_like_base64(b64)
    assert ps.photo_src(b64).startswith("data:image/jpeg;base64,")
    # Имя несуществующего файла -> пусто (UI покажет заглушку), а не путь наружу
    assert ps.photo_src("../etc/passwd") == ""
    assert ps.photo_src("") == ""


def test_get_student_columns_matches_select_star(photo_env):
    _db, _ps, repo = photo_env
    sid = repo.add_student({"o_surname": "X"})
    row = repo.get_student_full(sid)
    cols = repo.get_student_columns()
    assert len(cols) == len(row)
    assert cols[0] == "id"
    assert "o_photo" in cols


def test_delete_student_cascades_child_rows(photo_env):
    db, _ps, repo = photo_env
    sid = repo.add_student({"o_surname": "Ю", "o_name": "Я"})
    repo.add_position(sid, "командир", "admin", "2026-01-01", "1")
    repo.add_rank(sid, "лейтенант", "admin", "2026-01-02", "2")
    db.add_encouragement(sid, "грамота", "за успехи", "admin", "2026-01-03", "3")
    db.add_penalty(sid, "выговор", "за опоздание", "2026-01-04", "admin", "2026-01-05", "4")

    assert repo.delete_student(sid) is True
    assert repo.get_student_full(sid) is None
    assert repo.get_position_history(sid) == []
    assert repo.get_rank_history(sid) == []
    assert db.get_encouragements_by_student(sid) == []
    assert db.get_penalties_by_student(sid) == []
    # Чужие данные не задеты
    other = repo.add_student({"o_surname": "Другой"})
    assert repo.delete_student(999999) is False
    assert repo.get_student_full(other) is not None


def test_edit_page_keys_pattern(photo_env):
    """Регрессия: student в EditStudentPage — sqlite3.Row, .keys() обязано работать.

    Историческая ошибка: set(row) бросал TypeError и «молча» отменял сохранение.
    Проверяем канонический паттерн фильтрации обновлений по схеме.
    """
    _db, _ps, repo = photo_env
    sid = repo.add_student({"o_surname": "Редакт", "o_name": "Тест"})
    student = repo.get_student_full(sid)
    assert hasattr(student, "keys"), "get_student_full должен возвращать sqlite3.Row"
    updates = {"o_surname": "Новая", "нет_такой_колонки": "x"}
    existing = set(student.keys())
    filtered = {k: v for k, v in updates.items() if k in existing}
    assert filtered == {"o_surname": "Новая"}
    assert repo.update_student_fields(sid, filtered) is True
    cols = repo.get_student_columns()
    row2 = repo.get_student_full(sid)
    assert row2[cols.index("o_surname")] == "Новая"


def test_migrate_legacy_base64(photo_env):
    """Старые base64-значения в o_photo переносятся в файлы при миграции."""
    import base64 as b64
    _db, ps, repo = photo_env
    sid = repo.add_student({"o_surname": "Старый", "o_name": "Ф", "о_lastname" if False else "o_lastname": "Ото"})
    legacy = b64.b64encode(b"\x89PNG fake image bytes" * 10).decode()
    assert ps.looks_like_base64(legacy)
    _db.execute_query("UPDATE students SET o_photo = ? WHERE id = ?", params=(legacy, sid))
    # до миграции photo_src отдаёт data-URI (обратная совместимость)
    src_before = ps.photo_src(_db.execute_query("SELECT o_photo FROM students WHERE id=?", params=(sid,), fetch=True)[0]["o_photo"])
    assert src_before and src_before.startswith("data:")
    n = ps.migrate_legacy_base64()
    assert n == 1
    row = _db.execute_query("SELECT o_photo FROM students WHERE id = ?", params=(sid,), fetch=True)[0]
    assert row["o_photo"] == f"{sid}.png"
    assert os.path.exists(os.path.join(ps.PHOTOS_DIR, f"{sid}.png"))
    # повторный вызов — no-op
    assert ps.migrate_legacy_base64() == 0
