"""Печать отчётных форм Дорожной карты (перенос из MKR: report_generator).

Формы Р-1…Р-5 в форматах Excel и PDF. Сгенерированные файлы сохраняются
в data/reports и доступны для скачивания через FilePicker/Fletdownload.
"""

import os

import flet as ft
from config import REPORTS_DIR
from database import execute_query, log_action, search_students_by_name_part
from theme import DANGER, PRIMARY, SUCCESS, TEXT_DARK, TEXT_MUTED, card, section_title
from utils import session_get, to_int
from utils_logger import log_except

FORMS = [
    ("R1", "Р-1 · Индивидуальный отчёт курсанта", True),
    ("R2", "Р-2 · Ведомость семестрового рейтинга", False),
    ("R3", "Р-3 · Сводный отчёт по группе", False),
    ("R4", "Р-4 · Сводный академический отчёт (план/факт)", False),
    ("R5", "Р-5 · Отчёт по выполнению ИПР", True),
]


class RoadmapReportsPage(ft.Column):
    def __init__(self, page, parent=None):
        super().__init__()
        self._fpage = page
        self.nav_parent = parent
        self.width = 1160
        self.expand_width = True
        self.spacing = 14
        self.last_path = None

        self.controls = [
            ft.Text("Отчётные формы Road Map", size=24, weight="bold",
                    color=TEXT_DARK),
            ft.Text("Формы Р-1…Р-5 — перенос печатных отчётов из системы "
                    "«Эксперт Дорожной карты» (MKR).", size=13,
                    color=TEXT_MUTED),
            self._build_form(),
            card(ft.Column([], spacing=6), expand=True),
        ]
        self._refresh_files()

    # ---------------- форма параметров ----------------
    def _build_form(self):
        self.form_dd = ft.Dropdown(
            label="Форма", width=380, dense=True, value="R2",
            options=[ft.dropdown.Option(key=k, text=t) for k, t, _ in FORMS],
            on_select=self._on_form_change)
        self.student_tf = ft.TextField(
            label="Курсант (фамилия)", width=240, dense=True,
            border_radius=10, visible=False)
        self.group_tf = ft.TextField(
            label="Группа (пусто = все)", width=220, dense=True,
            border_radius=10)
        self.sem_dd = ft.Dropdown(
            label="Семестр", width=170, dense=True,
            options=[ft.dropdown.Option(key="", text="Все")] +
                    [ft.dropdown.Option(key=str(s), text=f"Семестр {s}")
                     for s in range(1, 13)],
            value="")
        self.fmt_dd = ft.Dropdown(
            label="Формат", width=150, dense=True, value="xlsx",
            options=[ft.dropdown.Option("xlsx", "Excel (.xlsx)"),
                     ft.dropdown.Option("pdf", "PDF (.pdf)")])
        self.run_btn = ft.FilledButton(
            "Сформировать отчёт", icon=ft.Icons.PRINT,
            on_click=self.generate)
        self.status_txt = ft.Text("", size=13, color=TEXT_MUTED)

        return card(ft.Column([
            ft.Row([self.form_dd, self.student_tf, self.group_tf,
                    self.sem_dd, self.fmt_dd], spacing=10, wrap=True),
            ft.Row([self.run_btn, self.status_txt], spacing=12),
        ], spacing=12))

    def _on_form_change(self, e):
        needs_student = self._needs_student()
        self.student_tf.visible = needs_student
        self.group_tf.visible = not needs_student
        self._safe_update()

    def _needs_student(self):
        return self.form_dd.value in ("R1", "R5")

    # ---------------- генерация ----------------
    def generate(self, e):
        from report_generator import (
            REPORTLAB_AVAILABLE,
            generate_R1,
            generate_R2,
            generate_R3,
            generate_R4,
            generate_R5,
        )
        fmt = self.fmt_dd.value or "xlsx"
        if fmt == "pdf" and not REPORTLAB_AVAILABLE:
            self.status_txt.value = "Для PDF установите: pip install reportlab"
            self.status_txt.color = DANGER
            self.update()
            return
        semester = to_int(self.sem_dd.value)
        form = self.form_dd.value
        try:
            if form in ("R1", "R5"):
                sid = self._find_student_id()
                if sid is None:
                    self.status_txt.value = "Курсант не найден"
                    self.status_txt.color = DANGER
                    self.update()
                    return
                path = (generate_R1(sid, semester, fmt) if form == "R1"
                        else generate_R5(sid, semester, fmt))
            elif form == "R2":
                path = generate_R2((self.group_tf.value or "").strip(),
                                   semester, fmt)
            elif form == "R3":
                path = generate_R3((self.group_tf.value or "").strip(),
                                   semester, fmt)
            else:
                path = generate_R4(semester, fmt)

            username = session_get(self._fpage, "username") or "?"
            log_action(username, f"Сформирована форма {form} ({fmt})")
            self.last_path = path
            self.status_txt.value = f"Готово: {os.path.basename(path)}"
            self.status_txt.color = SUCCESS
            self._open_file(path)
            self._refresh_files()
        except Exception as ex:
            self.status_txt.value = f"Ошибка: {ex}"
            self.status_txt.color = DANGER
        self._safe_update()

    def _safe_update(self):
        try:
            self.update()
        except RuntimeError:
            log_except("roadmap_reports_page: блок на строке 143")

    def _find_student_id(self):
        name = (self.student_tf.value or "").strip()
        if not name:
            return None
        rows = search_students_by_name_part(name)
        return rows[0]["id"] if rows else None

    # ---------------- сохранённые файлы ----------------
    def _refresh_files(self):
        os.makedirs(REPORTS_DIR, exist_ok=True)
        files = sorted(
            (f for f in os.listdir(REPORTS_DIR)
             if f.lower().endswith((".xlsx", ".pdf"))),
            key=lambda f: os.path.getmtime(os.path.join(REPORTS_DIR, f)),
            reverse=True)[:20]
        controls = [section_title("Последние отчёты",
                                 os.path.relpath(REPORTS_DIR))]
        if not files:
            controls.append(ft.Text("Файлов пока нет.", size=13,
                                    color=TEXT_MUTED))
        for f in files:
            full = os.path.join(REPORTS_DIR, f)
            size_kb = round(os.path.getsize(full) / 1024, 1)
            controls.append(ft.Row([
                ft.Icon(ft.Icons.DESCRIPTION if f.endswith(".pdf")
                        else ft.Icons.TABLE_VIEW, size=18, color=PRIMARY),
                ft.Container(ft.Text(f, size=13, color=TEXT_DARK),
                             expand=True),
                ft.Text(f"{size_kb} КБ", size=12, color=TEXT_MUTED),
                ft.IconButton(ft.Icons.OPEN_IN_NEW, tooltip="Открыть",
                              on_click=lambda ev, p=full: self._open_file(p)),
            ], spacing=6))
        if len(self.controls) > 3:
            self.controls[3].content = ft.Column(controls, spacing=6,
                                                 scroll=ft.ScrollMode.AUTO,
                                                 height=360)

    def _open_file(self, path):
        """Открывает файл стандартной программой ОС (для десктоп-режима)."""
        try:
            import subprocess
            import sys
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            # в web-режиме файл доступен в папке data/reports — не критично
            log_except("roadmap_reports_page: открытие файла в ОС")
