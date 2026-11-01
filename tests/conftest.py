"""Общая фикстура тестов «Канцлер Про».

Модули приложения используют плоские импорты (from database import ...),
поэтому каталог app/ добавляется в sys.path до импорта любых модулей —
как это делает main.py при обычном запуске.

Каждый тест получает ЧИСТУЮ временную базу SQLite: путь берётся из
переменной окружения KANZLER_DB, которую читает config.py. Фикстура
сбрасывает уже импортированные модули БД, чтобы константа DB_PATH
пересчиталась для нового tmp-файла.
"""

import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Временная база с полной схемой; возвращает модуль database."""
    db_file = tmp_path / "test_kanzler.db"
    monkeypatch.setenv("KANZLER_DB", str(db_file))

    # config.DB_PATH вычисляется при импорте — сбрасываем кэш модулей,
    # читающих конфигурацию, чтобы они увидели новый KANZLER_DB.
    _reset_mod_cache()

    import database
    database.init_db()  # схема Kanzler + MKR-таблицы (init_mkr_tables внутри)
    yield database

    _reset_mod_cache()


def _reset_mod_cache():
    """Удаляет из sys.modules все модули приложения, кэширующие конфиг/БД.

    Страницы держат on-import ссылки на функции database.*, поэтому без их
    сброса следующий тест получил бы устаревший DB_PATH (flaky-поведение).
    """
    stale = [m for m in list(sys.modules)
             if m.split(".")[0] in {"config", "database", "repositories", "ui_kit"}
             or m.startswith(("pages", "authz"))]
    for m in stale:
        sys.modules.pop(m, None)
