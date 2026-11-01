
# tkinter используется только для диалога выбора пути сохранения файлов;
# импорт выполняется лениво внутри методов, чтобы приложение запускалось
# даже на системах без установленной среды X11/tkinter.
from datetime import datetime

import flet as ft

# Слой репозиториев: UI больше не пишет SQL напрямую (см. repositories.py)
import repositories as repo
from database import (
    get_subjects_by_name_part,
    log_action,
)
from utils import session_get, show_snack

from pages import shell


class StudiWorkPage(ft.Column):
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
        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        self.controls = [
            ft.Text("Учебная работа", size=20, weight="bold"),
            self.back_button    
        ]

    # Обработчик нажатия кнопки "Назад" 
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
        shell.back_to_app(self._page)

class VprWorkPage(ft.Column):
    def __init__(self, page, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO)
        self._page = page

        self.add_encouragement_button = ft.FilledButton("Добавить поощрение", width=300, on_click=self.encouragement_click)
        self.add_penalty_button = ft.FilledButton("Добавить взыскание", width=300, on_click=self.penalty_click)

        # Кнопка для возврата на главную страницу
        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        self.controls = [
            ft.Text("Военно-политическая работа", size=20, weight="bold"),
            self.add_encouragement_button,
            self.add_penalty_button,
            self.back_button
        ]

    # Обработчик нажатия кнопки "Добавить поощрение"
    def encouragement_click(self, e):
        shell.navigate(self._page, "EncouragementWorkPage")

    # Обработчик нажатия кнопки "Добавить взыскание"
    def penalty_click(self, e):
        shell.navigate(self._page, "PenaltyWorkPage")

    # Обработчик нажатия кнопки "Назад"
    def back_click(self, e):
        shell.back_to_app(self._page)

class SessionResultsPage(ft.Column):
    def __init__(self, page, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO)
        self._page = page

        # Поле для ввода группы с автодополнением
        self.group_search_field = ft.TextField(
            label="Введите название группы",
            width=300,
            on_change=self.update_group_dropdown
        )

        # Выпадающий список для отображения найденных групп
        self.group_dropdown = ft.Dropdown(
            width=300,
            options=[],  # Начально пустой список
            visible=False,  # Скрыт по умолчанию
            on_select=self.select_group
        )

        # Поле для ввода предмета с автодополнением
        self.subject_search_field = ft.TextField(
            label="Введите название предмета",
            width=300,
            on_change=self.update_subject_dropdown
        )

        # Выпадающий список для отображения найденных предметов
        self.subject_dropdown = ft.Dropdown(
            width=300,
            options=[],  # Начально пустой список
            visible=False,  # Скрыт по умолчанию
            on_select=self.select_subject
        )

        # Поля для выбора типа экзамена
        self.type_exam_field = ft.Dropdown(
            label="Тип зачетной единицы",
            options=[
                ft.dropdown.Option("Экзамен"),
                ft.dropdown.Option("Зачет с оценкой"),
                ft.dropdown.Option("Зачет без оценки")
            ],
            width=300
        )

        # Поля для выбора даты, номера ведомости и семестра
        self.date_field = ft.TextField(label="Дата (ДД.ММ.ГГГГ)", width=300)
        self.statement_number_field = ft.TextField(label="Номер ведомости", width=300)
        self.statement_tip_field = ft.Dropdown(
            label="Тип ведомости",
            options=[
                ft.dropdown.Option("Первая"),
                ft.dropdown.Option("Повторная 1"),
                ft.dropdown.Option("Повторная 2"),
                ft.dropdown.Option("Индивидуальная")
            ],
            width=300
        )
        self.semester_field = ft.Dropdown(
            label="Семестр", 
            options=[ft.dropdown.Option(str(i)) for i in range(1, 13)], 
            width=300
        )
        self.show_students_button = ft.FilledButton("Выставить оценки", on_click=self.show_students_click)

        self.students_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("№")),
                ft.DataColumn(ft.Text("ФИО")),
                ft.DataColumn(ft.Text("Допуск")),
                ft.DataColumn(ft.Text("Присутствие")),
                ft.DataColumn(ft.Text("Оценка")),
            ],
            rows=[],
            data_row_min_height=55
        )

        # Кнопка для сохранения результатов
        self.save_button = ft.FilledButton("Сохранить", on_click=self.save_results_click)
        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        self.controls = [
            ft.Text("Результаты сессии", size=20, weight="bold"),
            self.group_search_field,
            self.group_dropdown,
            self.subject_search_field,
            self.subject_dropdown,
            self.type_exam_field,
            self.date_field,
            self.statement_number_field,
            self.statement_tip_field,
            self.semester_field,
            self.show_students_button,
            ft.Divider(),
            self.students_table,
            ft.Row([self.save_button, self.back_button])
        ]

        # Переменная для хранения выбранной группы
        self.selected_group = None
        # Переменная для хранения выбранного предмета
        self.selected_subject = None

    def check_statement_exists(self, group_name, sabject_name, date):
        return repo.count_session_results(group_name, sabject_name, date) > 0

    def update_group_dropdown(self, e):
        search_text = self.group_search_field.value.strip()
        if search_text:
            # Ищем группы по части названия
            groups = self.get_groups_by_name_part(search_text)
            if groups:
                # Обновляем опции выпадающего списка
                self.group_dropdown.options = [
                    ft.dropdown.Option(group) for group in groups
                ]
                self.group_dropdown.visible = True  # Показываем выпадающий список
            else:
                self.group_dropdown.options = []
                self.group_dropdown.visible = False  # Скрываем выпадающий список, если нет результатов
        else:
            # Если поле поиска пустое, очищаем список и скрываем его
            self.group_dropdown.options = []
            self.group_dropdown.visible = False

        self._page.update()

    def select_group(self, e):
        # Получаем выбранную группу из выпадающего списка
        selected_group = self.group_dropdown.value
        if selected_group:
            self.selected_group = selected_group
            # Обновляем поле ввода текстом выбранной группы
            self.group_search_field.value = selected_group
            self.group_dropdown.visible = False  # Скрываем выпадающий список после выбора

            # Показываем сообщение о выборе группы
            show_snack(self._page, ft.Text(f"Выбрана группа: {selected_group}"))
            self._page.update()

    def update_subject_dropdown(self, e):
        search_text = self.subject_search_field.value.strip()
        if search_text:
            # Ищем предметы по части названия
            subjects = get_subjects_by_name_part(search_text)
            if subjects:
                # Обновляем опции выпадающего списка
                self.subject_dropdown.options = [
                    ft.dropdown.Option(subject[1]) for subject in subjects
                ]
                self.subject_dropdown.visible = True  # Показываем выпадающий список
            else:
                self.subject_dropdown.options = []
                self.subject_dropdown.visible = False  # Скрываем выпадающий список, если нет результатов
        else:
            # Если поле поиска пустое, очищаем список и скрываем его
            self.subject_dropdown.options = []
            self.subject_dropdown.visible = False

        self._page.update()

    def select_subject(self, e):
        # Получаем выбранный предмет из выпадающего списка
        selected_subject = self.subject_dropdown.value
        if selected_subject:
            self.selected_subject = selected_subject
            # Обновляем поле ввода текстом выбранного предмета
            self.subject_search_field.value = selected_subject
            self.subject_dropdown.visible = False  # Скрываем выпадающий список после выбора

            # Показываем сообщение о выборе предмета
            show_snack(self._page, ft.Text(f"Выбран предмет: {selected_subject}"))
            self._page.update()

    def get_groups_by_name_part(self, search_text):
        # Получаем список групп, которые содержат введенный текст
        return repo.list_groups_like(search_text)

    def show_students_click(self, e):
        if not self.selected_group:
            show_snack(self._page, ft.Text("Выберите группу"))
            self._page.update()
            return

        if not self.selected_subject:
            show_snack(self._page, ft.Text("Выберите предмет"))
            self._page.update()
            return

        statement_tip = self.statement_tip_field.value
        semester = self.semester_field.value
        typ_exam = self.type_exam_field.value

        if not statement_tip or not semester:
            show_snack(self._page, ft.Text("Заполните все поля"))
            self._page.update()
            return

        # Преобразуем дату из ДД.ММ.ГГГГ в ГГГГ-ММ-ДД
        try:
            date_obj = datetime.strptime(self.date_field.value, "%d.%m.%Y").strftime("%Y-%m-%d")
        except ValueError:
            show_snack(self._page, ft.Text("Некорректный формат даты. Используйте ДД.ММ.ГГГГ"))
            self._page.update()
            return

        # Проверяем, существует ли уже ведомость с такими же параметрами
        if statement_tip != "Индивидуальная" and self.check_statement_exists(self.selected_group, self.selected_subject, date_obj):
            show_snack(self._page, ft.Text("Ведомость с такими параметрами уже существует для этой группы и даты"))
            self._page.update()
            return

        # Получаем список курсантов выбранной группы
        students = repo.list_students_by_group(self.selected_group)

        # Очищаем таблицу
        self.students_table.rows = []

        # В зависимости от типа ведомости фильтруем студентов
        if statement_tip == "Первая":
            # Показываем всех студентов
            filtered_students = students
        elif statement_tip == "Повторная 1":
            # Показываем только тех, кто получил 2 или не присутствовал на экзамене по первой ведомости
            filtered_students = []
            for student in students:
                student_id = student[0]
                result = repo.get_first_statement_result(student_id, self.selected_subject, typ_exam, semester)
                if result and (result[0] == "2" or result[1] == "Отсутствовал" or result[2] == "Не допущен"):
                    filtered_students.append(student)
        elif statement_tip == "Повторная 2":
            # Показываем только тех, кто получил 2 или не присутствовал на экзамене по первой и повторной 1 ведомости
            filtered_students = []
            for student in students:
                student_id = student[0]
                result = repo.get_statement_results_first_and_repeat1(student_id, self.selected_subject, typ_exam, semester)
                if result and all((r[0] == "2" or r[1] == "Отсутствовал" or r[2] == "Не допущен") for r in result):
                    filtered_students.append(student)
        elif statement_tip == "Индивидуальная":
            # Показываем всех студентов, но добавляем колонку с чекбоксами
            filtered_students = students
        else:
            filtered_students = []

        # Добавляем студентов в таблицу
        for i, student in enumerate(filtered_students):
            # Поле для допуска
            admission_dropdown = ft.Dropdown(
                options=[
                    ft.dropdown.Option("Допущен"),
                    ft.dropdown.Option("Не допущен")
                ],
                value="Допущен",
                on_select=lambda e, row_index=i: self.update_grade_field_state(e, row_index)
            )

            # Поле для присутствия
            attendance_dropdown = ft.Dropdown(
                options=[
                    ft.dropdown.Option("Присутствовал"),
                    ft.dropdown.Option("Отсутствовал")
                ],
                value="Присутствовал",
                on_select=lambda e, row_index=i: self.update_grade_field_state(e, row_index)
            )

            # Поле для оценки
            grade_dropdown = ft.Dropdown(
                options=[
                    ft.dropdown.Option("5"),
                    ft.dropdown.Option("4"),
                    ft.dropdown.Option("3"),
                    ft.dropdown.Option("2"),
                ],
                disabled=False  # Изначально поле активно
            )

            # Если тип ведомости "Индивидуальная", добавляем чекбокс
            if statement_tip == "Индивидуальная":
                checkbox = ft.Checkbox(value=False)
                row_cells = [
                    ft.DataCell(ft.Text(str(i + 1))),  # Номер по порядку
                    ft.DataCell(ft.Text(f"{student[1]} {student[2]} {student[3]}")),  # ФИО
                    ft.DataCell(ft.Container(admission_dropdown, width=150)),  # Допуск
                    ft.DataCell(ft.Container(attendance_dropdown, width=150)),  # Присутствие
                    ft.DataCell(ft.Container(grade_dropdown, width=100)),  # Оценка
                    ft.DataCell(checkbox)  # Чекбокс
                ]
            else:
                row_cells = [
                    ft.DataCell(ft.Text(str(i + 1))),  # Номер по порядку
                    ft.DataCell(ft.Text(f"{student[1]} {student[2]} {student[3]}")),  # ФИО
                    ft.DataCell(ft.Container(admission_dropdown, width=150)),  # Допуск
                    ft.DataCell(ft.Container(attendance_dropdown, width=150)),  # Присутствие
                    ft.DataCell(ft.Container(grade_dropdown, width=100)),  # Оценка
                ]

            self.students_table.rows.append(ft.DataRow(cells=row_cells))

        # Если тип ведомости "Индивидуальная", добавляем колонку с чекбоксами
        if statement_tip == "Индивидуальная":
            self.students_table.columns.append(ft.DataColumn(ft.Text("Выбрать")))
        else:
            # Убираем колонку с чекбоксами, если она была добавлена ранее
            if len(self.students_table.columns) > 5:
                self.students_table.columns.pop()

        self._page.update()

    def update_grade_field_state(self, e, row_index):
        # Получаем строку по индексу
        row = self.students_table.rows[row_index]
        
        # Получаем значения из Dropdown для допуска и присутствия
        admission_dropdown = row.cells[2].content.content
        attendance_dropdown = row.cells[3].content.content
        
        # Получаем значение из Dropdown для оценки
        grade_dropdown = row.cells[4].content.content

        # Если студент допущен и присутствовал, разблокируем поле оценки
        if admission_dropdown.value == "Допущен" and attendance_dropdown.value == "Присутствовал":
            grade_dropdown.disabled = False
        else:
            grade_dropdown.disabled = True

        self._page.update()

    def save_results_click(self, e):
        if not self.selected_group:
            show_snack(self._page, ft.Text("Выберите группу"))
            self._page.update()
            return

        if not self.selected_subject:
            show_snack(self._page, ft.Text("Выберите предмет"))
            self._page.update()
            return

        date_str = self.date_field.value
        statement_number = self.statement_number_field.value
        statement_tip = self.statement_tip_field.value
        semester = self.semester_field.value
        type_exam = self.type_exam_field.value

        if not date_str or not statement_number or not semester or not statement_tip or not type_exam:
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

        # Сохраняем результаты для каждого курсанта
        for row in self.students_table.rows:
            student_name = row.cells[1].content.value  # Получаем ФИО курсанта

            # Если тип ведомости "Индивидуальная", проверяем чекбокс
            if statement_tip == "Индивидуальная":
                checkbox = row.cells[5].content.value  # Получаем значение чекбокса
                if not checkbox:  # Если чекбокс не отмечен, пропускаем студента
                    continue

            # Извлекаем Dropdown из Container
            admission_container = row.cells[2].content
            admission_dropdown = admission_container.content  # Получаем Dropdown для допуска

            attendance_container = row.cells[3].content
            attendance_dropdown = attendance_container.content  # Получаем Dropdown для присутствия

            grade_container = row.cells[4].content
            grade_dropdown = grade_container.content  # Получаем Dropdown для оценки

            admission = admission_dropdown.value  # Допуск
            attendance = attendance_dropdown.value  # Присутствие
            grade = grade_dropdown.value  # Оценка

            # Проверяем, что если студент допущен и присутствовал, то оценка должна быть заполнена
            if admission == "Допущен" and attendance == "Присутствовал" and not grade:
                show_snack(self._page, ft.Text(f"Для студента {student_name} не указана оценка"))
                self._page.update()
                return

            # Получаем ID курсанта по ФИО
            student_id = repo.find_student_id_by_full_name(student_name)
            if student_id:
                # Проверяем, есть ли уже запись с таким же номером и типом ведомости для этого курсанта и предмета
                if repo.session_result_exists(student_id, self.selected_subject, type_exam, statement_number, statement_tip):
                    # Если запись уже существует, пропускаем сохранение и выводим сообщение
                    show_snack(self._page, ft.Text(f"Уже есть запись с таким номером и типом ведомости по предмету {self.selected_subject}"))
                    self._page.update()
                    continue

                # Если записи нет, сохраняем результат
                repo.add_session_result(self.selected_group, self.selected_subject, type_exam, date_obj, statement_number, statement_tip, student_id, admission, attendance, grade, semester)
                session_get(log_action(self._page, "username"), f"Добавлен результат для группы {self.selected_group} по предмету {self.selected_subject} типа {type_exam} даты {date_obj} номера ведомости {statement_number} типа {statement_tip} семестра {semester}")
        show_snack(self._page, ft.Text("Результаты успешно сохранены"))
        self._page.update()

    def back_click(self, e):
        shell.back_to_app(self._page)
