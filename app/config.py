"""Единая конфигурация приложения «Канцлер Про».

Хранит пути (база данных, каталоги данных/отчётов) и общие параметры UI.
Все модули берут значения отсюда, чтобы не зависеть от текущей директории,
из которой запущено приложение.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # корень проекта

DATA_DIR = os.environ.get("KANZLER_DATA_DIR", os.path.join(BASE_DIR, "data"))
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

DB_PATH = os.environ.get("KANZLER_DB", os.path.join(DATA_DIR, "kanzler_pro.db"))


def ensure_dirs():
    for d in (DATA_DIR, REPORTS_DIR, PHOTOS_DIR):
        os.makedirs(d, exist_ok=True)
