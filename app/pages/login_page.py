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
from utils import session_get, session_set, session_clear


class LoginPage(ft.Column):
    def __init__(self, page: ft.Page):
        super().__init__(
            alignment=ft.MainAxisAlignment.CENTER,       # Вертикальное выравнивание по центру
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,  # Горизонтальное выравнивание по центру
            expand=True                                  # Растягиваем столбец на всю страницу
        )
        # В Flet >= 0.29 у Control.page — свойство только для чтения,
        # поэтому сохраняем ссылку на страницу в собственном атрибуте _page.
        self._page = page
        self.username = ft.TextField(label="Имя пользователя", width=300)
        self.password = ft.TextField(label="Пароль", width=300, password=True)
        self.login_button = ft.FilledButton("Войти", on_click=self.login_click)
        self.error_text = ft.Text(color="red")
        
        # Оборачиваем элементы в контейнер для дополнительного контроля выравнивания
        self.controls = [
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.PERSON, size=64, color="#3b82f6"),
                        ft.Text("Канцлер Про", size=28, weight="bold", color="#1e293b"),
                        ft.Text("Учёт курсантов · Дорожная карта · Отчёты",
                                size=13, color="#64748b"),
                        self.username,
                        self.password,
                        self.login_button,
                        self.error_text
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=10
                ),
                padding=20
            )
        ]

    def login_click(self, e):
        page = self._page  # ссылка на ft.Page (в Flet >= 0.29 Control.page только для чтения)
        username = self.username.value.strip()
        password = self.password.value.strip()
        if not username or not password:
            self.error_text.value = "Заполните все поля"
        else:
            user = check_user(username, password)
            if user:
                # check_user возвращает [(id, username, role)] — ровно 3 поля
                user_id, username, role = user[0]
                # page.session — это SessionStorage (dict-подобное хранилище):
                # значения сохраняются по ключам, читаются через .get()
                session_set(page, "user_id", user_id)
                session_set(page, "username", username)
                session_set(page, "role", role)
                log_action(username, "Вход в систему")
                page.controls.clear()
                page.add(get_page("KantslerApp")(page))
            else:
                self.error_text.value = "Неверное имя пользователя или пароль"
        page.update()
