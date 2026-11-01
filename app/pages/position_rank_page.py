
# tkinter используется только для диалога выбора пути сохранения файлов;
# импорт выполняется лениво внутри методов, чтобы приложение запускалось
# даже на системах без установленной среды X11/tkinter.
from datetime import datetime

import flet as ft

# Слой репозиториев: UI больше не пишет SQL напрямую (см. repositories.py)
import repositories as repo
from access import PermissionDeniedError
from database import (
    log_action,
    search_students_by_name_part,
)
from utils import session_get, show_snack, to_int

from pages import shell


def _deny_position_snack(page):
    """B-1: единый ответ на отказ серверного слоя прав."""
    show_snack(page, "Недостаточно прав: действие доступно только администратору")
    page.update()


class PositionChangePage(ft.Column):
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
            options=[],  # Начально пустой список
            visible=False,  # Скрыт по умолчанию
            on_select=self.select_student
        )

        # Поля для ввода данных о должности
        self.position_field = ft.Dropdown(
            label="Должность",
            options=[
                ft.dropdown.Option("Старшина курса"),
                ft.dropdown.Option("Заместитель командира взвода"),
                ft.dropdown.Option("Командир 1 отделения"),
                ft.dropdown.Option("Командир 2 отделения"),
                ft.dropdown.Option("Командир 3 отделения")
            ], 
            width=500)

        self.assigned_by_field = ft.Dropdown(
            label="Кем присвоено",
            options=[
                ft.dropdown.Option("НВМедА")
            ], 
            width=500)
        
        self.date_field = ft.TextField(label="Дата (ДД.ММ.ГГГГ)", width=245)
        self.order_number_field = ft.TextField(label="Номер приказа", width=250)

        # Кнопка для изменения должности
        self.change_position_button = ft.FilledButton("Изменить должность", on_click=self.change_position_click)

        # Таблица для отображения истории изменений должностей
        self.position_history_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Должность")),
                ft.DataColumn(ft.Text("Кем присвоено")),
                ft.DataColumn(ft.Text("Дата")),
                ft.DataColumn(ft.Text("Номер приказа")),
            ],
            rows=[]
        )
        self.date_order_number_field = ft.Row([self.date_field, self.order_number_field], spacing=5)
        # Кнопка для возврата на главную страницу
        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        self.controls = [
            ft.Text("Изменение должности", size=20, weight="bold"),
            self.student_search_field,
            self.student_dropdown,
            self.position_field,
            self.assigned_by_field,
            self.date_order_number_field,
            self.change_position_button,
            ft.Divider(),
            self.position_history_table,
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

            # Обновляем таблицу с историей изменений должностей для выбранного курсанта
            self.update_position_history_table(self.selected_student_id)

            # Показываем сообщение о выборе курсанта
            show_snack(self._page, ft.Text(f"Выбран курсант: {selected_student_text}"))
            self._page.update()

    def change_position_click(self, e):
        if not self.selected_student_id:
            show_snack(self._page, ft.Text("Выберите курсанта"))
            self._page.update()
            return

        position = self.position_field.value
        date_str = self.date_field.value
        assigned_by = self.assigned_by_field.value
        order_number = self.order_number_field.value

        if not position or not date_str or not assigned_by or not order_number:
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

        # Добавляем запись об изменении должности в базу данных
        # B-1: серверная проверка прав — роль из сессии
        try:
            repo.add_position(self.selected_student_id, position, assigned_by,
                              date_obj, order_number,
                              actor_role=session_get(self._page, "role"))
        except PermissionDeniedError:
            _deny_position_snack(self._page)
            return
        session_get(log_action(self._page, "username"), f"Добавлено изменение должности для студента {self.selected_student_id} c {self.position_history_table.rows[-1][0]} на {position}")

        # Обновляем таблицу с историей изменений должностей
        self.update_position_history_table(self.selected_student_id)

        # Очищаем поля ввода
        self.position_field.value = ""
        self.date_field.value = ""
        self.assigned_by_field.value = ""
        self.order_number_field.value = ""

        show_snack(self._page, ft.Text("Должность успешно изменена"))
        self._page.update()

    def update_position_history_table(self, student_id):
        # Получаем историю изменений должностей для курсанта
        history = repo.get_position_history(student_id)

        # Очищаем таблицу и добавляем записи
        self.position_history_table.rows = []
        for record in history:
            # Преобразуем дату из ГГГГ-ММ-ДД в ДД.ММ.ГГГГ для отображения
            date_display = datetime.strptime(record[2], "%Y-%m-%d").strftime("%d.%m.%Y")
            self.position_history_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(record[0])),  # Должность
                        ft.DataCell(ft.Text(record[1])),  # Кем присвоено
                        ft.DataCell(ft.Text(date_display)),  # Дата
                        ft.DataCell(ft.Text(record[3])),  # Номер приказа
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
        shell.navigate(self._page, "KadriWorkPage")

class RankChangePage(ft.Column):
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
            options=[],  # Начально пустой список
            visible=False,  # Скрыт по умолчанию
            on_select=self.select_student
        )

        # Поля для ввода данных о должности
        self.rank_field = ft.Dropdown(
            label="Звание",
            options=[
                ft.dropdown.Option("Ефрейтор"),
                ft.dropdown.Option("Младший сержант"),
                ft.dropdown.Option("Сержант"),
                ft.dropdown.Option("Старший сержант"),
                ft.dropdown.Option("Старшина"),
                ft.dropdown.Option("Прапорщик"),
                ft.dropdown.Option("Старший прапорщик"),
                ft.dropdown.Option("Младший лейтенант"),
                ft.dropdown.Option("Лейтенант"),
                ft.dropdown.Option("Старший лейтенант"),
                ft.dropdown.Option("Капитан"),
                ft.dropdown.Option("Майор"),
                ft.dropdown.Option("Подполковник"),
                ft.dropdown.Option("Полковник")
            ], 
            width=500)
    
        self.assigned_by_field = ft.Dropdown(
            label="Кем присвоено",
            options=[
                ft.dropdown.Option("НВМедА")
            ], 
            width=500)
        
        self.date_field = ft.TextField(label="Дата (ДД.ММ.ГГГГ)", width=245)
        self.order_number_field = ft.TextField(label="Номер приказа", width=250)
        self.date_order_number_field = ft.Row([self.date_field, self.order_number_field], spacing=5)

        # Кнопка для изменения звания
        self.change_position_button = ft.FilledButton("Изменить звание", on_click=self.change_position_click)

        # Таблица для отображения истории изменений званий
        self.rank_history_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Дата")),
                ft.DataColumn(ft.Text("Звание")),
                ft.DataColumn(ft.Text("Кем присвоено")),
                ft.DataColumn(ft.Text("Номер приказа")),
            ],
            rows=[]
        )

        # Кнопка для возврата на главную страницу
        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        self.controls = [
            ft.Text("Изменение звания", size=20, weight="bold"),
            self.student_search_field,
            self.student_dropdown,
            self.rank_field,
            self.assigned_by_field,
            self.date_order_number_field,
            self.change_position_button,
            ft.Divider(),
            self.rank_history_table,
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

            # Обновляем таблицу с историей изменений должностей для выбранного курсанта
            self.update_rank_history_table(self.selected_student_id)

            # Показываем сообщение о выборе курсанта
            show_snack(self._page, ft.Text(f"Выбран курсант: {selected_student_text}"))
            self._page.update()

    def change_position_click(self, e):
        if not self.selected_student_id:
            show_snack(self._page, ft.Text("Выберите курсанта"))
            self._page.update()
            return

        rank = self.rank_field.value
        assigned_by = self.assigned_by_field.value
        date_str = self.date_field.value
        order_number = self.order_number_field.value

        if not rank or not date_str or not assigned_by or not order_number:
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

        # Добавляем запись об изменении звания в базу данных
        # B-1: серверная проверка прав — роль из сессии
        try:
            repo.add_rank(self.selected_student_id, rank, assigned_by,
                          date_obj, order_number,
                          actor_role=session_get(self._page, "role"))
        except PermissionDeniedError:
            _deny_position_snack(self._page)
            return
        session_get(log_action(self._page, "username"), f"Добавлено изменение должности для студента {self.selected_student_id} c {self.rank_history_table.rows[-1][0]} на {rank}")

        # Обновляем таблицу с историей изменений должностей
        self.update_rank_history_table(self.selected_student_id)

        # Очищаем поля ввода
        self.rank_field.value = ""
        self.assigned_by_field.value = ""
        self.date_field.value = ""
        self.order_number_field.value = ""

        show_snack(self._page, ft.Text("Звание успешно изменено"))
        self._page.update()

    def update_rank_history_table(self, student_id):
        # Получаем историю изменений званий для курсанта
        # (исправлено: ранее запрос ошибочно читал колонку position из rank_history)
        history = repo.get_rank_history(student_id)

        # Очищаем таблицу и добавляем записи
        self.rank_history_table.rows = []
        for record in history:
            # Преобразуем дату из ГГГГ-ММ-ДД в ДД.ММ.ГГГГ для отображения
            date_display = datetime.strptime(record[2], "%Y-%m-%d").strftime("%d.%m.%Y")
            self.rank_history_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(record[0])),  # Должность
                        ft.DataCell(ft.Text(record[1])),  # Кем присвоено
                        ft.DataCell(ft.Text(date_display)),  # Дата
                        ft.DataCell(ft.Text(record[3])),  # Номер приказа
                    ]
                )
            )

        self._page.update()

    def back_click(self, e):
        shell.navigate(self._page, "KadriWorkPage")
