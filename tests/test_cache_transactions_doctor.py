"""Тесты новых модулей промежуточной ветки: кэш (C-4), транзакции (A-3),
пагинация журнала (C-1) и консольная диагностика doctor (D-5).

Закрепляют поведение, заявленное в BACKLOG.md, чтобы незакоммиченные
изменения можно было верифицировать через pytest.
"""



# ---------- app/cache.py: кэш справочников с инвалидацией (C-4) ----------

def test_cached_computes_once_and_serves_from_memory(db):
    """loader() вызывается ровно один раз; повторные чтения — из памяти."""
    import cache

    cache.invalidate_all()
    calls = []

    def loader():
        calls.append(1)
        return ["Г-1", "Г-2"]

    assert cache.cached("t:groups", loader) == ["Г-1", "Г-2"]
    assert cache.cached("t:groups", loader) == ["Г-1", "Г-2"]
    assert len(calls) == 1, "второй вызов должен отдавать закэшированное значение"
    cache.invalidate_all()


def test_invalidate_by_table_clears_only_dependent_keys(db):
    import cache

    cache.invalidate_all()
    cache.cached("students:groups", lambda: ["Г-1"], table="students")
    cache.cached("other:key", lambda: [1, 2], table="logs")

    cache.invalidate("students")
    assert "students:groups" not in cache.stats()
    assert "other:key" in cache.stats(), "инвалидация точечная, по таблице"

    cache.invalidate_all()
    assert cache.stats() == []


def test_add_student_invalidates_groups_cache(db):
    """Мутатор students сбрасывает кэш справочника групп (C-4)."""
    import cache

    cache.invalidate_all()
    db.execute_query(
        "INSERT INTO students (o_surname, o_name, o_lastname, o_course,"
        " o_group_name) VALUES ('Иванов', 'И', 'И', 1, 'А-101')")

    groups = cache.cached(
        "students:groups",
        lambda: [str(r[0]) for r in (db.list_groups() or [])],
        table="students")
    assert groups == ["А-101"]

    db.add_student({"o_surname": "Петров", "o_name": "П", "o_lastname": "П",
                    "o_course": 2, "o_group_name": "Б-202"},
                   actor_role="Администратор")
    # Кэш сброшен мутатором — следующее чтение увидит новую группу.
    assert "students:groups" not in cache.stats()
    fresh = cache.cached(
        "students:groups",
        lambda: [str(r[0]) for r in (db.list_groups() or [])],
        table="students")
    assert sorted(fresh) == ["А-101", "Б-202"]
    cache.invalidate_all()


# ---------- database.transaction(): атомарность пакетных операций (A-3) ----------

def test_transaction_commits_all_rows(db):
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO students (o_surname, o_name, o_lastname, o_course,"
            " o_group_name) VALUES (?, 'И', 'И', 1, 'Г-1')", ("Абрамов",))
        conn.execute(
            "INSERT INTO students (o_surname, o_name, o_lastname, o_course,"
            " o_group_name) VALUES (?, 'И', 'И', 1, 'Г-1')", ("Барсов",))
    assert db.count_students() == 2


def test_transaction_rolls_back_on_error(db):
    try:
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO students (o_surname, o_name, o_lastname,"
                " o_course, o_group_name) VALUES ('Волков', 'И', 'И', 1, 'Г-1')")
            raise RuntimeError("сбой в середине пакета")
    except RuntimeError:
        pass
    assert db.count_students() == 0, "ни одна строка не должна записаться"


def test_wal_journal_mode_enabled(db):
    """PRAGMA journal_mode = WAL применяется при каждом подключении (A-3)."""
    conn = db.connect_to_db()
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    # На сетевых ФС WAL может быть недоступен — тогда допустим другой режим,
    # но для обычных tmp-файлов ожидаем именно wal.
    assert str(mode).lower() == "wal"


# ---------- Пагинация журнала действий (C-1, продолжение) ----------

def _seed_logs(db, n):
    for i in range(1, n + 1):
        db.log_action("admin", f"действие {i:03d}")


def test_get_logs_pagination_pages_are_disjoint(db):
    _seed_logs(db, db.LOGS_PAGE_SIZE + 7)
    total = db.count_logs()
    assert total == db.LOGS_PAGE_SIZE + 7

    page1 = db.get_logs(limit=db.LOGS_PAGE_SIZE, offset=0)
    page2 = db.get_logs(limit=db.LOGS_PAGE_SIZE, offset=db.LOGS_PAGE_SIZE)
    assert len(page1) == db.LOGS_PAGE_SIZE
    assert len(page2) == 7
    actions = [r["action"] for r in page1] + [r["action"] for r in page2]
    assert len(actions) == len(set(actions)), "страницы не пересекаются"


def test_get_logs_no_limit_backward_compatible(db):
    _seed_logs(db, 5)
    assert len(db.get_logs()) == 5, "limit=None сохраняет прежний результат"


def test_count_logs_with_date_prefix(db):
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    _seed_logs(db, 3)
    assert db.count_logs(date_prefix=today + "%") == 3
    assert db.count_logs(date_prefix="1999-01-01%") == 0
    page = db.get_logs(limit=2, offset=0, date_prefix=today + "%")
    assert len(page) == 2


# ---------- app/doctor.py: консольная диагностика (D-5) ----------

def test_doctor_checks_pass_on_fresh_db(db, tmp_path, monkeypatch):
    """На чистой проинициализированной БД все проверки doctor проходят."""
    import config

    # Изолируем каталог данных во временную папку: doctor проверяет наличие
    # свежих резервных копий в DATA_DIR/backups (A-4), чего в tmp-базе нет.
    data_dir = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", str(data_dir))
    db.backup_database()  # создаёт копию — как при старте приложения в main.py

    import doctor

    problems = []
    problems += doctor.check_database_integrity()
    problems += doctor.check_logs_chain()
    problems += doctor.check_backups()
    assert problems == [], f"doctor нашёл проблемы: {problems}"


def test_doctor_detects_missing_db(db, tmp_path):
    """Отсутствующий файл БД — корректный код проблемы, без исключения."""
    import config
    import doctor

    missing = tmp_path / "nope.db"
    # doctor перечитывает DB_PATH из config при каждом вызове — подменяем атрибут.
    saved = config.DB_PATH
    try:
        config.DB_PATH = str(missing)
        assert doctor.check_database_integrity() == ["db-missing"]
    finally:
        config.DB_PATH = saved
