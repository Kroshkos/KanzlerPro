"""Экспертиза достижений Дорожной карты (наследие MKR: expert_window).

Позволяет зарегистрировать достижение курсанта, выставить коэффициенты и
принять экспертное решение (одобрить/отклонить) с автоматическим расчётом
итоговых баллов по формуле MKR.
"""

import flet as ft
from access import PermissionDeniedError
from authz import is_admin, require_admin
from database import (
    BLOCK_NAMES,
    add_review,
    calculate_final_points,
    delete_review,
    get_achievements,
    get_reviews,
    log_action,
    search_students_by_name_part,
    update_review,
)
from theme import BG, TEXT_DARK, TEXT_MUTED, card, page_header, status_chip
from utils import row_get, session_get, to_int, to_num

from pages import shell


class RoadmapExpertPage(ft.Column):
    def __init__(self, page_obj, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO)
        self._page = page_obj

        # --- Защита прав: экспертиза доступна только Администратору. ---
        # Раньше страница не проверяла роль вообще: любой пользователь мог
        # одобрять/отклонять заявки и начислять баллы Дорожной карты.
        # Проверка дублируется в точках мутаций (см. _guard_write), потому
        # что сессия может измениться после построения страницы (выход).
        denied = require_admin(page_obj,
                               "Экспертиза достижений доступна только администратору")
        if denied is not None:
            self.controls = [denied]
            return

        # ---- выбор студента (по поиску ФИО, как в Канцлере) ----
        self.student_search = ft.TextField(label="Поиск курсанта (фамилия/имя)",
                                          width=300, on_change=self.suggest_students)
        self.student_dd = ft.Dropdown(label="Курсант", width=340)
        self.student_info = ft.Text("", size=12, color=TEXT_MUTED)

        # ---- выбор достижения ----
        self.block_dd = ft.Dropdown(label="Блок", width=280, value=None,
                                    options=[ft.dropdown.Option(key=str(b), text=n)
                                             for b, n in BLOCK_NAMES.items()],
                                    on_select=self.load_achievements)
        self.ach_dd = ft.Dropdown(label="Достижение", width=420)
        self.semester_field = ft.TextField(label="Семестр", width=120, value="1")

        # ---- коэффициенты ----
        self.k_ur = ft.TextField(label="К-уровень", width=110, value="1.0")
        self.k_role = ft.TextField(label="К-роль", width=110, value="1.0")
        self.k_vn = ft.TextField(label="К-вид", width=110, value="1.0")
        self.k_st = ft.TextField(label="К-статус", width=110, value="1.0")
        self.months = ft.TextField(label="Месяцев", width=110, value="0")
        self.grant = ft.TextField(label="Грант, ₽", width=130, value="0")
        self.ip_bonus = ft.TextField(label="Бонус ИПР", width=120, value="0")
        self.preview = ft.Text("Итог: —", size=14, weight="bold", color=TEXT_DARK)

        self.add_btn = ft.FilledButton("Зарегистрировать достижение",
                                       icon=ft.Icons.ADD_TASK,
                                       on_click=self.add_new_review)

        # ---- фильтры и таблица решений ----
        self.status_filter = ft.Dropdown(label="Статус", width=220, value=None,
                                         options=[
                                             ft.dropdown.Option("pending", "На рассмотрении"),
                                             ft.dropdown.Option("approved", "Одобрено"),
                                             ft.dropdown.Option("rejected", "Отклонено"),
                                         ], on_select=self.refresh_table)
        self.table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h)) for h in
                     ("№", "Курсант", "Достижение", "Семестр", "Статус", "Баллы")]
            + [ft.DataColumn(ft.Text("Решение"))],
            rows=[], expand=True, horizontal_margin=0)
        self.counter = ft.Text("", size=13, color=TEXT_MUTED)

        form = card(ft.Column([
            ft.Text("Новое экспертное решение", size=15, weight="bold", color=TEXT_DARK),
            ft.Row([self.student_search, self.student_dd], wrap=True, spacing=10),
            self.student_info,
            ft.Row([self.block_dd, self.ach_dd, self.semester_field],
                   wrap=True, spacing=10),
            ft.Row([self.k_ur, self.k_role, self.k_vn, self.k_st,
                    self.months, self.grant, self.ip_bonus], wrap=True, spacing=8),
            ft.Row([self.add_btn, self.preview], spacing=16,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=12))

        toolbar = ft.Row([
            self.status_filter,
            ft.OutlinedButton("Обновить", icon=ft.Icons.REFRESH,
                              on_click=self.refresh_table),
        ], spacing=10)

        self.controls = [ft.Container(
            content=ft.Column([
                page_header(page_obj, "Экспертиза достижений Road Map",
                            on_back=self.go_home),
                form,
                toolbar,
                card(self.table, padding=12),
                self.counter,
            ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True),
            bgcolor=BG, padding=24, expand=True)]

        self.load_achievements()
        self.refresh_table()

    # ------------------------------------------------------------------
    def go_home(self, e=None):
        shell.navigate(self._page, "DashboardPage", dashboard=True)

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
        self._page.update()

    def load_achievements(self, e=None):
        block = self.block_dd.value
        opts = [ft.dropdown.Option(key=str(r["id"]),
                                   text=f"[{r['points']}] {r['name']}")
                for r in get_achievements(block=block)[:200]]
        self.ach_dd.options = opts
        self.ach_dd.value = None
        self._page.update()

    def _f(self, tf, default=1.0):
        try:
            return to_num(tf.value, default)
        except (TypeError, ValueError):
            return default

    def calc_preview(self, points, calc_type):
        final = calculate_final_points(
            calc_type, points,
            k_ur=self._f(self.k_ur), k_role=self._f(self.k_role),
            k_vn=self._f(self.k_vn), k_st=self._f(self.k_st),
            duration_months=int(self._f(self.months, 0)),
            grant_amount=self._f(self.grant, 0),
            ip_bonus=int(self._f(self.ip_bonus, 0)))
        self.preview.value = f"Итог: {final} баллов"

    def _guard_write(self):
        """Повторная проверка роли в точках мутации.

        Страница могла быть построена, пока пользователь был админом; после
        выхода/смены сессии кнопки ещё живы в дереве UI — не даём писать.
        """
        if is_admin(self._page):
            return True
        from utils import show_snack
        show_snack(self._page,
                   "Недостаточно прав: экспертиза доступна только администратору")
        return False

    def _deny_snack(self):
        """B-1: единый ответ на отказ серверного слоя прав."""
        from utils import show_snack
        show_snack(self._page,
                   "Недостаточно прав: действие доступно только администратору")
        self._page.update()

    def add_new_review(self, e):
        if not self._guard_write():
            return
        sid = self.student_dd.value
        aid = self.ach_dd.value
        if not sid or not aid:
            self.counter.value = "Выберите курсанта и достижение"
            self._page.update()
            return
        ach = next((a for a in get_achievements(search=aid) if a["id"] == aid), None)
        calc_type = ach["calc_type"] if ach else "ms"
        points = ach["points"] if ach else 0
        self.calc_preview(points, calc_type)
        try:
            semester = to_int(self.semester_field.value, 1)
        except ValueError:
            semester = 1
        try:
            # B-1: серверная проверка прав — роль из сессии
            add_review(int(sid), aid, semester, status="pending",
                       actor_role=session_get(self._page, "role"))
        except PermissionDeniedError:
            self._deny_snack()
            return
        log_action(session_get(self._page, "username"),
                   f"Road Map: зарегистрировано достижение {aid} для студента {sid}")
        self.refresh_table()

    def decide(self, review_id, status, final_points):
        if not self._guard_write():
            return
        if status == "deleted":
            # Удаление записи — через delete_review (DELETE FROM).
            # Раньше сюда вёл пункт «Удалить запись», но update_review с
            # таким статусом лишь помечал строку и она навсегда исчезала
            # из всех фильтров (get_reviews возвращает только известные
            # статусы) — фактически это была тихая порча данных.
            try:
                # B-1: серверная проверка прав — роль из сессии
                delete_review(review_id, actor_role=session_get(self._page, "role"))
            except PermissionDeniedError:
                self._deny_snack()
                return
            log_action(session_get(self._page, "username"),
                       f"Road Map: удалена заявка №{review_id}")
        else:
            try:
                update_review(review_id, status, final_points=final_points,
                              actor_role=session_get(self._page, "role"))
            except PermissionDeniedError:
                self._deny_snack()
                return
            log_action(session_get(self._page, "username"),
                       f"Road Map: решение '{status}' по заявке №{review_id}")
        self.refresh_table()

    def refresh_table(self, e=None):
        rows = []
        reviews = get_reviews(status=self.status_filter.value or None)
        for r in reviews:
            decision_cells = []
            if r["status"] == "pending":
                decision_cells.append(ft.IconButton(
                    ft.Icons.CHECK_CIRCLE, icon_color="green",
                    tooltip="Одобрить",
                    on_click=lambda ev, rid=r["id"], k=row_get(r, "k_ur", 1.0),
                            kr=row_get(r, "k_role", 1.0), kv=row_get(r, "k_vn", 1.0),
                            ks=row_get(r, "k_st", 1.0), d=row_get(r, "duration_months", 0),
                            g=row_get(r, "grant_amount", 0), ib=row_get(r, "ip_bonus", 0),
                            aid=r["achievement_id"]:
                        self.approve(rid, aid, k, kr, kv, ks, d, g, ib)))
                decision_cells.append(ft.IconButton(
                    ft.Icons.CANCEL, icon_color="red", tooltip="Отклонить",
                    on_click=lambda ev, rid=r["id"]:
                        self.decide(rid, "rejected", None)))
            else:
                decision_cells.append(ft.IconButton(
                    ft.Icons.DELETE_OUTLINE, icon_color="grey",
                    tooltip="Удалить запись",
                    on_click=lambda ev, rid=r["id"]: self.decide(rid, "deleted", None)))
            fio = f"{r['o_surname']} {r['o_name']} ({r['o_group_name'] or '—'})"
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(r["id"]))),
                ft.DataCell(ft.Text(fio, size=12)),
                ft.DataCell(ft.Text(str(r["ach_name"] or r["achievement_id"] or "—")[:70], size=12)),
                ft.DataCell(ft.Text(str(r["semester"]))),
                ft.DataCell(status_chip(r["status"])),
                ft.DataCell(ft.Text(str(r["final_points"] or "—"), weight="bold")),
                ft.DataCell(ft.Row(decision_cells, spacing=0)),
            ]))
        self.table.rows = rows
        self.counter.value = f"Заявок показано: {len(rows)}"
        self._page.update()

    def approve(self, review_id, achievement_id, k_ur=1.0, k_role=1.0,
                k_vn=1.0, k_st=1.0, duration_months=0, grant_amount=0,
                ip_bonus=0):
        if not self._guard_write():
            return
        ach = next((a for a in get_achievements(search=achievement_id)
                    if a["id"] == achievement_id), None)
        pts = ach["points"] if ach else 0
        calc = ach["calc_type"] if ach else "ms"
        final = calculate_final_points(calc, pts, k_ur, k_role, k_vn, k_st,
                                       duration_months, grant_amount, ip_bonus)
        try:
            update_review(review_id, "approved", final_points=final,
                          actor_role=session_get(self._page, "role"))
        except PermissionDeniedError:
            self._deny_snack()
            return
        log_action(session_get(self._page, "username"),
                   f"Road Map: одобрена заявка №{review_id} ({final} баллов)")
        self.refresh_table()
