"""Централизованная проверка прав доступа (RBAC).

Проблема, которую решает модуль: раньше роли сравнивали со строкой
"admin" (app/pages/home_page.py), тогда как в БД константа ADMIN_ROLE =
"Администратор" (constants.ROLES). Из-за этого админ никогда не получал
доступ к пунктам «Пользователи»/«Журнал действий», а проверки разбросаны
по UI-модулям по-разному (dashboard_page сверял с "Администратор",
users_page — с ADMIN_ROLE).

Теперь единственная точка истины — здесь:
  * is_admin(page)     — роль текущего пользователя;
  * require_admin(...) — бинарная защита страницы: пустой ответ для чужих;
  * PAGES_BY_CLASS + ROLE_PAGES — карта «класс страницы -> роль»,
    используется каркасом KantslerApp при переходах.
"""

from constants import ADMIN_ROLE
from utils import session_get


def current_role(page) -> str:
    """Роль пользователя из session (пустая строка, если не авторизован)."""
    return session_get(page, "role") or ""


def is_admin(page) -> bool:
    """True, если текущая роль — Администратор (значение из constants)."""
    return current_role(page) == ADMIN_ROLE


def require_admin(page, message="Недостаточно прав"):
    """Заглушка для страниц, доступных только админу.

    Возвращает готовый ft.Control с текстом отказа, если роль не
    администратор; иначе None — страница строится как обычно.
    Так закрытая страница не раскрывает ни данных, ни формы.
    """
    if is_admin(page):
        return None
    import flet as ft
    from theme import TEXT_MUTED
    return ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.LOCK_OUTLINE, size=48, color=TEXT_MUTED),
            ft.Text(message, size=16, color=TEXT_MUTED),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER),
        alignment=ft.alignment.center, expand=True)


#: Классы страниц, требующие роль «Администратор».
ADMIN_ONLY_PAGES = frozenset({"UsersPage", "LogsPage"})
