import flet as ft
import ui_kit as k

# Слой репозиториев: UI больше не пишет SQL напрямую (см. repositories.py)
from database import check_user, log_action
from utils import session_set

from pages.registry import get_page


class LoginPage(ft.Column):
    def __init__(self, page: ft.Page):
        super().__init__(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )
        # Фон приложения задаём на уровне страницы (у Column в Flet 1.x нет bgcolor)
        page.bgcolor = k.BG_SOFT
        # В Flet >= 0.29 у Control.page — свойство только для чтения,
        # поэтому сохраняем ссылку на страницу в собственном атрибуте _page.
        self._page = page
        self.username = ft.TextField(
            label="Имя пользователя",
            hint_text="например, ivanov",
            prefix_icon=ft.Icons.PERSON_OUTLINE,
            border_radius=10,
            autofocus=True,
            on_submit=self._submit_enter,
        )
        self.password = ft.TextField(
            label="Пароль",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            border_radius=10,
            on_submit=self._submit_enter,
        )
        self.login_button = ft.FilledButton(
            "Войти",
            icon=ft.Icons.LOGIN,
            on_click=self.login_click,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
        )
        self.notice = k.NoticeBox()

        # Карточка входа по центру экрана
        self.controls = [
            k.card(
                ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.SCHOOL, size=56, color=k.PRIMARY),
                        ft.Text("Канцлер Про", size=26, weight="bold",
                                color=k.PRIMARY_DARK),
                        ft.Text("Учёт курсантов · Дорожная карта · Отчёты",
                                size=13, color=k.MUTED),
                        ft.Divider(height=1, color=k.BORDER),
                        ft.Row([self.username], width=340),
                        ft.Row([self.password], width=340),
                        self.notice.control,
                        ft.Row([self.login_button], width=340),
                        ft.Text("Enter в поле ввода — быстрый вход",
                                size=11, color=k.MUTED),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
                padding=32,
            )
        ]

    def _submit_enter(self, e):
        """Enter в любом из полей отправляет форму."""
        self.login_click(e)

    def login_click(self, e):
        # ссылка на ft.Page (в Flet >= 0.29 Control.page только для чтения)
        page = self._page
        username = (self.username.value or "").strip()
        password = (self.password.value or "").strip()
        if not username or not password:
            self.notice.show("Заполните имя пользователя и пароль", kind="warning")
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
                self.notice.show("Неверное имя пользователя или пароль", kind="error")
        page.update()
