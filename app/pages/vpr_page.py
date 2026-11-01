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
from utils import show_snack, to_int


class EncouragementWorkPage(ft.Column):
    def _wrap_control(self, control):
        """Возвращает контрол для показа: внутри каркаса — через shell
        (боковое меню сохраняется), автономно — как раньше."""
        from pages import shell as _shell
        sh = _shell.get_shell()
        if sh is not None and self._page is not None:
            sh.open_standalone(type(control).__name__, control)
            return None
        return control

    def __init__(self, page, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO)
        self._page = page

        # Поле для ввода ФИО курсанта с автодополнением
        self.student_search_field = ft.TextField(
            label="Введите ФИО курсанта",
            width=500,
            on_change=self.update_student_dropdown
        )
        # Выпадающий список для отображения найденных курсантов
        self.student_dropdown = ft.Dropdown(
            width=500,
            options=[],
            visible=False,
            on_select=self.select_student
        )
        self.encouragement_type_field = ft.Dropdown(
            label="Тип поощерения",
            options=[
                ft.dropdown.Option("Благодароность"),
                ft.dropdown.Option("Одобрительное похлопавание по плечу"),
                ft.dropdown.Option("")
            ],
            width=500
        )
        self.reason_field = ft.TextField(label="За что", width=500)
        self.issued_by_field = ft.Dropdown(
            label="От кого",
            options= [
                ft.dropdown.Option("Начальника академии"),
                ft.dropdown.Option("Заместителя начальника академии"),
                ft.dropdown.Option("Начальника факультета"),
                ft.dropdown.Option("Заместителя начальника факультета"),
                ft.dropdown.Option("Начальника курса")
            ],
            width=500
        )
        self.date_field = ft.TextField(label="Дата (ДД.ММ.ГГГГ)", width=245)
        self.order_number_field = ft.TextField(label="Номер приказа", width=250)

        self.date_order_number_field = ft.Row([self.date_field, self.order_number_field], spacing=5)

        # Кнопка для добавления поощерения
        self.add_penalty_button = ft.FilledButton("Добавить поощерение", on_click=self.add_penalty_click)

        # Таблица для отображения поощерений
        self.penalties_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Вид поощерения")),
                ft.DataColumn(ft.Text("За что")),
                ft.DataColumn(ft.Text("От кого")),
                ft.DataColumn(ft.Text("Дата")),
                ft.DataColumn(ft.Text("Номер приказа")),
            ],
            rows=[]
        )

        # Кнопка для возврата на главную страницу
        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        self.controls = [
            ft.Text("Добавление поощерения", size=20, weight="bold"),
            self.student_search_field,
            self.student_dropdown,
            self.encouragement_type_field,
            self.reason_field,
            self.issued_by_field,
            self.date_order_number_field,
            self.add_penalty_button,
            ft.Divider(),
            self.penalties_table,
            self.back_button
        ]

        # Переменная для хранения выбранного курсанта
        self.selected_student_id = None

    def update_student_dropdown(self, e):
        search_text = self.student_search_field.value.strip()
        if search_text:
            # Ищем курсантов по части ФИО
            students = search_students_by_name_part(search_text)
            if students:
                # Обновляем опции выпадающего списка
                self.student_dropdown.options = [
                    ft.dropdown.Option(
                        text=f"{student[1]} {student[2]} {student[3]}",
                        key=str(student[0])  # Используем ID курсанта как ключ
                    )
                    for student in students
                ]
                self.student_dropdown.visible = True  # Показываем выпадающий список
            else:
                self.student_dropdown.options = []
                self.student_dropdown.visible = False  # Скрываем выпадающий список, если нет результатов
        else:
            # Если поле поиска пустое, очищаем список и скрываем его
            self.student_dropdown.options = []
            self.student_dropdown.visible = False

        self._page.update()

    def select_student(self, e):
        # Получаем выбранного курсанта из выпадающего списка
        selected_student_key = self.student_dropdown.value
        if selected_student_key:
            self.selected_student_id = to_int(selected_student_key)
            # Обновляем поле ввода текстом выбранного курсанта
            selected_student_text = next(
                option.text for option in self.student_dropdown.options
                if option.key == selected_student_key
            )
            self.student_search_field.value = selected_student_text
            self.student_dropdown.visible = False  # Скрываем выпадающий список после выбора

            # Обновляем таблицу с поощерениями для выбранного курсанта
            self.update_penalties_table(self.selected_student_id)

            # Показываем сообщение о выборе курсанта
            show_snack(self._page, ft.Text(f"Выбран курсант: {selected_student_text}"))
            self._page.update()

    def add_penalty_click(self, e):
        if not self.selected_student_id:
            show_snack(self._page, ft.Text("Выберите курсанта"))
            self._page.update()
            return

        encouragement_type = self.encouragement_type_field.value
        reason = self.reason_field.value
        issued_by = self.issued_by_field.value
        date_str = self.date_field.value
        order_number = self.order_number_field.value


        if not date_str or not encouragement_type or not issued_by or not reason:
            show_snack(self._page, ft.Text("Заполните все поля"))
            self._page.update()
            return

        # Преобразуем дату из ДД.ММ.ГГГГ в ГГГГ-ММ-ДД
        try:
            date_obj = datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")
        except ValueError:
            show_snack(self._page, ft.Text("Некорректный формат даты. Используйте ДД.ММ.ГГГГ"))
            self._page.update()
            return

        # Добавляем поощерение в базу данных
        add_encouragement(self.selected_student_id, encouragement_type, reason, issued_by, date_obj, order_number)

        # Обновляем таблицу с поощерениями
        self.update_encouragements_table(self.selected_student_id)

        # Очищаем поля ввода
        self.encouragement_type_field.value = ""
        self.reason_field.value = ""
        self.issued_by_field.value = ""
        self.date_field.value = ""
        self.order_number_field.value = ""

        show_snack(self._page, ft.Text("Поощерение успешно добавлено"))
        self._page.update()

    def update_encouragements_table(self, student_id):
        # Получаем поощерения для выбранного курсанта
        penalties = get_encouragements_by_student(student_id)

        # Очищаем таблицу и добавляем взыскания
        self.penalties_table.rows = []
        for penalty in penalties:
            # Преобразуем дату из ГГГГ-ММ-ДД в ДД.ММ.ГГГГ для отображения
            date_display = datetime.strptime(penalty[3], "%Y-%m-%d").strftime("%d.%m.%Y")
            self.penalties_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(penalty[0])),  # Тип взыскания
                        ft.DataCell(ft.Text(penalty[1])),  # За что
                        ft.DataCell(ft.Text(penalty[2])),  # От кого
                        ft.DataCell(ft.Text(date_display)),  # Дата
                        ft.DataCell(ft.Text(penalty[4])),  # Номер приказа
                    ]
                )
            )

        self._page.update()
    def _wrap_control(self, control):
        """Возвращает контрол для показа: внутри каркаса — через shell
        (боковое меню сохраняется), автономно — как раньше."""
        from pages import shell as _shell
        sh = _shell.get_shell()
        if sh is not None and self._page is not None:
            sh.open_standalone(type(control).__name__, control)
            return None
        return control


    def back_click(self, e):
        shell.navigate(self._page, "VprWorkPage")

class PenaltyWorkPage(ft.Column):
    def __init__(self, page, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO)
        self._page = page

        # Поле для ввода ФИО курсанта с автодополнением
        self.student_search_field = ft.TextField(
            label="Введите ФИО курсанта",
            width=500,
            on_change=self.update_student_dropdown
        )

        # Выпадающий список для отображения найденных курсантов
        self.student_dropdown = ft.Dropdown(
            width=500,
            options=[],
            visible=False,
            on_select=self.select_student
        )

        # Поля для ввода данных о взыскании
        self.penalty_type_field = ft.Dropdown(
            label="Вид взыскания", 
            options=[
                ft.dropdown.Option("Грубый дисциплинарный проступок"),
                ft.dropdown.Option("Строгий выговор"),
                ft.dropdown.Option("Выговор")
            ],
            width=500)
        self.reason_field = ft.TextField(label="Основание применения взскания", width=500)
        self.date_reason_field = ft.TextField(label="Когда совершен проступок(ДД.ММ.ГГГГ)", width=500)
        self.issued_by_field = ft.Dropdown(
            label="Кем применено",
            options= [
                ft.dropdown.Option("Начальник академии"),
                ft.dropdown.Option("Заместитель начальника академии"),
                ft.dropdown.Option("Начальник факультета"),
                ft.dropdown.Option("Заместитель начальника факультета"),
                ft.dropdown.Option("Начальник курса")
            ],
            width=500)
        self.date_field = ft.TextField(label="Дата применения (ДД.ММ.ГГГГ)", width=245)
        self.order_number_field = ft.TextField(label="Номер приказа", width=250)
        self.date_order_field = ft.Row([self.date_field, self.order_number_field], spacing=5)
        # Кнопка для добавления взыскания
        self.add_penalty_button = ft.FilledButton("Добавить взыскание", on_click=self.add_penalty_click)

        # Таблица для отображения взысканий
        self.penalties_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Вид взыскания")),
                ft.DataColumn(ft.Text("Основание применения взыскания")),
                ft.DataColumn(ft.Text("Когда совершен проступок")),
                ft.DataColumn(ft.Text("Кем применено")),
                ft.DataColumn(ft.Text("Дата применения")),
                ft.DataColumn(ft.Text("Номер приказа")),
            ],
            rows=[]
        )

        # Кнопка для возврата на главную страницу
        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        self.controls = [
            ft.Text("Добавление взысканий", size=20, weight="bold"),
            self.student_search_field,
            self.student_dropdown,
            self.penalty_type_field,
            self.reason_field,
            self.date_reason_field,
            self.issued_by_field,
            self.date_order_field,
            self.add_penalty_button,
            ft.Divider(),
            self.penalties_table,
            self.back_button
        ]

        # Переменная для хранения выбранного курсанта
        self.selected_student_id = None

    def update_student_dropdown(self, e):
        search_text = self.student_search_field.value.strip()
        if search_text:
            # Ищем курсантов по части ФИО
            students = search_students_by_name_part(search_text)
            if students:
                # Обновляем опции выпадающего списка
                self.student_dropdown.options = [
                    ft.dropdown.Option(
                        text=f"{student[1]} {student[2]} {student[3]}",
                        key=str(student[0])  # Используем ID курсанта как ключ
                    )
                    for student in students
                ]
                self.student_dropdown.visible = True  # Показываем выпадающий список
            else:
                self.student_dropdown.options = []
                self.student_dropdown.visible = False  # Скрываем выпадающий список, если нет результатов
        else:
            # Если поле поиска пустое, очищаем список и скрываем его
            self.student_dropdown.options = []
            self.student_dropdown.visible = False

        self._page.update()

    def select_student(self, e):
        # Получаем выбранного курсанта из выпадающего списка
        selected_student_key = self.student_dropdown.value
        if selected_student_key:
            self.selected_student_id = to_int(selected_student_key)
            # Обновляем поле ввода текстом выбранного курсанта
            selected_student_text = next(
                option.text for option in self.student_dropdown.options
                if option.key == selected_student_key
            )
            self.student_search_field.value = selected_student_text
            self.student_dropdown.visible = False  # Скрываем выпадающий список после выбора

            # Обновляем таблицу с взысканиями для выбранного курсанта
            self.update_penalties_table(self.selected_student_id)

            # Показываем сообщение о выборе курсанта
            show_snack(self._page, ft.Text(f"Выбран курсант: {selected_student_text}"))
            self._page.update()

    def add_penalty_click(self, e):
        if not self.selected_student_id:
            show_snack(self._page, ft.Text("Выберите курсанта"))
            self._page.update()
            return

        
        penalty_type = self.penalty_type_field.value
        reason = self.reason_field.value
        date_reason = self.date_reason_field.value
        issued_by = self.issued_by_field.value
        date_str = self.date_field.value
        order_number = self.order_number_field.value

        if not date_str or not penalty_type or not issued_by or not reason:
            show_snack(self._page, ft.Text("Заполните все поля"))
            self._page.update()
            return

        # Преобразуем дату из ДД.ММ.ГГГГ в ГГГГ-ММ-ДД
        try:
            date_obj = datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")
            date_r_obj = datetime.strptime(date_reason, "%d.%m.%Y").strftime("%Y-%m-%d")
        except ValueError:
            show_snack(self._page, ft.Text("Некорректный формат даты. Используйте ДД.ММ.ГГГГ"))
            self._page.update()
            return

        # Добавляем взыскание в базу данных
        add_penalty(self.selected_student_id, penalty_type, reason, date_r_obj, issued_by, date_obj, order_number)

        # Обновляем таблицу с взысканиями
        self.update_penalties_table(self.selected_student_id)

        # Очищаем поля ввода
        self.penalty_type_field.value = ""
        self.reason_field.value = ""
        self.date_reason_field.value = ""
        self.issued_by_field.value = ""
        self.date_field.value = ""
        self.order_number_field.value = ""

        show_snack(self._page, ft.Text("Взыскание успешно добавлено"))
        self._page.update()

    def update_penalties_table(self, student_id):
        # Получаем взыскания для выбранного курсанта
        penalties = get_penalties_by_student(student_id)

        # Очищаем таблицу и добавляем взыскания
        self.penalties_table.rows = []
        for penalty in penalties:
            # Преобразуем дату из ГГГГ-ММ-ДД в ДД.ММ.ГГГГ для отображения
            date = datetime.strptime(penalty[4], "%Y-%m-%d").strftime("%d.%m.%Y")
            date_reason = datetime.strptime(penalty[2], "%Y-%m-%d").strftime("%d.%m.%Y")
            self.penalties_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(penalty[0])),
                        ft.DataCell(ft.Text(penalty[1])),
                        ft.DataCell(ft.Text(date_reason)),
                        ft.DataCell(ft.Text(penalty[3])),
                        ft.DataCell(ft.Text(date)),
                        ft.DataCell(ft.Text(penalty[5])),
                    ]
                )
            )

        self._page.update()

    def back_click(self, e):
        shell.navigate(self._page, "VprWorkPage")
