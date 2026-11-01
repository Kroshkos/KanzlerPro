"""Каркас приложения «Канцлер Про» — точка входа после авторизации.

Современный полноэкранный интерфейс:
  * адаптивная боковая панель навигации (сворачивается в компактную на
    узких экранах, скрывается на мобильных);
  * верхняя шапка с названием текущего раздела и учётной записью;
  * область содержимого с фиксированными размерами — страницы больше не
    бывают пустыми из-за "unbounded height";
  * все межстраничные переходы идут через pages.shell, поэтому боковое
    меню остаётся видимым на каждом экране.

База данных заполняется заново; данные между разделами связываются через
общую таблицу students (наследие Kanzler + Дорожная карта MKR).
"""

import flet as ft

from pages.registry import get_page
from pages import shell
from theme import BG, PRIMARY, TEXT_DARK, TEXT_MUTED
from utils import session_get, session_clear, to_num
from database import log_action


class KantslerApp(ft.Column):
    """Навигационный каркас: панель слева + контент справа."""

    #: Пункты меню: (ключ, класс страницы, подпись, иконка)
    NAV_ITEMS = [
        ("dashboard", "DashboardPage", "Дашборд", ft.Icons.SPACE_DASHBOARD_ROUNDED),
        ("search", "SearchPage", "Поиск курсанта", ft.Icons.SEARCH),
        ("kadri", "KadriWorkPage", "Кадровая работа", ft.Icons.BADGE),
        ("study", "SessionResultsPage", "Учебная работа", ft.Icons.SCHOOL),
        ("vpr", "VprWorkPage", "ВПР", ft.Icons.SHIELD),
        ("premia", "PremiaWorkPage", "Премии", ft.Icons.WALLET),
        ("files", "PersonalFilePage", "Личное дело", ft.Icons.FOLDER_SPECIAL),
        ("catalog", "RoadmapCatalogPage", "Достижения Road Map", ft.Icons.CELL_TOWER),
        ("expert", "RoadmapExpertPage", "Экспертиза", ft.Icons.VERIFIED),
        ("ipr", "RoadmapIprPage", "ИПР курсанта", ft.Icons.EVENT_NOTE),
        ("rating", "RoadmapRatingPage", "Рейтинг Road Map", ft.Icons.EMOJI_EVENTS),
        ("reports", "RoadmapReportsPage", "Отчётные формы", ft.Icons.PRINT),
    ]
    ADMIN_ITEMS = [
        ("users", "UsersPage", "Пользователи", ft.Icons.PERSON_ADD_ALT),
        ("logs", "LogsPage", "Журнал действий", ft.Icons.HISTORY),
    ]

    WIDTH_SIDEBAR = 250      # полная панель (>= 1400 px)
    WIDTH_COMPACT = 76       # иконки (900..1400 px)
    CONTENT_PADDING = 28     # отступы области контента

    def __init__(self, page):
        super().__init__()
        if page is None:
            raise ValueError("Page is null")

        # Защита от прямого входа без авторизации
        if not session_get(page, "username"):
            page.controls.clear()
            page.add(get_page("LoginPage")(page))
            page.update()
            return

        self._fpage = page
        self.username = session_get(page, "username")
        self.role = session_get(page, "role")
        self._active_key = None
        self._title_ref = None
        self._subtitle_ref = None

        # ---------- Область содержимого ----------
        # Контент оборачивается в Column со скроллом: страница занимает всю
        # высоту окна, длинный контент прокручивается. Ширина выставляется
        # явно при ресайзе (Flet 1.x не даёт Row растягивать детей поперёк
        # оси прокрутки — именно из-за этого страницы раньше пустовали).
        self._content_col = ft.Column(
            [], scroll=ft.ScrollMode.AUTO, width=self._content_width(),
        )
        self.content_area = ft.Container(
            content=self._content_col,
            expand=True,
            bgcolor=BG,
            alignment=ft.Alignment(-1, -1),
            padding=ft.Padding(self.CONTENT_PADDING, 18,
                               self.CONTENT_PADDING, 18),
        )

        # ---------- Верхняя шапка ----------
        self._title_ref = ft.Text("Дашборд", size=18, weight="bold",
                                  color=TEXT_DARK)
        self._subtitle_ref = ft.Text("", size=12, color=TEXT_MUTED)
        header = ft.Container(
            content=ft.Row([
                ft.IconButton(ft.Icons.MENU_ROUNDED, icon_color=TEXT_DARK,
                              tooltip="Показать/скрыть меню",
                              on_click=self.toggle_sidebar),
                ft.Column([self._title_ref, self._subtitle_ref], spacing=2),
                ft.Container(expand=True),
                ft.CircleAvatar(
                    content=ft.Text(str(self.username)[:1].upper(),
                                    color="#ffffff", weight="bold"),
                    radius=16, bgcolor=PRIMARY),
                ft.Text(str(self.username), size=13, color=TEXT_DARK),
                ft.IconButton(ft.Icons.LOGOUT_ROUNDED, icon_color="#64748b",
                              tooltip="Выйти", on_click=self.logout_click),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor="#ffffff",
            padding=ft.Padding(10, 6, 16, 6),
            border=ft.Border(bottom=ft.BorderSide(1, "#e2e8f0")),
        )

        # ---------- Боковая панель ----------
        self.nav_panel = ft.Container(width=self.WIDTH_COMPACT,
                                      bgcolor="#ffffff", border_radius=0)
        self._build_nav()

        right_side = ft.Column([header, self.content_area], spacing=0,
                               expand=True)
        self.shell = ft.Row([self.nav_panel, right_side], spacing=0,
                            expand=True,
                            vertical_alignment=ft.CrossAxisAlignment.STRETCH)

        self.scroll = None
        self.expand = True
        self.controls = [self.shell]

        # Регистрация каркаса: страницы через pages.shell будут открываться
        # внутри области содержимого, а не заменять всю страницу.
        shell.set_shell(self)

        # Реакция на изменение размера окна (fullscreen / restore)
        try:
            self._fpage.on_resize = self._on_resize
        except Exception:
            pass

        self.show_dashboard()

    # ------------------------------------------------------------------
    # Размеры / адаптивность
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Безопасные преобразования размеров.
    # В Flet 1.x значения ширины/высоты могут приходить из протокола как
    # строки — прямое сравнение str с числом падает с ошибкой
    # "'<=' not supported between instances of 'str' and 'float'".
    # ------------------------------------------------------------------
    @staticmethod
    def _num(value, default=None):
        # общий хелпер из app/utils.py (to_num) — единая реализация на весь проект
        return to_num(value, default)

    def _page_width(self):
        # Приоритет: актуальные метрики страницы (заполняет рантайм Flet),
        # затем последнее событие ресайза, затем дефолт. Все значения
        # приводятся к числу — из протокола они могут прийти строкой.
        w = to_num(getattr(self._fpage, "width", None), None)
        if w is not None and w > 0:
            return int(w)
        w = getattr(self, "_last_width", None)
        if w:
            return int(w)
        return 1200

    def _sidebar_mode(self):
        w = self._page_width()
        if w >= 1400:
            return "full"
        if w >= 900:
            return "compact"
        return "hidden"

    def _panel_width(self):
        mode = self._sidebar_mode()
        if mode == "full":
            return self.WIDTH_SIDEBAR
        if mode == "compact":
            return self.WIDTH_COMPACT
        return 0

    def _content_width(self):
        w = self._page_width()
        return max(w - self._panel_width() - 2, 320)

    def _apply_layout(self):
        """Пересчитывает ширину панели и области контента (все числа — int)."""
        pw = self._panel_width()
        changed = False
        if pw != self.nav_panel.width:
            self.nav_panel.width = int(pw)
            self._build_nav()
            changed = True
        cw = self._content_width()
        if cw != self._content_col.width:
            self._content_col.width = int(cw)
            changed = True
        return changed

    def _on_resize(self, e):
        # ВАЖНО: page.width/page.height в Flet 1.x — read-only поля, их
        # заполняет рантайм. Присваивать им нельзя (в том числе значения из
        # события ресайза). Ширина окна для адаптивной раскладки берётся из
        # метрик страницы; если они ещё не получены — из события (тоже с
        # безопасным приведением строки к числу).
        try:
            pw = to_num(getattr(e, "width", None), None)
            if pw is not None and pw > 0:
                self._last_width = float(pw)
            ph = to_num(getattr(e, "height", None), None)
            if ph is not None and ph > 0:
                self._last_height = float(ph)
        except Exception:
            pass
        if self._apply_layout():
            self._fpage.update()

    def toggle_sidebar(self, e=None):
        """Переключение полной/компактной панели (мобильный — скрытие)."""
        mode = self._sidebar_mode()
        if mode == "full":
            self._forced = "compact"
        elif mode == "compact":
            self._forced = "full"
        else:
            self._forced = "compact"
        if self._apply_layout():
            self._fpage.update()

    # ------------------------------------------------------------------
    # Построение панели навигации
    # ------------------------------------------------------------------
    def _build_nav(self):
        panel_w = int(self._num(self.nav_panel.width, self.WIDTH_COMPACT))
        compact = panel_w <= 100
        items = list(self.NAV_ITEMS)
        if self.role == "admin":
            items += list(self.ADMIN_ITEMS)

        logo_children = [ft.Icon(ft.Icons.SHIELD_ROUNDED, color=PRIMARY,
                                 size=28)]
        if not compact:
            logo_children.append(ft.Text("Канцлер Про", size=15,
                                         weight="bold", color=TEXT_DARK))
        children = [
            ft.Container(
                content=ft.Row(logo_children, spacing=10,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(14, 16, 14, 12)),
        ]
        self._nav_buttons = {}
        for key, cls_name, label, icon in items:
            row_children = [ft.Icon(icon, size=22, color="#475569")]
            if not compact:
                row_children.append(
                    ft.Text(label, size=13.5, color=TEXT_DARK, no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS))
            active = (key == self._active_key)
            btn = ft.Container(
                content=ft.Row(row_children, spacing=12,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(14, 10, 14, 10),
                border_radius=10,
                margin=ft.Margin(8, 1, 8, 1),
                ink=True,
                tooltip=label,
                on_click=lambda e, k=key, c=cls_name, l=label: self.go_to(c, key=k, title=l),
            )
            if active:
                btn.bgcolor = "rgba(59,130,246,0.12)"
                first = btn.content.controls[0]
                last = btn.content.controls[-1]
                # ВАЖНО: у ft.Icon поле weight — числовое (вес шрифта),
                # строка "bold" роняет валидатор Flet 1.x с ошибкой
                # "'<=' not supported between instances of 'str' and 'float'".
                # Жирность задаём только текстовым элементам.
                if isinstance(first, ft.Icon):
                    first.color = PRIMARY
                if isinstance(last, ft.Text):
                    last.weight = "bold"
                    last.color = PRIMARY
            self._nav_buttons[key] = btn
            children.append(btn)

        footer_children = []
        if compact:
            footer_children = [ft.IconButton(
                ft.Icons.LOGOUT_ROUNDED, icon_color="#64748b",
                tooltip="Выйти", on_click=self.logout_click)]
        else:
            footer_children = [
                ft.Text(str(self.username), size=12, color=TEXT_MUTED,
                        no_wrap=True),
                ft.Text(f"Роль: {self.role}", size=11, color=TEXT_MUTED),
            ]
        children.append(ft.Container(
            content=ft.Row(footer_children, spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(12, 10, 8, 14)))

        self.nav_panel.content = ft.Column(children, spacing=1)

    # ------------------------------------------------------------------
    # Навигация
    # ------------------------------------------------------------------
    def go_to(self, cls_name, *extra, keep_selection=None, key=None, title=None,
              view=None):
        """Открывает страницу внутри области содержимого (меню сохраняется)."""
        if view is None:
            page_cls = get_page(cls_name)
            try:
                view = page_cls(self._fpage, *extra, parent=self)
            except TypeError:
                view = page_cls(self._fpage, *extra)

        # Контейнер с фиксированной шириной и автоскроллом — страницы
        # гарантированно получают ограниченные размеры (нет пустых экранов).
        col_w = int(self._num(self._content_col.width, 1200))
        holder = ft.Container(
            content=view,
            width=max(col_w - self.CONTENT_PADDING * 2, 320),
            bgcolor=BG,
        )
        self._content_col.controls = [holder]

        # Подсветка активного пункта и заголовок шапки
        active_key = key
        if active_key is None:
            for k, cn, lbl, ic in list(self.NAV_ITEMS) + list(self.ADMIN_ITEMS):
                if cn == cls_name:
                    active_key, title = k, lbl
                    break
        self._active_key = active_key
        if title:
            self._title_ref.value = title
            self._subtitle_ref.value = ""
        self._build_nav()
        self._fpage.update()

    def open_standalone(self, cls_name, view):
        """Открывает произвольный контрол внутри каркаса (для кнопок
        «Добавить курсанта», «Редактировать» и т.п.). Меню остаётся."""
        self.go_to(cls_name, view=view,
                   title=self._subpage_title(cls_name))

    @staticmethod
    def _subpage_title(cls_name):
        TITLES = {
            "AddStudentPage": "Новый курсант",
            "ShowStudentsPage": "Список курсантов",
            "EditStudentPage": "Редактирование курсанта",
            "PositionChangePage": "Изменение должности",
            "RankChangePage": "Изменение звания",
            "EncouragementWorkPage": "Поощрения",
            "PenaltyWorkPage": "Взыскания",
            "StudiWorkPage": "Учебная работа",
            "KadriWorkPage": "Кадровая работа",
            "VprWorkPage": "ВПР",
        }
        return TITLES.get(cls_name, cls_name)

    def show_dashboard(self):
        self.go_to("DashboardPage", key="dashboard", title="Дашборд")

    def show_legacy_menu(self):
        """Совместимость: старое меню убрано — открываем дашборд."""
        self.show_dashboard()

    def logout_click(self, e=None):
        log_action(self.username, "Выход из учетной записи")
        session_clear(self._fpage)
        shell.set_shell(None)
        self._fpage.controls.clear()
        self._fpage.add(get_page("LoginPage")(self._fpage))
        self._fpage.update()
