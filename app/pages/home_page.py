import flet as ft
import pandas as pd
# tkinter используется только для диалога выбора пути сохранения файлов;
# импорт выполняется лениво внутри методов, чтобы приложение запускалось
# даже на системах без установленной среды X11/tkinter.
import os
import shutil
import base64
from openpyxl.utils import get_column_letter
from datetime import datetime, timedelta
from database import add_student, get_students, check_user, search_students_by_multiple_params, add_encouragement, get_encouragements_by_student, add_penalty, get_penalties_by_student, search_students_by_name_part, get_subjects_by_name_part, log_action, get_users, add_user, update_user_role, delete_user, get_logs, get_user_by_id, update_user_password
# Слой репозиториев: UI больше не пишет SQL напрямую (см. repositories.py)
import repositories as repo
from constants import ROLES, ADMIN_ROLE, DEFAULT_ROLE, EDITABLE_STUDENT_FIELDS
from pages.registry import get_page
from utils import session_get, session_set, session_clear


from theme import BG, PRIMARY, TEXT_DARK


class KantslerApp(ft.Column):
    """Каркас приложения «Канцлер Про».

    Точка входа после авторизации: боковая навигация + область содержимого.
    По умолчанию открывается новый информативный дашборд; классическое
    кнопочное меню Канцлера сохранено как LegacyMenu и доступно с дашборда.
    """

    #: Пункты бокового меню: (класс страницы, подпись, иконка)
    NAV_ITEMS = [
        ("DashboardPage", "Дашборд", ft.Icons.SPACE_DASHBOARD_ROUNDED),
        ("SearchPage", "Поиск курсанта", ft.Icons.SEARCH),
        ("KadriWorkPage", "Кадровая работа", ft.Icons.BADGE),
        ("SessionResultsPage", "Учебная работа", ft.Icons.SCHOOL),
        ("VprWorkPage", "ВПР", ft.Icons.SHIELD),
        ("PremiaWorkPage", "Премии", ft.Icons.WALLET),
        ("PersonalFilePage", "Личное дело", ft.Icons.FOLDER_SPECIAL),
        ("RoadmapCatalogPage", "Достижения Road Map", ft.Icons.CELL_TOWER),
        ("RoadmapExpertPage", "Экспертиза", ft.Icons.VERIFIED),
        ("RoadmapIprPage", "ИПР курсанта", ft.Icons.EVENT_NOTE),
    ]
    ADMIN_ITEMS = [
        ("UsersPage", "Пользователи", ft.Icons.PERSON_ADD_ALT),
        ("LogsPage", "Журнал действий", ft.Icons.HISTORY),
    ]

    def __init__(self, page):
        super().__init__()
        if page is None:
            raise ValueError("Page is null")
        # Защита от прямого входа без авторизации (например, вызов из консоли/отладки)
        if not session_get(page, "username"):
            page.controls.clear()
            page.add(get_page("LoginPage")(page))
            page.update()
            return
        self._page = page
        self.username = session_get(self._page, "username")
        self.role = session_get(page, "role")

        # ---------- Каркас нового интерфейса ----------
        self.content_area = ft.Container(expand=True, bgcolor=BG)
        self.nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=92,
            bgcolor="#ffffff",
            indicator_color="rgba(59,130,246,0.18)",
            leading=ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.SHIELD_ROUNDED, color=PRIMARY, size=30),
                    ft.Text("Канцлер\nПро", size=11, weight="bold",
                            color=TEXT_DARK, text_align="center"),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                padding=ft.Padding(0, 12, 0, 12)),
            trailing=ft.Container(
                content=ft.Column([
                    ft.IconButton(ft.Icons.LOGOUT, tooltip="Выход",
                                  on_click=self.logout_click),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(0, 0, 0, 12)),
            destinations=[],
            on_change=self.on_nav_change,
        )
        items = list(self.NAV_ITEMS)
        if self.role == ADMIN_ROLE:
            items += list(self.ADMIN_ITEMS)
        self._nav_names = []
        for name, label, icon in items:
            self._nav_names.append(name)
            self.nav_rail.destinations.append(
                ft.NavigationRailDestination(icon=icon, selected_icon=icon,
                                             label=label))

        shell = ft.Row([
            self.nav_rail,
            ft.VerticalDivider(width=1, color="#e2e8f0"),
            self.content_area,
        ], spacing=0, expand=True)
        self.controls = [shell]
        self.show_dashboard()

    # ------------------------------------------------------------------
    # Навигация каркаса
    # ------------------------------------------------------------------
    def on_nav_change(self, e):
        idx = e.control.selected_index
        if 0 <= idx < len(self._nav_names):
            self.go_to(self._nav_names[idx], keep_selection=idx)

    def go_to(self, cls_name, keep_selection=None):
        """Открывает страницу внутри области содержимого (без перезагрузки page)."""
        if cls_name is None:
            self.show_legacy_menu()
            return
        page_cls = get_page(cls_name)
        try:
            view = page_cls(self._page, parent=self)
        except TypeError:
            view = page_cls(self._page)
        self.content_area.content = view
        names = self._nav_names + ["LegacyMenu"]
        if keep_selection is not None:
            self.nav_rail.selected_index = keep_selection
        elif cls_name in names:
            self.nav_rail.selected_index = names.index(cls_name)
        self._page.update()

    def show_dashboard(self):
        self.go_to("DashboardPage", keep_selection=0)

    def show_legacy_menu(self):
        """Возврат к классическому кнопочному меню Канцлера."""
        legacy = LegacyMenu(self._page, parent=self)
        self.content_area.content = legacy
        self.nav_rail.selected_index = len(self._nav_names)  # пункт неактивен
        self._page.update()

    def logout_click(self, e=None):
        log_action(self.username, "Выход из учетной записи")
        session_clear(self._page)
        self._page.controls.clear()
        self._page.add(get_page("LoginPage")(self._page))
        self._page.update()


class LegacyMenu(ft.Column):
    """Классическое кнопочное меню Канцлера (сохранено как запасной вариант)."""

    def __init__(self, page, parent=None):
        super().__init__()
        if page is None:
            raise ValueError("Page is null")
        if not session_get(page, "username"):
            page.controls.clear()
            page.add(get_page("LoginPage")(page))
            page.update()
            return
        self._page = page
        self.nav_parent = parent  # KantslerApp — чтобы вернуться на дашборд
        self.username = session_get(self._page, "username")

        # Кнопки основного меню
        self.search_button = ft.FilledButton("Поиск курсанта", width=300, on_click=self.go_to_search_page)
        self.kadri_button = ft.FilledButton("Кадровая работа", width=300, on_click=self.kadri_work_click)
        self.studi_button = ft.FilledButton("Учебная работа", width=300, on_click=self.studi_work_click)
        self.vpr_button = ft.FilledButton("Военно-политическая работа", width=300, on_click=self.vpr_click)
        self.premia_button = ft.FilledButton("Премии", width=300, on_click=self.premia_click)
        self.personal_file_button = ft.FilledButton("Личное дело", width=300, on_click=self.personal_file_click)
        self.logout_button = ft.FilledButton("Выход", width=150, on_click=self.logout_click)  # Уменьшаем ширину кнопки "Выход"

        if self.kadri_button is None:
            raise ValueError("Kadri button is null")
        if self.studi_button is None:
            raise ValueError("Studi button is null")
        if self.vpr_button is None:
            raise ValueError("Vpr button is null")

        # Основное меню в столбце
        main_menu = ft.Column(
            controls=[
                self.search_button,
                self.kadri_button,
                self.studi_button,
                self.vpr_button,
                self.premia_button,
                self.personal_file_button,
            ],
            alignment=ft.MainAxisAlignment.START,
            #horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Заголовок и кнопка "Выход" в строке
        header_row = ft.Row(
            controls=[
                ft.Text("Главное меню", size=20, weight="bold"),
                ft.OutlinedButton("Новый дашборд", icon=ft.Icons.SPACE_DASHBOARD_ROUNDED,
                                  on_click=self.back_to_dashboard) if parent else ft.Container(),
                ft.Container(expand=True),  # Растягиваемый контейнер для выравнивания кнопки "Выход" вправо
                self.logout_button,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,  # Распределяем элементы по краям
        )

        # Инициализация списка controls
        self.controls = [
            header_row,  # Строка с заголовком и кнопкой "Выход"
            main_menu,   # Основное меню
            ft.Divider() # Разделитель
        ]

        # Добавляем кнопки для администратора, если роль соответствует
        self.role = session_get(page, "role")
        if self.role == ADMIN_ROLE:
            self.users_button = ft.FilledButton("Пользователи", width=300, on_click=self.users_click)
            self.logs_button = ft.FilledButton("Журнал", width=300, on_click=self.logs_click)
            self.controls.extend([self.users_button, self.logs_button])
        
        self.controls.append(ft.Divider())

    # Обработчик нажатия кнопки "Поиск курсантов"
    def go_to_search_page(self, e):
        self._page.controls.clear()
        self._page.add(get_page("SearchPage")(self._page))
        self._page.update()

    # Обработчик нажатия кнопки "Кадровая работа"
    def kadri_work_click(self, e):
        if self._page:
            self._page.controls.clear()
            self._page.add(get_page("KadriWorkPage")(self._page))
            self._page.update()

    # Обработчик нажатия кнопки "Учебная работа"
    def studi_work_click(self, e):
        self._page.controls.clear()
        self._page.add(get_page("SessionResultsPage")(self._page))
        self._page.update()

    # Обработчик нажатия кнопки "Военно-политическая работа"
    def vpr_click(self, e):
        self._page.controls.clear()
        self._page.add(get_page("VprWorkPage")(self._page))
        self._page.update()

    # Обработчик нажатия кнопки "Премии"
    def premia_click(self, e):
        self._page.controls.clear()        
        self._page.add(get_page("PremiaWorkPage")(self._page))
        self._page.update()

    # Обработчик нажатия кнопки "Личное дело"
    def personal_file_click(self, e):
        self._page.controls.clear()
        self._page.add(get_page("PersonalFilePage")(self._page))
        self._page.update()

    def users_click(self, e):
        log_action(self.username, "Переход на страницу управления пользователями")
        self._page.controls.clear()
        self._page.add(get_page("UsersPage")(self._page))
        self._page.update()

    def logs_click(self, e):
        log_action(self.username, "Переход на страницу журнала")
        self._page.controls.clear()
        self._page.add(get_page("LogsPage")(self._page))
        self._page.update()
    
    # Обработчик для кнопки выхода
    def logout_click(self, e):
        log_action(self.username, "Выход из учетной записи")
        session_clear(self._page)  # Очищаем сессию
        self._page.controls.clear()
        self._page.add(get_page("LoginPage")(self._page))  # Возвращаемся на страницу входа
        self._page.update()

    # Если меню встроено в каркас — переход на новый дашборд
    def back_to_dashboard(self, e=None):
        if self.parent is not None:
            self.nav_parent.show_dashboard()
