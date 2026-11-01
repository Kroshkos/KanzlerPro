
# tkinter используется только для диалога выбора пути сохранения файлов;
# импорт выполняется лениво внутри методов, чтобы приложение запускалось
# даже на системах без установленной среды X11/tkinter.
from datetime import datetime

import flet as ft
import pandas as pd

# Слой репозиториев: UI больше не пишет SQL напрямую (см. repositories.py)
import repositories as repo
from database import (
    log_action,
)
from openpyxl.utils import get_column_letter
from utils import session_get, show_snack
from utils_logger import log_except

from pages import shell


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

    # ---------- Формула размера премии (BACKLOG T-3) ----------
    # Сама формула вынесена в чистый модуль pages.premia_calc (без Flet/БД),
    # чтобы её покрывали табличные тесты; здесь остаётся только сбор данных.

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

        # Пакетные выборки вместо N+1: 5 запросов на весь курс вместо
        # 4-5 запросов на каждого курсанта (см. repositories.map_*).
        ids = [s[0] for s in students]
        positions_map = repo.map_last_positions(ids)
        ranks_map = repo.map_last_ranks(ids)
        penalties_map = repo.map_penalties_in_period(ids, start_date, end_date)
        failed_ids = repo.map_failed_subjects(ids)
        session_map = repo.map_latest_session_results(ids, semester)

        # Таблица должностей/форм для причин — из чистого модуля (T-3)
        from pages import premia_calc

        # Очищаем таблицу и добавляем результаты
        self.results_table.rows = []
        for i, student in enumerate(students):
            student_id = student[0]
            full_name = f"{student[1]} {student[2]} {student[3]}"
            personal_number = student[4]
            post = student[5]

            # Последняя должность/звание из пакетных словарей
            # (кортеж (position, date, order_number) совместим со старым
            # форматом get_last_position_row)
            last_position = positions_map.get(student_id)
            # '' вместо None: ft.Text(None) в Flet 1.x падает (как и в
            # старой версии с get_last_rank -> None)
            last_rank = ranks_map.get(student_id, "") or ""

            # Получаем взыскания курсанта за выбранный период (из пакета)
            penalties = penalties_map.get(student_id, [])

            # Формируем текст с выговорами
            penalty_text = ", ".join([f"{p[0]} от {p[1]} (от {datetime.strptime(p[2], '%Y-%m-%d').strftime('%d.%m.%Y')})" for p in penalties]) if penalties else "Нет"

            # Проверяем, есть ли хотя бы один предмет, по которому последняя
            # оценка отсутствует (не допущен или отсутствовал) или равна 2
            # (батч map_failed_subjects по всем семестрам)
            has_failed = student_id in failed_ids

            # Результаты сессии за выбранный семестр из пакетной карты
            session_results = session_map.get(student_id, [])
            grades = [r[1] for r in session_results if r[1] is not None]
            min_grade = min(grades) if grades else None

            # Размер премии, причина и результат сессии — чистая формула
            # premia_calc.compute_premia (табличные тесты T-3). Дату приказа
            # передаём как есть (ГГГГ-ММ-ДД); форматирование — на уровне UI.
            premia_size, premia_reason, session_result = \
                premia_calc.compute_premia(
                    min_grade=min_grade,
                    has_penalties=bool(penalties),
                    last_position=last_position,
                    has_failed_subjects=has_failed,
                    has_session_results=bool(session_results))
            if "приказ НВМедА №" in premia_reason and last_position:
                premia_reason = premia_reason.replace(
                    last_position[1],
                    datetime.strptime(last_position[1],
                                      "%Y-%m-%d").strftime("%d.%m.%Y"))

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
        # Одна запись в журнал на весь расчёт (раньше log_action вызывался
        # внутри цикла — по строке лога на каждого курсанта).
        log_action(session_get(self._page, "username"),
                   f"Рассчитаны премии для курса {course} за семестр {semester} "
                   f"и период {start_date} - {end_date} ({len(students)} чел.)")
        self._page.update()

    def export_to_excel(self, e):
        from tkinter import Tk, filedialog
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
                            max_length = max(max_length, len(str(cell.value)))
                        except Exception:
                            log_except("premia_page: расчёт ширины колонки Excel")
                    adjusted_width = (max_length + 2) * 1.2  # Добавляем небольшой отступ
                    worksheet.column_dimensions[column_letter].width = adjusted_width

            show_snack(self._page, ft.Text(f"Файл сохранен: {file_path}"))
            self._page.update()

    def back_click(self, e):
        shell.back_to_app(self._page)
