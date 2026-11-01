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


class SearchPage(ft.Column):
    def __init__(self, page, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO)
        self._page = page
        
        # Основное поле для поиска по фамилии
        self.search_surname = ft.TextField(label="Фамилия", width=300)
        
        # Выпадающий список для выбора дополнительных полей
        self.additional_fields_dropdown = ft.Dropdown(
            label="Добавить поле для поиска",
            options=[
                ft.dropdown.Option("Имя"),
                ft.dropdown.Option("Отчество"),
                ft.dropdown.Option("Группа"),
                ft.dropdown.Option("Курс"),
                ft.dropdown.Option("Возраст"),
                ft.dropdown.Option("Пол"),
                ft.dropdown.Option("Дата рождения"),
                ft.dropdown.Option("Место рождения"),
                ft.dropdown.Option("Гражданство"),
                ft.dropdown.Option("Национальность"),
                ft.dropdown.Option("Вероисповедание"),
                ft.dropdown.Option("Семейное положение"),
                ft.dropdown.Option("Место жительства"),
                ft.dropdown.Option("Вредные привычки"),
                ft.dropdown.Option("Состояние здоровья"),
                ft.dropdown.Option("Интересы"),
                ft.dropdown.Option("Навыки"),

            ],
            on_select=self.add_additional_field
        )
        
        # Контейнер для дополнительных полей
        self.additional_fields_container = ft.Column()
        
        # Кнопка для выполнения поиска
        self.search_button = ft.FilledButton("Искать", on_click=self.perform_search)
        
        # Кнопка для возврата на главную страницу
        self.back_button = ft.FilledButton("Назад", on_click=self.back_to_main)
        
        # Контейнер для отображения результатов поиска
        self.results_container = ft.Column()
        
        # Добавляем все элементы на страницу
        self.controls = [
            ft.Text("Поиск курсантов", size=20, weight="bold"),
            self.search_surname,
            self.additional_fields_container,
            self.additional_fields_dropdown,
            self.search_button,
            self.back_button,
            self.results_container
        ]

        # Словарь для хранения дополнительных полей
        self.additional_fields = {
            "Имя": None,
            "Отчество": None,
            "Группа": None,
            "Курс": None,
            "Возраст": None,
            "Пол": None,
            "Дата рождения": None,
            "Место рождения": None,
            "Гражданство": None,
            "Национальность": None,
            "Вероисповедание": None,
            "Семейное положение": None,
            "Место жительства": None,
            "Вредные привычки": None,
            "Состояние здоровья": None,
            "Интересы": None,
            "Навыки": None,
        }

    # Обработчик добавления дополнительного поля
    def add_additional_field(self, e):
        selected_field = self.additional_fields_dropdown.value
        
        # Если поле уже добавлено, ничего не делаем
        if self.additional_fields[selected_field] is not None:
            return
        
        # Создаем поле для ввода в зависимости от выбранного параметра
        if selected_field == "Имя":
            field = ft.TextField(label="Имя", width=300)
        elif selected_field == "Отчество":
            field = ft.TextField(label="Отчество", width=300)
        elif selected_field == "Группа":
            field = ft.TextField(label="Группа", width=300)
        elif selected_field == "Курс":
            field = ft.TextField(label="Курс", width=300)
        elif selected_field == "Возраст":
            field = ft.TextField(label="Возраст", width=300)
        elif selected_field == "Пол":
            field = ft.TextField(label="Пол", width=300)
        elif selected_field == "Дата рождения":
            field = ft.TextField(label="Дата рождения", width=300)
        elif selected_field == "Место рождения":
            field = ft.TextField(label="Место рождения", width=300)
        elif selected_field == "Гражданство":
            field = ft.TextField(label="Гражданство", width=300)
        elif selected_field == "Национальность":
            field = ft.TextField(label="Национальность", width=300)
        elif selected_field == "Вероисповедание":
            field = ft.TextField(label="Вероисповедание", width=300)
        elif selected_field == "Семейное положение":
            field = ft.TextField(label="Семейное положение", width=300)
        elif selected_field == "Место жительства":
            field = ft.TextField(label="Место жительства", width=300)
        elif selected_field == "Вредные привычки":
            field = ft.TextField(label="Вредные привычки", width=300)
        elif selected_field == "Состояние здоровья":
            field = ft.TextField(label="Состояние здоровья", width=300)
        elif selected_field == "Интересы":
            field = ft.TextField(label="Интересы", width=300)
        elif selected_field == "Навыки":
            field = ft.TextField(label="Навыки", width=300)
        
        # Сохраняем поле в словаре
        self.additional_fields[selected_field] = field
        
        # Добавляем поле на страницу
        self.additional_fields_container.controls.append(field)
        self._page.update()

    # Обработчик выполнения поиска
    def perform_search(self, e):
        surname = self.search_surname.value.strip()
        
        # Собираем данные из дополнительных полей
        name = self.additional_fields["Имя"].value.strip() if self.additional_fields["Имя"] else None
        lastname = self.additional_fields["Отчество"].value.strip() if self.additional_fields["Отчество"] else None
        group = self.additional_fields["Группа"].value.strip() if self.additional_fields["Группа"] else None
        course = self.additional_fields["Курс"].value.strip() if self.additional_fields["Курс"] else None
        age = self.additional_fields["Возраст"].value.strip() if self.additional_fields["Возраст"] else None
        gender = self.additional_fields["Пол"].value.strip() if self.additional_fields["Пол"] else None
        birthday = self.additional_fields["Дата рождения"].value.strip() if self.additional_fields["Дата рождения"] else None
        birthplace = self.additional_fields["Место рождения"].value.strip() if self.additional_fields["Место рождения"] else None
        citizenship = self.additional_fields["Гражданство"].value.strip() if self.additional_fields["Гражданство"] else None
        nationality = self.additional_fields["Национальность"].value.strip() if self.additional_fields["Национальность"] else None
        religion = self.additional_fields["Вероисповедание"].value.strip() if self.additional_fields["Вероисповедание"] else None
        marital_status = self.additional_fields["Семейное положение"].value.strip() if self.additional_fields["Семейное положение"] else None
        residence = self.additional_fields["Место жительства"].value.strip() if self.additional_fields["Место жительства"] else None
        bad_habits = self.additional_fields["Вредные привычки"].value.strip() if self.additional_fields["Вредные привычки"] else None
        health_status = self.additional_fields["Состояние здоровья"].value.strip() if self.additional_fields["Состояние здоровья"] else None
        interests = self.additional_fields["Интересы"].value.strip() if self.additional_fields["Интересы"] else None
        skills = self.additional_fields["Навыки"].value.strip() if self.additional_fields["Навыки"] else None
        
        # Вызов функции поиска по нескольким параметрам
        students = search_students_by_multiple_params(
            surname=surname if surname else None,
            name=name if name else None,
            lastname=lastname if lastname else None,
            group_name=group if group else None,
            course=course if course else None,
            age=age if age else None,
            gender=gender if gender else None,
            birthday=birthday if birthday else None,
            birthplace=birthplace if birthplace else None,
            citizenship=citizenship if citizenship else None,
            nationality=nationality if nationality else None,
            religion=religion if religion else None,
            marital_status=marital_status if marital_status else None,
            residence=residence if residence else None,
            bad_habits=bad_habits if bad_habits else None,
            health_status=health_status if health_status else None,
            interests=interests if interests else None,
            skills=skills if skills else None
        )
        
        # Очистка контейнера с результатами
        self.results_container.controls.clear()
        
        if students:
            self.results_container.controls.append(ft.Text("Результаты поиска:", size=16, weight="bold"))
            for student in students:
                self.results_container.controls.append(
                    ft.Text(f"{student[1]} {student[2]} {student[3]} (Группа: {student[5]}, Курс: {student[4]})")
                )
        else:
            self.results_container.controls.append(ft.Text("Курсанты не найдены.", color="red"))
        
        # Обновляем страницу
        self._page.update()

    # Обработчик возврата на главную страницу
    def back_to_main(self, e):
        shell.back_to_app(self._page)
