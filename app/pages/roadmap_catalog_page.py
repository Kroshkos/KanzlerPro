"""Справочник достижений Дорожной карты (наследие MKR: achievements_catalog).

Позволяет просматривать/фильтровать справочник, добавлять и удалять позиции,
а также импортировать справочник из CSV-файла.
"""

import os

import flet as ft
from access import PermissionDeniedError
from database import (
    BLOCK_NAMES,
    add_achievement,
    count_achievements,
    delete_achievement,
    get_achievements,
    import_achievements_from_csv,
    log_action,
)
from theme import BG, TEXT_DARK, TEXT_MUTED, card, page_header
from utils import session_get, to_int

from pages import shell


class RoadmapCatalogPage(ft.Column):
    def __init__(self, page_obj, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO)
        self._page = page_obj
        self.block_filter = ft.Dropdown(
            label="Блок", width=260, value=None,
            options=[ft.dropdown.Option(key=str(b), text=n)
                     for b, n in BLOCK_NAMES.items()],
            on_select=self.refresh_table)
        self.search_field = ft.TextField(label="Поиск по названию/ID",
                                         width=280, on_change=self.refresh_table)
        self.csv_field = ft.TextField(label="Путь к CSV-справочнику",
                                      width=380,
                                      value="achievements_catalog.csv")

        self.table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Блок")),
                ft.DataColumn(ft.Text("Название достижения")),
                ft.DataColumn(ft.Text("Баллы")),
                ft.DataColumn(ft.Text("Тип расчёта")),
                ft.DataColumn(ft.Text("Версия")),
                ft.DataColumn(ft.Text("")),
            ],
            rows=[],
            expand=True,
            horizontal_margin=0,
        )
        self.counter = ft.Text("", size=13, color=TEXT_MUTED)

        # форма добавления
        self.f_id = ft.TextField(label="ID", width=100)
        self.f_block = ft.Dropdown(label="Блок", width=260,
                                   options=[ft.dropdown.Option(key=str(b), text=n)
                                            for b, n in BLOCK_NAMES.items()], value="1")
        self.f_name = ft.TextField(label="Название", width=420)
        self.f_points = ft.TextField(label="Баллы", width=100, value="10")
        self.f_calc = ft.Dropdown(label="Тип расчёта", width=180, value="ms",
                                  options=[
                                      ft.dropdown.Option("ms", "Множитель (k)"),
                                      ft.dropdown.Option("month", "За месяц"),
                                      ft.dropdown.Option("grant", "Грант (сумма)"),
                                      ft.dropdown.Option("avg_score", "Средний балл"),
                                  ])
        self.f_version = ft.TextField(label="Версия", width=140)

        form = card(ft.Column([
            ft.Text("Добавить / обновить достижение", size=15, weight="bold",
                    color=TEXT_DARK),
            ft.Row([self.f_id, self.f_block, self.f_name], wrap=True, spacing=10),
            ft.Row([self.f_points, self.f_calc, self.f_version,
                    ft.FilledButton("Сохранить", icon=ft.Icons.SAVE,
                                    on_click=self.add_row)],
                   wrap=True, spacing=10),
        ], spacing=10))

        toolbar = ft.Row([
            self.block_filter, self.search_field,
            ft.OutlinedButton("Показать", icon=ft.Icons.FILTER_ALT,
                              on_click=self.refresh_table),
            ft.Container(expand=True),
            self.csv_field,
            ft.OutlinedButton("Импорт CSV", icon=ft.Icons.UPLOAD_FILE,
                              on_click=self.import_csv),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self.controls = [ft.Container(
            content=ft.Column([
                page_header(page_obj, "Справочник достижений Road Map",
                            on_back=self.go_home),
                toolbar,
                card(self.table, padding=12),
                self.counter,
                form,
            ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True),
            bgcolor=BG, padding=24, expand=True)]
        self.refresh_table()

    # ------------------------------------------------------------------
    def go_home(self, e=None):
        shell.navigate(self._page, "DashboardPage", dashboard=True)

    def refresh_table(self, e=None):
        rows = []
        block = self.block_filter.value
        search = (self.search_field.value or "").strip()
        for r in get_achievements(block=block, search=search or None):
            del_btn = ft.IconButton(
                ft.Icons.DELETE_OUTLINE, icon_color="red",
                tooltip="Удалить",
                on_click=lambda ev, rid=r["id"]: self.delete_row(rid))
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(r["id"]))),
                ft.DataCell(ft.Text(BLOCK_NAMES.get(r["block"], str(r["block"])),
                                    size=12)),
                ft.DataCell(ft.Text(r["name"], size=12)),
                ft.DataCell(ft.Text(str(r["points"]), weight="bold")),
                ft.DataCell(ft.Text(r["calc_type"] or "ms", size=12)),
                ft.DataCell(ft.Text(r["version"] or "", size=12)),
                ft.DataCell(del_btn),
            ]))
        self.table.rows = rows
        self.counter.value = f"Всего в базе: {count_achievements()} · " \
                             f"показано: {len(rows)}"
        self._page.update()

    def add_row(self, e):
        try:
            if not self.f_id.value or not self.f_name.value:
                raise ValueError("Заполните ID и название")
            add_achievement(self.f_id.value.strip(), self.f_block.value,
                            self.f_name.value.strip(), to_int(self.f_points.value, 0),
                            self.f_version.value or "", self.f_calc.value,
                            actor_role=session_get(self._page, "role"))
            user = session_get(self._page, "username")
            log_action(user, f"Справочник: сохранено достижение {self.f_id.value}")
            self.refresh_table()
        except PermissionDeniedError:
            self.counter.value = "Отказано: действие доступно только администратору"
            self._page.update()
        except Exception as ex:
            self.counter.value = f"Ошибка: {ex}"
            self._page.update()

    def delete_row(self, ach_id):
        try:
            # B-1: серверная проверка прав — роль из сессии
            delete_achievement(ach_id, actor_role=session_get(self._page, "role"))
        except PermissionDeniedError:
            self.counter.value = "Отказано: действие доступно только администратору"
            self._page.update()
            return
        log_action(session_get(self._page, "username"),
                   f"Справочник: удалено достижение {ach_id}")
        self.refresh_table()

    def import_csv(self, e):
        path = (self.csv_field.value or "").strip()
        try:
            n = import_achievements_from_csv(
                path, actor_role=session_get(self._page, "role"))
            log_action(session_get(self._page, "username"),
                       f"Справочник: импорт CSV ({n} записей)")
            self.counter.value = f"Импортировано записей: {n}"
            self.refresh_table()
        except PermissionDeniedError:
            self.counter.value = "Отказано: импорт доступен только администратору"
            self._page.update()
        except Exception as ex:
            self.counter.value = f"Ошибка импорта: {ex}"
            self._page.update()

    # --- Импорт курсантов из XLSX (BACKLOG F-5) ----------------------------
    def import_students_xlsx(self, path: str) -> str:
        """Двухшаговый импорт: разбор+валидация, затем транзакционная вставка.

        Возвращает человекочитаемый отчёт; бросает PermissionDeniedError
        (роль из сессии — B-1) и ValueError (битый файл/заголовки).
        Строки с ошибками в БД не попадают; если валидных нет — 0 вставок.
        """
        from xlsx_import import commit_import, parse_workbook

        rows = parse_workbook(path)
        bad = [r for r in rows if not r.ok]
        inserted = commit_import(
            rows,
            actor_role=session_get(self._page, "role"),
            log_user=session_get(self._page, "username") or "system")
        report = f"Импорт XLSX: добавлено {inserted}, строк с ошибками {len(bad)}"
        log_action(session_get(self._page, "username"),
                   f"{report} (файл: {os.path.basename(path)})")
        return report
