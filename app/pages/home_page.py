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
from authz import ADMIN_ONLY_PAGES, is_admin, require_admin
from database import log_action
from theme import BG, PRIMARY, TEXT_DARK, TEXT_MUTED
from utils import session_clear, session_get, to_int, to_num
from utils_logger import log_except

from pages import shell
from pages.registry import get_page


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
        # Глобальный поиск: курсанты / заявки Road Map / достижения
        self._search_field = ft.TextField(
            hint_text="Поиск: фамилия, группа, заявка…",
            width=300, dense=True, border_radius=999,
            prefix_icon=ft.Icons.SEARCH,
            on_submit=self.global_search_click)
        # ---------- Колокольчик уведомлений: новые заявки на экспертизу ----
        self._notif_btn = ft.IconButton(
            ft.Icons.NOTIFICATIONS_NONE, icon_color="#64748b",
            tooltip="Уведомления: новые заявки на экспертизу",
            on_click=self.notifications_click)
        self._notif_badge = ft.Container(
            content=ft.Text("0", size=9, color="#ffffff", weight="bold"),
            bgcolor="#ef4444", border_radius=999,
            padding=ft.Padding(4, 1, 4, 1), visible=False)
        self._notif_stack = ft.Stack([self._notif_btn, self._notif_badge],
                                     width=40, height=40)

        header = ft.Container(
            content=ft.Row([
                ft.IconButton(ft.Icons.MENU_ROUNDED, icon_color=TEXT_DARK,
                              tooltip="Показать/скрыть меню",
                              on_click=self.toggle_sidebar),
                ft.Column([self._title_ref, self._subtitle_ref], spacing=2),
                ft.Container(expand=True),
                self._search_field,
                ft.IconButton(ft.Icons.SEARCH, icon_color=PRIMARY,
                              tooltip="Глобальный поиск",
                              on_click=self.global_search_click),
                # Колокольчик уведомлений (собирается до header в _build_notifications)
                self._notif_stack,
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
            log_except("home_page: блок на строке 159")

        self.refresh_notifications()
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
            log_except("home_page: блок на строке 238")
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
        if is_admin(self._fpage):
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
            # Серверная (в терминах приложения) проверка прав: скрыть пункт
            # меню недостаточно — страницу можно открыть из уведомлений или
            # вызвав go_to напрямую. Для закрытых классов подставляем
            # заглушку вместо реальной страницы.
            denied = (require_admin(self._fpage)
                      if cls_name in ADMIN_ONLY_PAGES else None)
            if denied is not None:
                view = denied
            else:
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
        try:
            self.refresh_notifications()
        except Exception:
            log_except("home_page: блок на строке 374")
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

    def global_search_click(self, e=None):
        """Глобальный поиск из шапки: курсанты + заявки Road Map + каталог."""
        query = str(getattr(self._search_field, "value", "") or "").strip()
        if len(query) < 2:
            from utils import show_snack
            show_snack(self._fpage, "Введите не менее 2 символов для поиска.")
            return
        try:
            view = get_page("SearchResultsPage")(self._fpage, query,
                                                 parent=self)
        except TypeError:
            view = get_page("SearchResultsPage")(self._fpage, query)
        self.go_to("SearchResultsPage", view=view, key=None,
                   title=f"Поиск: {query}")

    # ------------------------------------------------------------------
    # Уведомления о новых заявках на экспертизу (колокольчик в шапке)
    # ------------------------------------------------------------------
    def refresh_notifications(self):
        """Пересчитывает счётчик заявок 'на рассмотрении' на бейдже."""
        try:
            from database import count_pending_reviews
            pending = int(count_pending_reviews())
        except Exception:
            pending = 0
        self._pending_reviews_count = pending
        self._notif_badge.content.value = str(pending if pending < 100 else "99+")
        self._notif_badge.visible = pending > 0
        self._notif_btn.icon = (ft.Icons.NOTIFICATIONS_ACTIVE if pending > 0
                                else ft.Icons.NOTIFICATIONS_NONE)
        self._notif_btn.tooltip = (
            f"Уведомления: новых заявок на экспертизу — {pending}"
            if pending else "Новых заявок на экспертизу нет")

    def notifications_click(self, e=None):
        """Показывает панель последних неотработанных заявок."""
        try:
            from database import get_recent_pending_reviews
            rows = get_recent_pending_reviews(limit=15) or []
        except Exception:
            log_except("home_page: загрузка уведомлений")
            rows = []
        items = []
        if not rows:
            items.append(ft.Container(
                padding=14,
                content=ft.Text("Новых заявок на экспертизу нет ✨",
                                size=13, color=TEXT_MUTED)))

        # Вспомогательная функция вне цикла: раньше _g определялась внутри
        # цикла и ссылалась на переменную r из замыкания (B023) — при
        # отложенном вызове все строки читались бы по последней итерации.
        def _g(row, k):
            try:
                v = row[k]
            except Exception:
                v = None
            return str(v).strip() if v not in (None, "") else "—"

        for r in rows:
            fio = " ".join(x for x in [_g(r, "o_surname"), _g(r, "o_name"),
                                       _g(r, "o_lastname")] if x != "—") or "—"
            sem = to_int(_g(r, "semester"))
            items.append(
                ft.Container(
                    ink=True,
                    padding=ft.Padding(12, 8, 12, 8),
                    border=ft.Border(bottom=ft.BorderSide(1, "#f1f5f9")),
                    content=ft.Row([
                        ft.Icon(ft.Icons.FORWARD_TO_INBOX, size=18,
                                color="#f59e0b"),
                        ft.Column([
                            ft.Text(fio, size=13, weight="bold",
                                    color=TEXT_DARK, no_wrap=True),
                            ft.Text(f"{_g(r, 'name')}"
                                    + (f" · семестр {sem}" if sem else ""),
                                    size=11.5, color=TEXT_MUTED,
                                    no_wrap=True,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                        ], spacing=2, expand=True),
                    ]),
                    on_click=lambda ev, sid=to_int(_g(r, "student_id")):
                        self.open_expert_for_student(sid),
                ))
        panel = ft.Container(
            width=360,
            bgcolor="#ffffff",
            border=ft.Border.all(1, "#e2e8f0"),
            border_radius=12,
            shadow=ft.BoxShadow(blur_radius=18, color="#1f000000",
                                 offset=ft.Offset(0, 6)),
            content=ft.Column([
                ft.Container(
                    padding=ft.Padding(14, 12, 14, 10),
                    border=ft.Border(bottom=ft.BorderSide(1, "#e2e8f0")),
                    content=ft.Row([
                        ft.Text("Уведомления", size=15, weight="bold",
                                color=TEXT_DARK, expand=True),
                        ft.IconButton(ft.Icons.CLOSE, icon_size=16,
                                      icon_color="#64748b",
                                      on_click=self.close_notifications),
                    ])),
                ft.Column(items, spacing=0, scroll=ft.ScrollMode.AUTO,
                          height=min(430, 62 * max(len(items), 1) + 8)),
                ft.Container(
                    padding=ft.Padding(14, 8, 14, 12),
                    content=ft.FilledButton(
                        "Открыть все заявки", icon=ft.Icons.VERIFIED,
                        on_click=lambda ev: self.go_to(
                            "RoadmapExpertPage", key="expert",
                            title="Экспертиза Road Map")),
                ),
            ], spacing=0))
        self._notif_overlay = ft.Container(
            content=panel, right=110, top=52,
            bgcolor="#00000000")
        # закрытие по клику мимо панели
        closer = ft.GestureDetector(
            on_tap=self.close_notifications,
            content=ft.Container(bgcolor="#00000022"))
        self._notif_overlay = ft.Stack([closer, panel])
        try:
            self._notif_overlay.expand = True
            closer.expand = True
        except Exception:
            log_except("home_page: блок на строке 521")
        holder = getattr(self, "_notif_holder", None)
        if holder is None:
            holder = ft.Container(visible=False, left=0, top=0, right=0, bottom=0,
                               expand=True)
            try:
                self._fpage.overlay.append(holder)
            except Exception:
                log_except("home_page: блок на строке 529")
            self._notif_holder = holder
        holder.content = self._notif_overlay
        holder.visible = True
        holder.update()

    def open_expert_for_student(self, student_id):
        """Из уведомления — сразу к курсанту на страницу Экспертизы."""
        self.close_notifications()
        self.go_to("RoadmapExpertPage", key="expert", title="Экспертиза",
                   keep_selection=student_id)

    def close_notifications(self, e=None):
        holder = getattr(self, "_notif_holder", None)
        if holder is not None:
            holder.visible = False
            try:
                holder.update()
            except Exception:
                log_except("home_page: блок на строке 548")

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
