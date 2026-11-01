"""«Канцлер Про» — объединённое приложение (Kanzler + MKR «Дорожная карта»).

Точка входа: авторизация → новый информативный дашборд с боковой навигацией.
База данных SQLite создаётся заново (data/kanzler_pro.db) и заполняется
пользователями программы.

Запуск:
    python main.py

Первичная учётная запись администратора:
    логин: admin
    пароль: берётся из переменной окружения KANZLER_ADMIN_PASSWORD,
            иначе генерируется случайный и выводится в консоль один раз.
"""

import os
import sys

# Все модули приложения лежат в каталоге app/ — добавляем его в путь импорта,
# чтобы запуск был возможен из любой рабочей директории.
APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import flet as ft

from config import ensure_dirs
from database import init_db


def main(page: ft.Page):
    ensure_dirs()
    init_db()  # схема Kanzler + таблицы Дорожной карты (MKR) в одной базе

    # Однократная миграция старых base64-фото из БД в файловое хранилище
    # (no-op, если все записи уже перенесены).
    try:
        from photo_storage import migrate_legacy_base64
        n = migrate_legacy_base64()
        if n:
            print(f"[photo_storage] перенесено base64-фото в файлы: {n}")
    except Exception as e:
        from utils_logger import log_except
        log_except("main: миграция base64-фото", e)

    # ---------- Параметры окна ----------
    page.title = "Канцлер Про"
    page.window = ft.Window(
        width=1440,
        height=900,
        min_width=1024,
        min_height=700,
    )
    page.padding = 0
    page.bgcolor = "#f1f5f9"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.font_family = "Segoe UI"
    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary="#3b82f6",
            secondary="#8b5cf6",
            surface="#ffffff",
            surface_container="#f1f5f9",
            surface_container_low="#f8fafc",
            surface_container_high="#e2e8f0",
        ),
    )

    from pages.registry import get_page  # после init_db — страницы тянут БД
    page.add(get_page("LoginPage")(page))


if __name__ == "__main__":
    ft.run(main)
