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


from theme import BG, PRIMARY, TEXT_DARK, TEXT_MUTED


class KantslerApp(ft.Column):
    """Каркас приложения «Канцлер Про».

    Точка входа после авторизации: боковая панель навигации слева +
    область содержимого. Открывается информативный дашборд; все разделы
    (Kanzler + Дорожная карта MKR) доступны через боковое меню.
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
        # Flet 1.x: Column по умолчанию скроллируется (AutoScrollView) и даёт
        # детям неограниченную высоту — NavigationRail на этом падает с
        # ошибкой "height is unbounded". Отключаем скролл каркаса.
        self.scroll = None
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
        # Собственная панель навигации вместо ft.NavigationRail:
        #   1) NavigationRail в Flet 1.x падает с "height is unbounded"
        #      внутри скроллируемых обёрток страницы;
        #   2) при ошибке отрисовки rail показывает пустую белую полосу —
        #      именно её наблюдали пользователи ("широкая белая полоса").
        # Панель из обычных контролов работает при любой конфигурации.
        # Область содержимого — скроллируемый Row с stretch-выравниванием:
        # страница занимает всю высоту окна при коротком контенте и получает
        # вертикальный скролл при длинном (работает в Flet 1.x).
        self._page_holder = ft.Container(width=0, visible=False)
        self.content_area = ft.Row(
            [self._page_holder],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            alignment=ft.MainAxisAlignment.START,
        )
        self._nav_buttons = {}
        nav_children = [
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.SHIELD_ROUNDED, color=PRIMARY, size=30),
                    ft.Text("Канцлер Про", size=13, weight="bold",
                            color=TEXT_DARK, text_align="center"),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4),
                padding=ft.Padding(8, 16, 8, 12)),
        ]
        items = list(self.NAV_ITEMS)
        if self.role == ADMIN_ROLE:
            items += list(self.ADMIN_ITEMS)
        self._nav_names = []
        for name, label, icon in items:
            self._nav_names.append(name)
            btn = ft.Container(
                content=ft.Row([
                    ft.Icon(icon, size=20, color="#475569"),
                    ft.Text(label, size=13, color=TEXT_DARK,
                            no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                ], spacing=10,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(12, 9, 12, 9),
                border_radius=8,
                margin=ft.Margin(6, 2, 6, 2),
                ink=True,
                on_click=lambda e, n=name: self.go_to(n),
            )
            self._nav_buttons[name] = btn
            nav_children.append(btn)
        # Кнопки разделов — скроллируемый список; выход прижат к низу панели.
        self._nav_list = ft.ListView(nav_children[1:], spacing=1,
                                     height=690, expand=False)
        self.nav_panel = ft.Container(
            width=210,
            bgcolor="#ffffff",
            border=ft.Border(right=ft.BorderSide(1, "#e2e8f0")),
            content=ft.Column([
                nav_children[0],          # логотип
                self._nav_list,           # разделы (со скроллом)
                ft.Container(             # пользователь + выход внизу
                    content=ft.Row([
                        ft.IconButton(ft.Icons.LOGOUT, tooltip="Выход",
                                      on_click=self.logout_click),
                        ft.Text(str(self.username), size=12, color=TEXT_MUTED,
                                no_wrap=True),
                    ], spacing=4,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(10, 8, 8, 12)),
            ], spacing=1),
        )

        self.shell = ft.Row(
            [self.nav_panel, self.content_area],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.controls = [self.shell]
        self.show_dashboard()

    # ------------------------------------------------------------------
    # Навигация каркаса
    # ------------------------------------------------------------------
    def go_to(self, cls_name, keep_selection=None):
        """Открывает страницу внутри области содержимого (без перезагрузки page)."""
        page_cls = get_page(cls_name)
        try:
            view = page_cls(self._page, parent=self)
        except TypeError:
            view = page_cls(self._page)
        # Оборачиваем страницу в Container с фиксированной шириной, чтобы
        # она занимала всю ширину области содержимого (Row не поддерживает
        # expand дочерних контролов поперёк оси прокрутки).
        self._page_holder.content = view
        self._page_holder.width = max((self._page.width or 1200) - 250, 600)
        self._page_holder.visible = True
        # Подсветка активного пункта бокового меню
        for n, btn in self._nav_buttons.items():
            active = (n == cls_name)
            btn.bgcolor = "rgba(59,130,246,0.12)" if active else None
            try:
                row = btn.content
                row.controls[0].color = PRIMARY if active else "#475569"
                row.controls[1].weight = "bold" if active else None
                row.controls[1].color = PRIMARY if active else TEXT_DARK
            except Exception:
                pass
        self._page.update()

    def show_dashboard(self):
        self.go_to("DashboardPage", keep_selection=0)

    def show_legacy_menu(self):
        """Совместимость: старое меню убрано — открываем дашборд."""
        self.show_dashboard()

    def logout_click(self, e=None):
        log_action(self.username, "Выход из учетной записи")
        session_clear(self._page)
        self._page.controls.clear()
        self._page.add(get_page("LoginPage")(self._page))
        self._page.update()
