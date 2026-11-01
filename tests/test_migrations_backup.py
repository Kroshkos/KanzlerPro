"""Тесты миграции схемы (BACKLOG T-2) и резервного копирования (A-4).

Чтобы воспроизвести «старую» БД, тестовый хендс-ап пересоздаёт таблицу
users без проверяемых колонок — так, как если бы файл был создан до их
появления. После этого migrate_schema()/check_user обязаны идемпотентно
добавить недостающее через ensure_column.
"""

import os
import sqlite3


def _recreate_users_without(db, columns):
    """Пересоздаёт users без указанных колонок (эмуляция старой схемы)."""
    remaining = [c for c in db.table_columns("users") if c not in columns]
    conn = db.connect_to_db()
    try:
        conn.execute("DROP TABLE users")
        conn.execute("CREATE TABLE users (" +
                     ", ".join(remaining) + ")")
        conn.commit()
    finally:
        conn.close()


# ---------- T-2: идемпотентность ensure_column / migrate_schema ----------

def test_ensure_column_adds_once(db):
    assert db.ensure_column("users", "failed_attempts",
                            "INTEGER NOT NULL DEFAULT 0") is False  # уже есть
    assert db.ensure_column("students", "extra_probe", "TEXT") is True
    assert db.ensure_column("students", "extra_probe", "TEXT") is False


def test_ensure_column_rejects_bad_identifiers(db):
    import pytest
    with pytest.raises(ValueError):
        db.ensure_column("students; DROP", "x")


def test_migrate_schema_restores_missing_columns(db):
    """Старая БД без новых колонок -> migrate_schema их доавляет."""
    _recreate_users_without(db, {"locked_until", "failed_attempts"})
    assert "locked_until" not in db.table_columns("users")

    added = db.migrate_schema()
    assert "locked_until" in added and "failed_attempts" in added
    cols = db.table_columns("users")
    assert "locked_until" in cols and "failed_attempts" in cols

    # идемпотентность: повторный вызов ничего не добавляет
    assert db.migrate_schema() == []


def test_check_user_works_on_unmigrated_db(db):
    """check_user сам тянет миграцию счётчиков (защита от прямого запуска
    поверх старой базы без явного migrate_schema)."""
    _recreate_users_without(db, {"failed_attempts", "locked_until"})
    db.add_user("probe", "probe-password", "Пользователь")
    assert db.check_user("probe", "probe-password") is not None
    assert "failed_attempts" in db.table_columns("users")


# ---------- A-4: резервное копирование ----------

def test_backup_creates_copy_and_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("KANZLER_DB", str(tmp_path / "src.db"))
    for m in ("config", "database"):
        import sys
        sys.modules.pop(m, None)
    import database as db

    db.init_db()
    db.add_user("backupuser", "backuppass1", "Пользователь")

    backups_dir = tmp_path / "backups"
    dest = db.backup_database(backups_dir=backups_dir, keep=3)
    assert dest and os.path.exists(dest)
    # копия читается и содержит данные оригинала
    con = sqlite3.connect(dest)
    n = con.execute("SELECT COUNT(*) FROM users WHERE username='backupuser'").fetchone()[0]
    con.close()
    assert n == 1

    # ротация: создаём ещё копии и проверяем, что старше `keep` удаляются
    for _ in range(4):
        db.backup_database(backups_dir=backups_dir, keep=3)
    files = [f for f in os.listdir(backups_dir) if f.endswith(".db")]
    # метка времени до секунды — при быстром цикле имена могут совпасть;
    # проверяем только верхнюю границу количества
    assert len(files) <= 3 + 1  # 3 свежих + возможное совпадение метки


def test_backup_returns_none_without_db(tmp_path, monkeypatch):
    monkeypatch.setenv("KANZLER_DB", str(tmp_path / "missing.db"))
    for m in ("config", "database"):
        import sys
        sys.modules.pop(m, None)
    import database as db
    assert db.backup_database(backups_dir=tmp_path / "b") is None


# ---------- C-2: индексы под частые фильтры ----------

def test_frequent_filter_indexes_exist(db):
    """init_mkr_tables() создаёт индексы под типовые выборки (A-план C-2)."""
    db.init_mkr_tables()
    conn = db.connect_to_db()
    try:
        # row_factory не выставлен — строки обычные кортежи, имя индекса [1]
        names = {r[1] for r in
                 conn.execute("PRAGMA index_list(students)").fetchall()}
    finally:
        conn.close()
    assert {"idx_students_surname", "idx_students_group",
            "idx_students_course"} <= names
