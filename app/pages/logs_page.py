
# tkinter используется только для диалога выбора пути сохранения файлов;
# импорт выполняется лениво внутри методов, чтобы приложение запускалось
# даже на системах без установленной среды X11/tkinter.
from datetime import datetime

import flet as ft

# Слой репозиториев: UI больше не пишет SQL напрямую (см. repositories.py)
from authz import require_admin
from database import (
    LOGS_PAGE_SIZE,
    count_logs,
    get_logs,
    log_action,
    verify_logs_chain,
)
from utils import session_get, show_snack, to_int

from pages import shell


class LogsPage(ft.Column):
    def __init__(self, page, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO)
        self._page = page
        # Журнал действий — админский раздел (см. authz.ADMIN_ONLY_PAGES);
        # проверка в конструкторе защищает и прямой вызов страницы вне каркаса.
        denied = require_admin(page, "Журнал действий доступен только администратору")
        if denied is not None:
            self.controls = [denied]
            return
        self.username = session_get(self._page, "username")

        # Поле для выбора даты
        self.date_picker = ft.TextField(
            label="Выберите дату (ДД.ММ.ГГГГ) или оставьте пустым для всех дат",
            width=300,
            on_change=self.filter_logs
        )

        # Выпадающий список для количества строк
        self.rows_dropdown = ft.Dropdown(
            label="Количество строк",
            width=150,
            options=[
                ft.dropdown.Option("10"),
                ft.dropdown.Option("25"),
                ft.dropdown.Option("50"),
                ft.dropdown.Option("100"),
                ft.dropdown.Option("Все строки"),
            ],
            value="10",  # Значение по умолчанию
            on_select=self.filter_logs
        )

        # Кнопка для экспорта в txt
        self.export_button = ft.FilledButton("Экспорт в TXT", width=150, on_click=self.export_to_txt)

        # Таблица логов
        self.logs_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Дата и время")),
                ft.DataColumn(ft.Text("Пользователь")),
                ft.DataColumn(ft.Text("Действие")),
            ],
            rows=[]
        )

        # Кнопка "Назад"
        self.back_button = ft.FilledButton("Назад", on_click=self.back_click)

        # C-1 (второй этап): листание журнала страницами (SQL LIMIT/OFFSET)
        self.current_page = 0
        self.prev_button = ft.IconButton(
            ft.Icons.CHEVRON_LEFT, on_click=self.prev_page_click,
            tooltip="Предыдущая страница")
        self.next_button = ft.IconButton(
            ft.Icons.CHEVRON_RIGHT, on_click=self.next_page_click,
            tooltip="Следующая страница")
        self.page_label = ft.Text("", weight="bold")

        # B-5: баннер целостности журнала (виден только при разрыве цепочки)
        self.logs_banner = ft.Text(
            "", color=ft.Colors.RED_400, weight="bold", visible=False)

        # Составляем интерфейс
        self.controls = [
            ft.Row(
                controls=[
                    ft.Text("Журнал действий", size=20, weight="bold"),
                    ft.Container(expand=True),  # Для выравнивания элементов справа
                    self.date_picker,
                    self.rows_dropdown,
                    self.export_button
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER
            ),
            ft.Divider(),
            self.logs_banner,
            ft.Row(
                [self.prev_button, self.page_label, self.next_button],
                alignment=ft.MainAxisAlignment.CENTER),
            self.logs_table,
            self.back_button
        ]

        # Загружаем логи при инициализации
        self.load_logs()

    def load_logs(self):
        """Загружает и фильтрует логи в зависимости от выбранной даты и количества строк.

        C-1 (второй этап): страница выбирается на уровне SQL (LIMIT/OFFSET),
        а не срезом списка в памяти — журнал может расти без удорожания
        отрисовки.
        """
        self.logs_table.rows = []

        # Фильтрация по дате: условие выносится в SQL (параметром),
        # чтобы offset считался уже по отфильтрованной выборке.
        date_prefix = None
        selected_date = self.date_picker.value.strip()
        if selected_date:
            try:
                # Преобразуем введённую дату в формат для сравнения
                date_prefix = datetime.strptime(
                    selected_date, "%d.%m.%Y").strftime("%Y-%m-%d") + "%"
            except ValueError:
                show_snack(self._page, ft.Text("Неверный формат даты. Используйте ДД.ММ.ГГГГ"))
                self._page.update()
                return

        # Количество строк на странице ("Все строки" -> limit=None)
        rows_limit = self.rows_dropdown.value
        page_size = LOGS_PAGE_SIZE if rows_limit == "Все строки" \
            else to_int(rows_limit, LOGS_PAGE_SIZE)
        total = count_logs(date_prefix=date_prefix)
        total_pages = max(1, -(-total // page_size))  # ceil
        # При смене размера страницы/фильтра не выходим за границы журнала
        self.current_page = min(self.current_page, total_pages - 1)
        offset = self.current_page * page_size

        logs = get_logs(limit=page_size, offset=offset, date_prefix=date_prefix)

        # Заполняем таблицу
        for log in logs:
            timestamp, username, action = log
            self.logs_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(timestamp)),
                        ft.DataCell(ft.Text(username)),
                        ft.DataCell(ft.Text(action)),
                    ]
                )
            )
        self.page_label.value = (
            f"Стр. {self.current_page + 1} из {total_pages} (всего: {total})")
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= total_pages - 1
        self._page.update()

        # B-5: проверка целостности хеш-цепочки журнала
        try:
            broken = verify_logs_chain()
        except Exception:
            broken = []
        if broken:
            self.logs_banner.visible = True
            self.logs_banner.value = (
                f"⚠ Целостность журнала нарушена: строки {broken[:10]}. "
                "Возможна правка записей вне приложения."
            )
        else:
            self.logs_banner.visible = False

    def prev_page_click(self, e):
        if self.current_page > 0:
            self.current_page -= 1
            self.load_logs()

    def next_page_click(self, e):
        self.current_page += 1
        self.load_logs()

    def filter_logs(self, e):
        """Обработчик изменения даты или количества строк."""
        self.current_page = 0  # новый фильтр — начинаем с первой страницы
        self.load_logs()

    def export_to_txt(self, e):
        """Экспортирует отображаемые логи в текстовый файл."""
        from tkinter import Tk, filedialog

        # Собираем данные из таблицы
        log_text = "Дата и время\tПользователь\tДействие\n"
        for row in self.logs_table.rows:
            timestamp = row.cells[0].content.value
            username = row.cells[1].content.value
            action = row.cells[2].content.value
            log_text += f"{timestamp}\t{username}\t{action}\n"

        # Запрашиваем путь для сохранения файла
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            title="Сохранить логи как"
        )

        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(log_text)
            show_snack(self._page, ft.Text(f"Логи сохранены в: {file_path}"))
            self._page.update()

    def back_click(self, e):
        log_action(self.username, "Возврат на главную страницу из журнала")
        shell.back_to_app(self._page)
