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
from pages import shell
from utils import session_get, session_set, session_clear, show_snack, to_int, to_num


class LogsPage(ft.Column):
    def __init__(self, page, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO)
        self._page = page
        self.username = session_get(self._page, "username")

        # Поле для выбора даты
        self.date_picker = ft.TextField(
            label="Выберите дату (ДД.ММ.ГГГГ) или оставьте пустым для всех дат",
            width=300,
            on_change=self.filter_logs
        )

        # Выпадающий список для количества строк
        self.rows_dropdown = ft.Dropdown(
            label="Количество строк",
            width=150,
            options=[
                ft.dropdown.Option("10"),
                ft.dropdown.Option("25"),
                ft.dropdown.Option("50"),
                ft.dropdown.Option("100"),
                ft.dropdown.Option("Все строки"),
            ],
            value="10",  # Значение по умолчанию
            on_select=self.filter_logs
        )

        # Кнопка для экспорта в txt
        self.export_button = ft.FilledButton("Экспорт в TXT", width=150, on_click=self.export_to_txt)

        # Таблица логов
        self.logs_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Дата и время")),
                ft.DataColumn(ft.Text("Пользователь")),
                ft.DataColumn(ft.Text("Действие")),
            ],
            rows=[]
        )

        # Кнопка "Назад"
        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        # Составляем интерфейс
        self.controls = [
            ft.Row(
                controls=[
                    ft.Text("Журнал действий", size=20, weight="bold"),
                    ft.Container(expand=True),  # Для выравнивания элементов справа
                    self.date_picker,
                    self.rows_dropdown,
                    self.export_button
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER
            ),
            ft.Divider(),
            self.logs_table,
            self.back_button
        ]

        # Загружаем логи при инициализации
        self.load_logs()

    def load_logs(self):
        """Загружает и фильтрует логи в зависимости от выбранной даты и количества строк."""
        logs = get_logs()
        self.logs_table.rows = []

        # Фильтрация по дате
        selected_date = self.date_picker.value.strip()
        if selected_date:
            try:
                # Преобразуем введённую дату в формат для сравнения
                selected_date = datetime.strptime(selected_date, "%d.%m.%Y").strftime("%Y-%m-%d")
                logs = [log for log in logs if log[0].startswith(selected_date)]
            except ValueError:
                show_snack(self._page, ft.Text("Неверный формат даты. Используйте ДД.ММ.ГГГГ"))
                self._page.update()
                return

        # Ограничение количества строк
        rows_limit = self.rows_dropdown.value
        if rows_limit != "Все строки":
            logs = logs[:to_int(rows_limit, len(logs))]

        # Заполняем таблицу
        for log in logs:
            timestamp, username, action = log
            self.logs_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(timestamp)),
                        ft.DataCell(ft.Text(username)),
                        ft.DataCell(ft.Text(action)),
                    ]
                )
            )
        self._page.update()

    def filter_logs(self, e):
        """Обработчик изменения даты или количества строк."""
        self.load_logs()

    def export_to_txt(self, e):
        """Экспортирует отображаемые логи в текстовый файл."""
        from tkinter import filedialog, Tk
        import os

        # Собираем данные из таблицы
        log_text = "Дата и время\tПользователь\tДействие\n"
        for row in self.logs_table.rows:
            timestamp = row.cells[0].content.value
            username = row.cells[1].content.value
            action = row.cells[2].content.value
            log_text += f"{timestamp}\t{username}\t{action}\n"

        # Запрашиваем путь для сохранения файла
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            title="Сохранить логи как"
        )

        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(log_text)
            show_snack(self._page, ft.Text(f"Логи сохранены в: {file_path}"))
            self._page.update()

    def back_click(self, e):
        log_action(self.username, "Возврат на главную страницу из журнала")
        shell.back_to_app(self._page)
