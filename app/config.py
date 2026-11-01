"""Единая конфигурация приложения «Канцлер Про».

Хранит пути (база данных, каталоги данных/отчётов) и общие параметры UI.
Все модули берут значения отсюда, чтобы не зависеть от текущей директории,
из которой запущено приложение.

Секреты (BACKLOG B-4): при наличии файла `.env` в корне проекта он
загружается python-dotenv ОДИН раз при импорте config — переменные из
файла попадают в os.environ ДО чтения KANZLER_* ниже. Значения, уже
выставленные в окружении процесса, имеют приоритет (override=False),
поэтому CI/тесты с monkeypatch.setenv не ломаются. Секретов в репозитории
нет; `.env` внесён в .gitignore, образец — `.env.example`.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # корень проекта

# --- B-4: локальный .env как источник секретов вне репозитория -------------
try:  # dotenv — опциональная dev-зависимость: без неё приложение работает
    from dotenv import load_dotenv

    load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)
except ImportError:  # pragma: no cover
    pass

DATA_DIR = os.environ.get("KANZLER_DATA_DIR", os.path.join(BASE_DIR, "data"))
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

DB_PATH = os.environ.get("KANZLER_DB", os.path.join(DATA_DIR, "kanzler_pro.db"))


def ensure_dirs():
    for d in (DATA_DIR, REPORTS_DIR, PHOTOS_DIR):
        os.makedirs(d, exist_ok=True)
