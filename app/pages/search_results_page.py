"""Страница результатов глобального поиска (запуск из шапки каркаса).

Показывает найденные курсантов, заявки экспертизы, достижения каталога,
дисциплинарные записи и результаты сессий. Из каждой карточки — быстрый
переход в соответствующий раздел (личное дело / экспертиза / каталог).
"""

import flet as ft
from database import log_action
from global_search import global_search, total_found
from theme import DANGER, PRIMARY, SUCCESS, TEXT_DARK, TEXT_MUTED, WARNING, card
from utils_logger import log_except

from pages import shell

REVIEW_STATUS = {
    "pending": ("На рассмотрении", WARNING),
    "approved": ("Одобрено", SUCCESS),
    "rejected": ("Отклонено", DANGER),
}


class SearchResultsPage(ft.Column):
    def __init__(self, page_obj, query="", parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO, spacing=14)
        self._page = page_obj
        self.nav_parent = parent
        self.query = str(query or "").strip()

        header = ft.Row([
            ft.Icon(ft.Icons.SEARCH, color=PRIMARY, size=26),
            ft.Text(f"Глобальный поиск: «{self.query}»",
                    size=20, weight="bold", color=TEXT_DARK),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self.refine_field = ft.TextField(
            value=self.query, width=340, dense=True,
            border_radius=10, hint_text="Уточнить запрос…",
            on_submit=self._refine)
        refine_btn = ft.FilledButton("Искать", icon=ft.Icons.SEARCH,
                                     on_click=self._refine)

        self.results_area = ft.Column(spacing=12)
        self.controls = [
            ft.Row([header, ft.Container(expand=True),
                    self.refine_field, refine_btn],
                   spacing=10,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self.results_area,
        ]
        self._render()

    # ------------------------------------------------------------------
    def _refine(self, e=None):
        self.query = str(self.refine_field.value or "").strip()
        self._render()
        try:
            self._page.update()
        except Exception:
            log_except("search_results_page: блок на строке 60")

    def _open_student(self, student_id):
        """Переход в личное дело найденного курсанта."""
        if self.nav_parent is not None and hasattr(self.nav_parent, "go_to"):
            self.nav_parent.go_to("PersonalFilePage", student_id,
                                  key="files", title="Личное дело")
        else:
            shell.navigate(self._page, "PersonalFilePage", student_id)

    def _goto(self, cls_name, key, title):
        if self.nav_parent is not None and hasattr(self.nav_parent, "go_to"):
            self.nav_parent.go_to(cls_name, key=key, title=title)
        else:
            shell.navigate(self._page, cls_name)

    # ------------------------------------------------------------------
    def _section(self, title, icon, count, rows, empty_hint):
        if count == 0:
            return None
        body = ft.Column(rows, spacing=6)
        return card(
            ft.Column([
                ft.Row([ft.Icon(icon, size=20, color=PRIMARY),
                        ft.Text(f"{title} ({count})", size=15,
                                weight="bold", color=TEXT_DARK)],
                       spacing=8),
                body,
            ], spacing=8), expand=False)

    def _render(self):
        self.results_area.controls = []
        if len(self.query) < 2:
            self.results_area.controls.append(card(ft.Text(
                "Введите не менее 2 символов для поиска.",
                color=TEXT_MUTED)))
            return

        res = global_search(self.query)
        total = total_found(res)
        if total == 0:
            self.results_area.controls.append(card(ft.Row([
                ft.Icon(ft.Icons.SEARCH_OFF_ROUNDED, color=TEXT_MUTED),
                ft.Text(f"По запросу «{self.query}» ничего не найдено.",
                        color=TEXT_MUTED),
            ], spacing=8)))
            return

        students = res["students"]
        if students:
            rows = []
            for s in students:
                full = " ".join(x for x in
                                [s["o_surname"], s["o_name"], s["o_lastname"]]
                                if x)
                rows.append(ft.Container(
                    content=ft.Row([
                        ft.CircleAvatar(content=ft.Text(full[:1].upper()),
                                        radius=14, bgcolor=PRIMARY),
                        ft.Column([
                            ft.Text(full, size=13.5, weight="bold",
                                    color=TEXT_DARK),
                            ft.Text(f"группа {s['o_group_name']} · "
                                    f"{s['o_course']}-й курс · ID {s['id']}",
                                    size=11.5, color=TEXT_MUTED),
                        ], spacing=1, expand=True),
                        ft.TextButton("Личное дело", icon=ft.Icons.OPEN_IN_NEW,
                                      on_click=lambda e, sid=s["id"]:
                                      self._open_student(sid)),
                    ], spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(10, 6, 10, 6),
                    border_radius=10, bgcolor="#f8fafc"))
            sec = self._section("Курсанты", ft.Icons.PERSON, len(students),
                                rows, "")
            if sec:
                self.results_area.controls.append(sec)

        reviews = res["reviews"]
        if reviews:
            rows = []
            for r in reviews:
                label, color = REVIEW_STATUS.get(
                    r["status"], (str(r["status"]), TEXT_MUTED))
                full = " ".join(x for x in
                                [r["o_surname"], r["o_name"], r["o_lastname"]]
                                if x)
                ach = r["achievement_name"] or "Достижение не указано"
                rows.append(ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.VERIFIED, size=18, color=color),
                        ft.Column([
                            ft.Text(ach, size=13, weight="bold",
                                    color=TEXT_DARK),
                            ft.Text(f"заявка №{r['review_id']} · {full}"
                                    f" · семестр {r['semester'] or '—'}"
                                    f" · {r['final_points'] or 0} б.",
                                    size=11.5, color=TEXT_MUTED),
                        ], spacing=1, expand=True),
                        ft.Container(
                            content=ft.Text(label, size=11, color="#ffffff"),
                            bgcolor=color, border_radius=999,
                            padding=ft.Padding(10, 3, 10, 3)),
                        ft.TextButton("Экспертиза",
                                      on_click=lambda e: self._goto(
                                          "RoadmapExpertPage", "expert",
                                          "Экспертиза")),
                    ], spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(10, 6, 10, 6),
                    border_radius=10, bgcolor="#f8fafc"))
            sec = self._section("Заявки экспертизы Road Map",
                                ft.Icons.GAVEL, len(reviews), rows, "")
            if sec:
                self.results_area.controls.append(sec)

        achs = res["achievements"]
        if achs:
            rows = []
            for a in achs:
                rows.append(ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CELL_TOWER, size=18, color=PRIMARY),
                        ft.Column([
                            ft.Text(str(a["name"]), size=13,
                                    color=TEXT_DARK),
                            ft.Text(f"код {a['id']} · блок {a['block']} · "
                                    f"{a['points']} б.",
                                    size=11.5, color=TEXT_MUTED),
                        ], spacing=1, expand=True),
                        ft.TextButton("Каталог",
                                      on_click=lambda e: self._goto(
                                          "RoadmapCatalogPage", "catalog",
                                          "Достижения Road Map")),
                    ], spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(10, 6, 10, 6),
                    border_radius=10, bgcolor="#f8fafc"))
            sec = self._section("Достижения (каталог)", ft.Icons.STAR,
                                len(achs), rows, "")
            if sec:
                self.results_area.controls.append(sec)

        disc = res["discipline"]
        if disc:
            rows = []
            for d in disc:
                full = " ".join(x for x in [d["o_surname"], d["o_name"]]
                                if x)
                rows.append(ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.SHIELD, size=18, color=WARNING),
                        ft.Column([
                            ft.Text(f"{d['kind']} — {full}", size=13,
                                    color=TEXT_DARK),
                            ft.Text(f"{d['reason'] or ''} · {d['date_obj'] or ''}",
                                    size=11.5, color=TEXT_MUTED),
                        ], spacing=1, expand=True),
                        ft.TextButton("Личное дело",
                                      on_click=lambda e, sid=d["student_id"]:
                                      self._open_student(sid)),
                    ], spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(10, 6, 10, 6),
                    border_radius=10, bgcolor="#f8fafc"))
            sec = self._section("Дисциплинарная практика", ft.Icons.GAVEL,
                                len(disc), rows, "")
            if sec:
                self.results_area.controls.append(sec)

        sess = res["sessions"]
        if sess:
            rows = []
            for c in sess:
                full = " ".join(x for x in [c["o_surname"], c["o_name"]]
                               if x)
                rows.append(ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.SCHOOL, size=18, color=PRIMARY),
                        ft.Column([
                            ft.Text(f"{c['subject_name']} — {full}",
                                    size=13, color=TEXT_DARK),
                            ft.Text(f"{c['exam_type'] or ''} · оценка "
                                    f"{c['mark'] or '—'} · {c['date'] or ''}",
                                    size=11.5, color=TEXT_MUTED),
                        ], spacing=1, expand=True),
                        ft.TextButton("Личное дело",
                                      on_click=lambda e, sid=c["student_id"]:
                                      self._open_student(sid)),
                    ], spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(10, 6, 10, 6),
                    border_radius=10, bgcolor="#f8fafc"))
            sec = self._section("Результаты сессий", ft.Icons.SCHOOL,
                                len(sess), rows, "")
            if sec:
                self.results_area.controls.append(sec)

        try:
            log_action(session_username(self._page),
                       f"Глобальный поиск: «{self.query}» ({total})")
        except Exception:
            log_except("search_results_page: блок на строке 262")


def session_username(page_obj):
    from utils import session_get
    return session_get(page_obj, "username") or "system"
