"""Индивидуальный план развития (ИПР) курсанта — наследие MKR (ipr_editor).

Семестровая работа с курсантом: статусы «кандидат в резиденты / резидент»,
средний балл за семестр, текст ИПР с утверждением, ручные баллы по блокам
дорожной карты и сводка накопленных баллов.
"""

import flet as ft

from database import (search_students_by_name_part, get_individual_plan,
                      save_individual_plan, get_semester_status,
                      set_semester_status, get_semester_average,
                      set_semester_average, add_manual_score,
                      get_manual_scores, delete_manual_score,
                      get_student_total_points, BLOCK_NAMES, log_action)
from pages.registry import get_page
from theme import BG, PRIMARY, SUCCESS, TEXT_DARK, TEXT_MUTED, card, page_header
from utils import session_get, show_snack


IPR_STATUS_LABELS = {
    "draft": ("Черновик", "#64748b"),
    "approved": ("Утверждён", SUCCESS),
}


class RoadmapIprPage(ft.Column):
    def __init__(self, page_obj):
        super().__init__()
        self._page = page_obj
        self.username = session_get(page_obj, "username") or ""

        # ---- выбор курсанта и семестра ----
        self.student_search = ft.TextField(
            label="Поиск курсанта (фамилия/имя)", width=300,
            on_change=self.suggest_students)
        self.student_dd = ft.Dropdown(label="Курсант", width=340)
        self.semester_dd = ft.Dropdown(
            label="Семестр", width=140, value="1",
            options=[ft.dropdown.Option(str(i)) for i in range(1, 9)],
            on_select=lambda e: self.load_student_data())

        # ---- статусы семестра ----
        self.candidate_switch = ft.Switch(label="Кандидат в резиденты", value=False)
        self.resident_switch = ft.Switch(label="Резидент", value=False)
        self.avg_field = ft.TextField(label="Средний балл за семестр", width=200)
        self.status_btn = ft.FilledButton("Сохранить статусы", icon=ft.Icons.SAVE,
                                          on_click=self.save_statuses)

        # ---- ИПР ----
        self.plan_field = ft.TextField(
            label="Текст индивидуального плана развития",
            multiline=True, filled=True, min_lines=6, max_lines=14, expand=True)
        self.plan_status_text = ft.Text("", size=12, color=TEXT_MUTED)
        self.save_plan_btn = ft.OutlinedButton("Сохранить черновик",
                                               icon=ft.Icons.DESCRIPTION,
                                               on_click=lambda e: self.save_plan("draft"))
        self.approve_plan_btn = ft.FilledButton("Утвердить ИПР",
                                                icon=ft.Icons.VERIFIED_USER,
                                                on_click=lambda e: self.save_plan("approved"))

        # ---- ручные баллы ----
        self.block_dd = ft.Dropdown(
            label="Блок", width=280,
            options=[ft.dropdown.Option(key=str(b), text=n)
                     for b, n in BLOCK_NAMES.items()])
        self.score_field = ft.TextField(label="Баллы", width=110, value="0")
        self.comment_field = ft.TextField(label="Комментарий", width=260)
        self.add_score_btn = ft.FilledButton("Добавить балл", icon=ft.Icons.ADD,
                                             on_click=self.add_score)
        self.scores_column = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)
        self.total_text = ft.Text("", size=15, weight="bold", color=PRIMARY)

        form_card = card(ft.Column([
            ft.Text("Курсант и семестр", size=15, weight="bold", color=TEXT_DARK),
            ft.Row([self.student_search, self.student_dd, self.semester_dd],
                   wrap=True, spacing=10),
            ft.Row([self.candidate_switch, self.resident_switch,
                    self.avg_field, self.status_btn],
                   wrap=True, spacing=12,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self.total_text,
        ], spacing=12))

        plan_card = card(ft.Column([
            ft.Text("Индивидуальный план развития", size=15,
                    weight="bold", color=TEXT_DARK),
            self.plan_field,
            ft.Row([self.save_plan_btn, self.approve_plan_btn,
                    self.plan_status_text], wrap=True, spacing=10),
        ], spacing=12), expand=True)

        scores_card = card(ft.Column([
            ft.Text("Ручные баллы по блокам", size=15, weight="bold",
                    color=TEXT_DARK),
            ft.Row([self.block_dd, self.score_field, self.comment_field,
                    self.add_score_btn], wrap=True, spacing=10),
            self.scores_column,
        ], spacing=12), expand=True)

        self.controls = [ft.Container(
            content=ft.Column([
                page_header(page_obj, "ИПР и статусы курсанта (Road Map)",
                            on_back=self.go_home),
                form_card,
                ft.Row([plan_card, scores_card], spacing=16,
                       vertical_alignment=ft.CrossAxisAlignment.START,
                       wrap=True),
            ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True),
            bgcolor=BG, padding=24, expand=True)]

    # ------------------------------------------------------------------
    def go_home(self, e=None):
        self._page.controls.clear()
        self._page.add(get_page("DashboardPage")(self._page))
        self._page.update()

    def _student_id(self):
        try:
            return int(self.student_dd.value)
        except (TypeError, ValueError):
            return None

    def _semester(self):
        try:
            return int(self.semester_dd.value or 1)
        except ValueError:
            return 1

    def suggest_students(self, e):
        part = (self.student_search.value or "").strip()
        if len(part) < 2:
            return
        opts = []
        for r in search_students_by_name_part(part)[:30]:
            full = f"{r['o_surname']} {r['o_name']} {r['o_lastname'] or ''}".strip()
            opts.append(ft.dropdown.Option(key=str(r["id"]),
                                           text=f"{full} (ID {r['id']})"))
        self.student_dd.options = opts
        self.student_dd.on_select = lambda e: self.load_student_data()
        self._page.update()

    def load_student_data(self):
        sid = self._student_id()
        if not sid:
            return
        sem = self._semester()

        st = get_semester_status(sid, sem)
        self.candidate_switch.value = bool(st and st["is_candidate"])
        self.resident_switch.value = bool(st and st["is_resident"])
        avg = get_semester_average(sid, sem)
        self.avg_field.value = str(avg) if avg is not None else ""

        plan = get_individual_plan(sid, sem)
        self.plan_field.value = plan["plan_text"] if plan else ""
        if plan:
            label, color = IPR_STATUS_LABELS.get(plan["status"],
                                                 (plan["status"], TEXT_MUTED))
            approved = plan["approved_by"] or "—"
            date = plan["approved_date"] or ""
            self.plan_status_text.value = (f"Статус: {label} · "
                                           f"утвердил: {approved} {date}")
            self.plan_status_text.color = color
        else:
            self.plan_status_text.value = "ИПР ещё не создан"
            self.plan_status_text.color = TEXT_MUTED

        total = get_student_total_points(sid, sem)
        self.total_text.value = (f"Накоплено одобренных баллов за семестр "
                                 f"{sem}: {total}")

        self.refresh_scores()
        self._page.update()

    # ------------------------------------------------------------------
    def save_statuses(self, e):
        sid = self._student_id()
        if not sid:
            show_snack(self._page, "Сначала выберите курсанта")
            return
        sem = self._semester()
        set_semester_status(sid, sem,
                            is_candidate=self.candidate_switch.value,
                            is_resident=self.resident_switch.value)
        avg_raw = (self.avg_field.value or "").replace(",", ".").strip()
        if avg_raw:
            try:
                set_semester_average(sid, sem, float(avg_raw))
            except ValueError:
                show_snack(self._page, "Средний балл должен быть числом")
                return
        log_action(self.username,
                   f"ИПР: обновлены статусы студента {sid} (семестр {sem})")
        show_snack(self._page, "Статусы сохранены")

    def save_plan(self, status):
        sid = self._student_id()
        if not sid:
            show_snack(self._page, "Сначала выберите курсанта")
            return
        sem = self._semester()
        approved_by = self.username if status == "approved" else None
        save_individual_plan(sid, sem, self.plan_field.value or "",
                             status=status, approved_by=approved_by)
        log_action(self.username,
                   f"ИПР: {'утверждён' if status == 'approved' else 'сохранён'} "
                   f"для студента {sid} (семестр {sem})")
        show_snack(self._page, "ИПР сохранён")
        self.load_student_data()

    # ------------------------------------------------------------------
    def add_score(self, e):
        sid = self._student_id()
        if not sid:
            show_snack(self._page, "Сначала выберите курсанта")
            return
        if not self.block_dd.value:
            show_snack(self._page, "Выберите блок достижений")
            return
        try:
            score = int(float((self.score_field.value or "0").replace(",", ".")))
        except ValueError:
            show_snack(self._page, "Баллы должны быть числом")
            return
        add_manual_score(sid, self._semester(), int(self.block_dd.value),
                         score, self.comment_field.value or "")
        log_action(self.username, f"ИПР: ручной балл {score} для студента {sid}")
        self.score_field.value = "0"
        self.comment_field.value = ""
        self.refresh_scores()
        self._page.update()

    def remove_score(self, score_id):
        delete_manual_score(score_id)
        self.refresh_scores()
        self._page.update()

    def refresh_scores(self):
        sid = self._student_id()
        rows = (get_manual_scores(student_id=sid, semester=self._semester())
                if sid else [])
        self.scores_column.controls.clear()
        if not rows:
            self.scores_column.controls.append(
                ft.Text("Ручных баллов пока нет.", color=TEXT_MUTED, italic=True))
            return
        for r in rows:
            block_name = BLOCK_NAMES.get(r["block"], f"Блок {r['block']}")
            self.scores_column.controls.append(ft.Row([
                ft.Text(block_name, width=240, size=13, color=TEXT_DARK),
                ft.Text(f"{r['score']} балл.", size=13, weight="bold", color=SUCCESS),
                ft.Text(r["comment"] or "", size=12, color=TEXT_MUTED, expand=True),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Удалить",
                              on_click=lambda e, sid_=r["id"]: self.remove_score(sid_)),
            ]))
