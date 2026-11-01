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
from utils import session_get, session_set, session_clear, show_snack


class PremiaWorkPage(ft.Column):
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

        # Поля для выбора курса, дат и семестра
        self.course_dropdown = ft.Dropdown(
            label="Выберите курс",
            options=[ft.dropdown.Option(str(i)) for i in range(2021, 2026)],  # Предположим, что курсов 5
            width=300
        )
        self.start_date_field = ft.TextField(label="Дата начала (ДД.ММ.ГГГГ)", width=300)
        self.end_date_field = ft.TextField(label="Дата окончания (ДД.ММ.ГГГГ)", width=300)
        self.semester_dropdown = ft.Dropdown(
            label="Выберите семестр",
            options=[ft.dropdown.Option(str(i)) for i in range(1, 13)],  # Предположим, что семестров 12
            width=300
        )
        self.show_results_button = ft.FilledButton("Показать результаты", on_click=self.show_results_click)

        # Кнопка для экспорта в Excel
        self.export_button = ft.FilledButton("Экспорт в Excel", on_click=self.export_to_excel)

        # Таблица для отображения результатов
        self.results_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("№")),
                ft.DataColumn(ft.Text("Воинское звание")),
                ft.DataColumn(ft.Text("ФИО")),
                ft.DataColumn(ft.Text("Личный номер")),
                ft.DataColumn(ft.Text("Должность")),
                ft.DataColumn(ft.Text("Наличие взыскания")),
                ft.DataColumn(ft.Text("Результат сессии")),
                ft.DataColumn(ft.Text("Размер премии")),
                ft.DataColumn(ft.Text("Причина изменения премии")),  # Новая колонка
            ],
            rows=[]
        )

        # Кнопка для возврата на главную страницу
        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        self.controls = [
            ft.Text("Премии", size=20, weight="bold"),
            self.course_dropdown,
            self.start_date_field,
            self.end_date_field,
            self.semester_dropdown,
            self.show_results_button,
            self.export_button,  # Добавляем кнопку экспорта
            ft.Divider(),
            self.results_table,
            self.back_button
        ]

    def show_results_click(self, e):
        course = self.course_dropdown.value
        start_date_str = self.start_date_field.value
        end_date_str = self.end_date_field.value
        semester = self.semester_dropdown.value

        if not course or not start_date_str or not end_date_str or not semester:
            show_snack(self._page, ft.Text("Заполните все поля"))
            self._page.update()
            return

        # Преобразуем даты из DD.MM.YYYY в YYYY-MM-DD
        try:
            start_date = datetime.strptime(start_date_str, "%d.%m.%Y").strftime("%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%d.%m.%Y").strftime("%Y-%m-%d")
        except ValueError:
            show_snack(self._page, ft.Text("Некорректный формат даты. Используйте ДД.ММ.ГГГГ"))
            self._page.update()
            return

        # Получаем список курсантов выбранного курса
        students = repo.list_students_by_course(course)

        # Очищаем таблицу и добавляем результаты
        self.results_table.rows = []
        for i, student in enumerate(students):
            student_id = student[0]
            full_name = f"{student[1]} {student[2]} {student[3]}"
            personal_number = student[4]
            post = student[5]

            # Получаем последнюю должность из таблицы position_history
            last_position = repo.get_last_position_row(student_id)

            # Получаем последнее звание из таблицы rank_history
            last_rank = repo.get_last_rank(student_id)

            if last_position and last_position[0] == "Заместитель командира взвода":
                formated_post = "заместителя командира взвода"
            elif last_position and last_position[0] == "Командир 1 отделения":
                formated_post = "командира 1 отделения"
            elif last_position and last_position[0] == "Командир 2 отделения":
                formated_post = "командира 2 отделения"
            elif last_position and last_position[0] == "Командир 3 отделения":
                formated_post = "командира 3 отделения"
            else:
                formated_post = None

            # Получаем взыскания для курсанта за выбранный период
            penalties = repo.list_penalties_in_period(student_id, start_date, end_date)

            # Формируем текст с выговорами
            penalty_text = ", ".join([f"{p[0]} от {p[1]} (от {datetime.strptime(p[2], '%Y-%m-%d').strftime('%d.%m.%Y')})" for p in penalties]) if penalties else "Нет"

            # Проверяем, есть ли хотя бы один предмет, по которому последняя оценка отсутствует (не допущен или отсутствовал) или равна 2
            # Проверяем по всем семестрам
            has_failed = repo.has_failed_subjects(student_id)

            # Если есть хотя бы один предмет без оценки или с оценкой 2, премия равна 1
            if has_failed:
                premia_size = 1
                premia_reason = "Не допущен, отсутствовал или оценка 2 по одному из предметов"
            else:
                # Получаем результаты сессии для выбранного семестра, учитывая только последнюю оценку по каждому предмету
                session_results = repo.list_latest_session_results(student_id, semester)

                # Если есть результаты, берем минимальную оценку из последних оценок
                if session_results:
                    grades = [result[1] for result in session_results if result[1] is not None]
                    min_grade = min(grades) if grades else None
                else:
                    min_grade = None

                # Определяем результат сессии
                if min_grade == "2":
                    session_result = "неудовлетворительно"
                elif min_grade == "3":
                    session_result = "удовлетворительно"
                elif min_grade == "4":
                    session_result = "хорошо"
                elif min_grade == "5":
                    session_result = "отлично"
                else:
                    session_result = "нет данных"

                # Определяем размер премии и причину изменения
                premia_size = 0
                premia_reason = ""

                if min_grade == "2":
                    premia_size = 1
                    premia_reason = "Неудовлетворительный результат сессии"
                elif session_result == "нет данных":
                    premia_size = "???"
                    premia_reason = "Нет данных о сессии"
                elif penalties:
                    premia_size = 1
                    premia_reason = "Наличие дисциплинарного взыскания"
                elif last_position and last_position[0].lower() not in ["курсант", "слушатель"]:
                    premia_size = 25
                    premia_reason = f"Занимает должность {formated_post} (приказ НВМедА № {last_position[2]} от {datetime.strptime(last_position[1], '%Y-%m-%d').strftime('%d.%m.%Y')}г.)"
                elif session_result == "неудовлетворительно":
                    premia_size = 1
                elif session_result == "удовлетворительно":
                    premia_size = 5
                elif session_result == "хорошо":
                    premia_size = 15
                elif session_result == "отлично":
                    premia_size = 25

            # Добавляем строку в таблицу
            self.results_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(i + 1))),  # Номер по порядку
                        ft.DataCell(ft.Text(last_rank)),  # Воинское звание
                        ft.DataCell(ft.Text(full_name)),  # ФИО
                        ft.DataCell(ft.Text(personal_number)),  # Личный номер
                        ft.DataCell(ft.Text(post)),  # Должность
                        ft.DataCell(ft.Text(penalty_text)),  # Наличие взыскания
                        ft.DataCell(ft.Text(session_result if not has_failed else "неудовлетворительно")),  # Результат сессии
                        ft.DataCell(ft.Text(str(premia_size))),  # Размер премии
                        ft.DataCell(ft.Text(premia_reason)),  # Причина изменения премии
                    ]
                )
            )
            log_action(session_get(self._page, "username"), f"Созадана премия для курса {course} за семестр {semester} и период {start_date} - {end_date}")
        self._page.update()

    def export_to_excel(self, e):
        from tkinter import filedialog, Tk
        # Собираем данные из таблицы
        data = []
        for row in self.results_table.rows:
            data.append([cell.content.value for cell in row.cells])

        # Создаем DataFrame из данных
        df = pd.DataFrame(data, columns=[
            "№", "Воинское звание", "ФИО", "Личный номер", "Должность", 
            "Наличие взыскания", "Результат сессии", "Размер премии", "Причина изменения премии"
        ])

        # Используем tkinter для выбора пути сохранения файла
        root = Tk()
        root.withdraw()  # Скрываем основное окно tkinter
        root.attributes('-topmost', True)  # Окно поверх всех окон
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            title="Сохранить файл как"
        )

        if file_path:
            # Сохраняем DataFrame в Excel
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name="Премии")
                worksheet = writer.sheets["Премии"]

                # Настраиваем ширину столбцов в зависимости от содержимого
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = get_column_letter(column[0].column)  # Получаем букву столбца
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = (max_length + 2) * 1.2  # Добавляем небольшой отступ
                    worksheet.column_dimensions[column_letter].width = adjusted_width

            show_snack(self._page, ft.Text(f"Файл сохранен: {file_path}"))
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
        shell.back_to_app(self._page)
