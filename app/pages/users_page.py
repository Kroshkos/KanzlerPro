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
from utils import session_get, session_set, session_clear, show_snack, to_int


class UsersPage(ft.Column):
    # Допустимые роли — единый источник правды для всего приложения
    ROLES = ROLES  # из constants.py — единый источник истины

    def __init__(self, page, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO)
        # Страница доступна только администраторам; при попытке прямого
        # захода без прав возвращаемся в главное меню.
        if session_get(page, "role") != ADMIN_ROLE:
            self.controls = [ft.Text("Недостаточно прав для управления пользователями", color="red")]
            return
        self._page = page
        self.username = session_get(self._page, "username")

        self.new_username = ft.TextField(label="Имя пользователя", width=300)
        self.new_password = ft.TextField(label="Пароль", width=300, password=True)
        self.new_role = ft.Dropdown(label="Роль", width=300, options=[
            ft.dropdown.Option(role) for role in self.ROLES
        ], value="Пользователь")
        self.add_user_button = ft.FilledButton("Добавить пользователя", on_click=self.add_user_click)

        self.users_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Имя пользователя")),
                ft.DataColumn(ft.Text("Роль")),
                ft.DataColumn(ft.Text("Действия")),
            ],
            rows=[]
        )
        self.load_users()

        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        self.controls = [
            ft.Text("Управление пользователями", size=20, weight="bold"),
            self.new_username,
            self.new_password,
            self.new_role,
            self.add_user_button,
            ft.Divider(),
            self.users_table,
            self.back_button
        ]

    def load_users(self):
        users = get_users()
        current_id = session_get(self._page, "user_id")
        self.users_table.rows = []
        for user in users:
            user_id, username, role = user
            buttons = [
                ft.FilledButton("Сменить пароль", data=user_id, on_click=self.change_password_click),
                ft.FilledButton("Изменить роль", data=user_id, on_click=self.change_role_click),
            ]
            # Запрещаем удалять собственную учётную запись и последнего администратора
            admin_ids = [u[0] for u in users if u[2] == ADMIN_ROLE]
            can_delete = user_id != current_id and not (role == ADMIN_ROLE and len(admin_ids) <= 1)
            if can_delete:
                buttons.append(ft.FilledButton("Удалить", data=user_id, on_click=self.delete_user_click))
            self.users_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(user_id))),
                        ft.DataCell(ft.Text(username)),
                        ft.DataCell(ft.Text(role)),
                        ft.DataCell(ft.Row(buttons))
                    ]
                )
            )

    def add_user_click(self, e):
        username = self.new_username.value.strip()
        password = self.new_password.value.strip()
        role = self.new_role.value
        if role not in self.ROLES:
            role = "Пользователь"
        if not username or not password:
            show_snack(self._page, ft.Text("Заполните имя пользователя и пароль"))
            self._page.update()
            return
        try:
            add_user(username, password, role)
        except Exception:
            # UNIQUE constraint violation — пользователь с таким именем уже существует
            show_snack(self._page, ft.Text(f"Пользователь '{username}' уже существует"))
            self._page.update()
            return
        log_action(session_get(self._page, "username"), f"Добавлен пользователь {username} с ролью {role}")
        self.new_username.value = ""
        self.new_password.value = ""
        self.load_users()
        show_snack(self._page, ft.Text(f"Пользователь {username} добавлен"))
        self._page.update()

    def change_password_click(self, e):
        """Смена пароля: новый пароль хешируется перед сохранением."""
        user_id = to_int(e.control.data)
        target = get_user_by_id(user_id)
        if not target:
            return
        new_password = self.new_password.value.strip()
        if not new_password:
            show_snack(self._page, ft.Text("Введите новый пароль в поле 'Пароль' и повторите нажатие"))
            self._page.update()
            return
        update_user_password(user_id, new_password)
        log_action(session_get(self._page, "username"), f"Изменён пароль пользователя ID {user_id}")
        self.new_password.value = ""
        show_snack(self._page, ft.Text(f"Пароль пользователя '{target[1]}' обновлён"))
        self._page.update()

    def change_role_click(self, e):
        user_id = to_int(e.control.data)
        target = get_user_by_id(user_id)
        if not target:
            return
        _, _, current_role = target
        new_role = DEFAULT_ROLE if current_role == ADMIN_ROLE else ADMIN_ROLE
        # Нельзя понизить последнего администратора
        if new_role != ADMIN_ROLE:
            admins = [u for u in get_users() if u[2] == ADMIN_ROLE]
            if len(admins) <= 1 and current_role == ADMIN_ROLE:
                show_snack(self._page, ft.Text("Нельзя снять роль администратора с последнего администратора"))
                self._page.update()
                return
        # Нельзя менять собственную роль (иначе можно случайно потерять доступ)
        if user_id == session_get(self._page, "user_id"):
            show_snack(self._page, ft.Text("Нельзя изменить собственную роль"))
            self._page.update()
            return
        update_user_role(user_id, new_role)
        log_action(session_get(self._page, "username"), f"Изменена роль пользователя с ID {user_id} на {new_role}")
        self.load_users()
        self._page.update()

    def delete_user_click(self, e):
        user_id = to_int(e.control.data)
        # Повторная серверная проверка прав (UI может быть обойдён)
        if user_id == session_get(self._page, "user_id"):
            show_snack(self._page, ft.Text("Нельзя удалить собственного пользователя"))
            self._page.update()
            return
        target = get_user_by_id(user_id)
        if target and target[2] == ADMIN_ROLE:
            admins = [u for u in get_users() if u[2] == ADMIN_ROLE]
            if len(admins) <= 1:
                show_snack(self._page, ft.Text("Нельзя удалить последнего администратора"))
                self._page.update()
                return
        delete_user(user_id)
        log_action(session_get(self._page, "username"), f"Удален пользователь с ID {user_id}")
        self.load_users()
        self._page.update()

    def back_click(self, e):
        log_action(self.username, "Возврат на главную страницу из управления пользователями")
        shell.back_to_app(self._page)
