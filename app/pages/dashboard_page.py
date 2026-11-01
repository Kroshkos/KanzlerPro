"""Дашборд «Канцлер Про» — главная страница после входа.

Информационная панель: ключевые показатели (курсанты, достижения, экспертные
решения, баллы), топ студентов Дорожной карты, разрез по блокам и последние
действия из журнала. Заменяет собой старое кнопочное меню Канцлера, оставаясь
точкой входа во все модули.
"""

from datetime import datetime

import flet as ft
from authz import is_admin
from database import get_logs, get_roadmap_stats
from theme import (
    BG,
    INFO,
    PRIMARY,
    SUCCESS,
    TEXT_DARK,
    TEXT_MUTED,
    VIOLET,
    WARNING,
    card,
    section_title,
    stat_card,
)
from utils import session_get


def _wrap(page_obj, control):
    """Обёртка страницы: скролл + фон + отступы."""
    return ft.Container(
        content=ft.Column([control], scroll=ft.ScrollMode.AUTO, expand=True),
        bgcolor=BG,
        padding=24,
        expand=True,
    )


class DashboardPage(ft.Column):
    def __init__(self, page_obj, parent=None):
        super().__init__()
        self._page = page_obj
        self.nav_parent = parent  # KantslerApp (для встраивания во вкладку)
        username = session_get(page_obj, "username") or "гость"
        role = session_get(page_obj, "role") or ""

        stats = get_roadmap_stats()

        # ---------- Шапка ----------
        header = ft.Row(
            controls=[
                ft.Column([
                    ft.Text(f"Добро пожаловать, {username}", size=24,
                            weight="bold", color=TEXT_DARK),
                    ft.Text(f"Роль: {role} · Сегодня: "
                            + datetime.now().strftime("%d.%m.%Y"),
                            size=13, color=TEXT_MUTED),
                ], spacing=2),
                ft.Container(expand=True),
                ft.FilledButton("Обновить", icon=ft.Icons.REFRESH_ROUNDED,
                                on_click=self.refresh),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # ---------- Показатели ----------
        kpis = ft.Row(
            wrap=True,
            run_spacing=16,
            spacing=16,
            controls=[
                stat_card("Курсантов на учёте", stats["students"],
                          ft.Icons.GROUP_ROUNDED, PRIMARY),
                stat_card("Достижений в справочнике", stats["achievements"],
                          ft.Icons.CELL_TOWER_ROUNDED, VIOLET),
                stat_card("Экспертных решений", stats["total"],
                          ft.Icons.ASSESSMENT_ROUNDED, INFO,
                          subtitle=f"одобрено: {stats['approved']} · "
                                   f"отклонено: {stats['rejected']}"),
                stat_card("На рассмотрении", stats["pending"],
                          ft.Icons.PENDING_ROUNDED, WARNING),
                stat_card("Начислено баллов", stats["points"],
                          ft.Icons.STAR_ROUNDED, SUCCESS),
            ],
        )

        # ---------- Быстрые действия ----------
        quick = ft.Row(
            wrap=True,
            spacing=10,
            run_spacing=10,
            controls=[
                ft.FilledButton("Поиск курсанта", icon=ft.Icons.SEARCH,
                                on_click=lambda e: self.open("SearchPage")),
                ft.FilledButton("Кадровая работа", icon=ft.Icons.BADGE,
                                on_click=lambda e: self.open("KadriWorkPage")),
                ft.FilledButton("Учебная работа", icon=ft.Icons.SCHOOL,
                                on_click=lambda e: self.open("SessionResultsPage")),
                ft.FilledButton("ВПР: поощрения/взыскания", icon=ft.Icons.SHIELD,
                                on_click=lambda e: self.open("VprWorkPage")),
                ft.FilledButton("Премии", icon=ft.Icons.WALLET,
                                on_click=lambda e: self.open("PremiaWorkPage")),
                ft.FilledButton("Справочник достижений", icon=ft.Icons.CELL_TOWER,
                                on_click=lambda e: self.open("RoadmapCatalogPage")),
                ft.FilledButton("Экспертиза Road Map", icon=ft.Icons.VERIFIED,
                                on_click=lambda e: self.open("RoadmapExpertPage")),
                ft.FilledButton("ИПР курсанта", icon=ft.Icons.EVENT_NOTE,
                                on_click=lambda e: self.open("RoadmapIprPage")),
            ],
        )
        if is_admin(page_obj):  # раньше сравнивалось с литералом "Администратор"
            quick.controls.extend([
                ft.FilledButton("Пользователи", icon=ft.Icons.PERSON_ADD_ALT,
                                on_click=lambda e: self.open("UsersPage")),
                ft.FilledButton("Журнал действий", icon=ft.Icons.HISTORY,
                                on_click=lambda e: self.open("LogsPage")),
            ])

        # ---------- Топ студентов ----------
        top_rows = []
        if stats["top"]:
            for i, r in enumerate(stats["top"], 1):
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, str(i))
                fio = f"{r['o_surname']} {r['o_name']} " \
                      f"({r['o_group_name'] or '—'})"
                top_rows.append(ft.Row([
                    ft.Text(medal, width=32),
                    ft.Text(fio, expand=True, size=14, color=TEXT_DARK),
                    ft.Text(str(r["pts"] or 0), size=14, weight="bold", color=SUCCESS),
                ]))
        else:
            top_rows.append(ft.Text("Пока нет одобренных достижений — "
                                   "заполните справочник и проведите экспертизу.",
                                   color=TEXT_MUTED, italic=True))
        top_card = card(ft.Column(
            [section_title("Топ-10 по баллам Дорожной карты"), *top_rows],
            spacing=8), expand=True)

        # ---------- Разрез по блокам ----------
        block_rows = []
        max_pts = max(((r["pts"] or 0) for r in stats["by_block"]), default=0) or 1
        from database import BLOCK_NAMES
        for r in stats["by_block"]:
            name = BLOCK_NAMES.get(r["block"], f"Блок {r['block']}")
            frac = (r["pts"] or 0) / max_pts
            block_rows.append(ft.Column([
                ft.Row([ft.Text(name, size=12, color=TEXT_DARK, expand=True),
                        ft.Text(str(r["pts"] or 0), size=12, weight="bold",
                                color=PRIMARY)]),
                ft.ProgressBar(value=frac, color=PRIMARY, bgcolor="#e2e8f0",
                               bar_height=8),
            ], spacing=2))
        if not block_rows:
            block_rows.append(ft.Text("Нет данных: одобрённые решения появятся "
                                      "после экспертизы.", color=TEXT_MUTED, italic=True))
        blocks_card = card(ft.Column(
            [section_title("Баллы по блокам достижений"), *block_rows],
            spacing=12), expand=True)

        # ---------- Журнал ----------
        log_rows = []
        for row in (get_logs() or [])[:8]:
            log_rows.append(ft.Row([
                ft.Text(row["timestamp"], size=11, color=TEXT_MUTED, width=150),
                ft.Text(row["username"], size=12, weight="bold", color=TEXT_DARK,
                        width=120),
                ft.Text(row["action"], size=12, color=TEXT_DARK, expand=True),
            ]))
        if not log_rows:
            log_rows.append(ft.Text("Журнал пуст.", color=TEXT_MUTED, italic=True))
        logs_card = card(ft.Column(
            [section_title("Последние действия"), *log_rows], spacing=6),
            expand=True)

        charts = ft.Row([top_card, blocks_card], spacing=16,
                        vertical_alignment=ft.CrossAxisAlignment.START)
        bottom = ft.Row([logs_card], spacing=16)

        menu_row = ft.Row([
            ft.Text("Модуль «Личные дела и учёт»", size=16, weight="bold",
                    color=TEXT_DARK),
        ])

        self.body = ft.Column([
            header,
            ft.Column([menu_row, quick], spacing=12),
            kpis,
            charts,
            bottom,
        ], spacing=20, expand=True, scroll=ft.ScrollMode.AUTO)

        self.controls = [_wrap(page_obj, self.body)] if parent is None else [self.body]

    # ------------------------------------------------------------------
    def open(self, cls_name):
        if self.nav_parent is not None:
            self.nav_parent.go_to(cls_name)
        elif cls_name:
            from theme import navigate
            navigate(self._page, cls_name)

    def refresh(self, e):
        if self.nav_parent is not None:
            self.nav_parent.show_dashboard()
        else:
            from theme import navigate
            navigate(self._page, "DashboardPage")
