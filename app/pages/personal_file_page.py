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
from utils import show_snack


class PersonalFilePage(ft.Column):
    def __init__(self, page):
        super().__init__()
        self._page = page
        self.scroll = True
        self.expand = True

        # Поле для поиска курсанта
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

        # Контейнер для отображения данных курсанта
        self.student_info_container = ft.Column()

        # Кнопка для возврата на главную страницу
        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        # Определяем порядок элементов, как в примере
        self.controls = [
            ft.Text("Личное дело курсанта", size=20, weight="bold"),
            self.student_search_field,
            self.student_dropdown,
            ft.Divider(),  # Добавляем разделитель
            self.student_info_container,
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
            self.selected_student_id = int(selected_student_key)
            # Обновляем поле ввода текстом выбранного курсанта
            selected_student_text = next(
                option.text for option in self.student_dropdown.options
                if option.key == selected_student_key
            )
            self.student_search_field.value = selected_student_text
            self.student_dropdown.visible = False  # Скрываем выпадающий список после выбора

            # Загружаем данные курсанта
            self.load_student_data(self.selected_student_id)

            # Показываем сообщение о выборе курсанта
            show_snack(self._page, ft.Text(f"Выбран курсант: {selected_student_text}"))
            self._page.update()

    def load_student_data(self, student_id):
        # Получаем данные курсанта из базы данных
        student_data = repo.get_student_full(student_id)

        if student_data:

            # Очищаем контейнер с данными
            self.student_info_container.controls.clear()

            # Добавляем заголовок "Личное дело курсанта"
            self.student_info_container.controls.append(
                ft.Text("ЛИЧНОЕ ДЕЛО", size=20, weight="bold", text_align="center")
            )

            # Функция для проверки корректности base64
            def is_valid_base64(base64_string):
                try:
                    base64.b64decode(base64_string, validate=True)
                    return True
                except (base64.binascii.Error, ValueError):
                    return False

            # Функция для исправления padding в base64
            def fix_base64_padding(base64_string):
                padding = len(base64_string) % 4
                if padding:
                    base64_string += '=' * (4 - padding)
                return base64_string

            # Создаем контейнер для фотографии
            photo_container = ft.Column()

            # Проверяем и добавляем фотографию
            if student_data[24]:  # Предполагаем, что photo_base64 находится в 23-м столбце
                base64_string = student_data[24].strip()  # Удаляем лишние пробелы и переносы

                if is_valid_base64(base64_string):
                    # В Flet >= 0.80 параметр src_base64 удалён: base64 передаётся
                    # через src в формате data-URI.
                    photo_container.controls.append(
                        ft.Image(
                            src=f"data:image/jpeg;base64,{base64_string}",
                            width=300,
                            height=400,
                            fit=ft.BoxFit.COVER,
                            border_radius=10,
                        )
                    )
                else:
                    base64_string = fix_base64_padding(base64_string)
                    if is_valid_base64(base64_string):
                        photo_container.controls.append(
                            ft.Image(
                                src=f"data:image/jpeg;base64,{base64_string}",
                                width=300,
                                height=400,
                                fit=ft.BoxFit.COVER,
                                border_radius=10,
                            )
                        )
                    else:
                        photo_container.controls.append(
                            ft.Text("Ошибка: некорректный формат изображения", color="red")
                        )
            else:
                photo_container.controls.append(
                    ft.Text("Фотография отсутствует", color="gray")
                )

            # Карточка с основными данными
            basic_data_card = ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("Основные данные", size=18, weight="bold"),
                            ft.DataTable(
                                columns=[
                                    ft.DataColumn(ft.Text("Поле", weight="bold")),
                                    ft.DataColumn(ft.Text("Значение", weight="bold")),
                                ],
                                rows=[
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(ft.Text("Фамилия:")),
                                            ft.DataCell(ft.Text(student_data[1])),
                                        ]
                                    ),
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(ft.Text("Имя:")),
                                            ft.DataCell(ft.Text(student_data[2])),
                                        ]
                                    ),
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(ft.Text("Отчество:")),
                                            ft.DataCell(ft.Text(student_data[3])),
                                        ]
                                    ),
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(ft.Text("Должность:")),
                                            ft.DataCell(ft.Text("Значение")),
                                        ]
                                    ),
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(ft.Text("Воинское звание:")),
                                            ft.DataCell(ft.Text("Значение")),
                                        ]
                                    ),
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(ft.Text("Учебная группа:")),
                                            ft.DataCell(ft.Text(student_data[5])),
                                        ]
                                    ),
                                ],
                            ),
                        ],
                        spacing=10,
                    ),
                    padding=10,
                ),
                elevation=5,
                margin=10,
            )

            reiting_card = ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.DataTable(
                                columns=[
                                    ft.DataColumn(ft.Text("Поле", weight="bold")),
                                    ft.DataColumn(ft.Text("Значение", weight="bold")),
                                ],
                                rows=[
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(ft.Text("Рейтинг:")),
                                            ft.DataCell(ft.Text("Значение")),
                                        ]
                                    ),
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(ft.Text("Позиция в рейтинге:")),
                                            ft.DataCell(ft.Text("Значение")),
                                        ]
                                    ),
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(ft.Text("Средний балл:")),
                                            ft.DataCell(ft.Text("Значение")),
                                        ]
                                    ),
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(ft.Text("Личная дисциплина:")),
                                            ft.DataCell(ft.Text("Значение")),
                                        ]
                                    ),
                                    ft.DataRow(
                                        cells=[
                                            ft.DataCell(ft.Text("Наличие академических\nзадолжностей:")),
                                            ft.DataCell(ft.Text("Значение")),
                                        ]
                                    ),
                                ],
                            ),
                        ],
                        spacing=10,
                    ),
                    padding=10,
                ),
                elevation=5,
                margin=10,
            )

            button_card =ft.Container(
                    content=ft.Column(
                        [
                            ft.FilledButton("Оценка успеваемости", height=55, width=270),
                            ft.FilledButton("Состояние личной дисциплины", height=55, width=270),
                            ft.FilledButton("Командно - методические навыки", height=55, width=270),
                            ft.FilledButton("Научная деятельность", height=55, width=270),
                            ft.FilledButton("Физическая подготовленность", height=55, width=270),

                        ],
                        spacing=10,
                    ),
                    padding=10,
                )

            #Карточка нижних кнопок
            button_botom_card =ft.Container(
                    content=ft.Column(
                        [
                            ft.FilledButton("Социальный портрет", height=55, width=350),
                            ft.FilledButton("Данные документов", height=55, width=350),
                            ft.FilledButton("Данные родителей, родственников", height=55, width=350),
                            ft.FilledButton("Грубые дисциплинарные проступки, травмы", height=55, width=350),
                            ft.FilledButton("Справка - объективка", height=55, width=350),

                        ],
                        spacing=10,
                    ),
                    padding=10,
                )
            
            #Карточка общественной работы
            ac_life_card = ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Text("Участие в жизни курса, факультета, академии", size=18, weight="bold"),
                                ft.Text("1. С декабря 2020 года по февраль 2021 года принимал участие в оказании медицинской помощи населению московской области в борьбе с новой коронавирусной инфекцией на базе КВЦ «Патриот», работая в должности санитара.", size=16),
                                ft.Text("2. В апреле-мае 2021 года принимал активное участие в подготовке и проведении праздничных мероприятий в честь юбилея ВИФК. Организовывал «Живое табло».", size=16),
                            ],
                            spacing=10,
                        ),
                        padding=10,
                    ),
                    width= 1000,
                    height= 300,
                    elevation=5,
                    margin=10,
                )

            row1_layout = ft.Row(
                controls=[
                    basic_data_card,
                    photo_container,
                    reiting_card,
                    button_card,
                ],
                spacing=20,
                alignment=ft.MainAxisAlignment.CENTER,
            )

            row2_layout = ft.Row(
                controls = [
                    button_botom_card,
                    ac_life_card,
                ],
                spacing=20,
                alignment=ft.MainAxisAlignment.CENTER,
            )
            
            self.student_info_container.controls.append(row1_layout)
            self.student_info_container.controls.append(row2_layout)

        self._page.update()

    def back_click(self, e):
        self._page.controls.clear()
        self._page.add(get_page("KantslerApp")(self._page))
        self._page.update()
