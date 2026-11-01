import flet as ft
import pandas as pd
# tkinter используется только для диалога выбора пути сохранения файлов;
# импорт выполняется лениво внутри методов, чтобы приложение запускалось
# даже на системах без установленной среды X11/tkinter.
import os
import shutil
from openpyxl.utils import get_column_letter
from datetime import datetime, timedelta
from database import get_students, check_user, search_students_by_multiple_params, add_encouragement, get_encouragements_by_student, add_penalty, get_penalties_by_student, search_students_by_name_part, get_subjects_by_name_part, log_action, get_users, add_user, update_user_role, delete_user, get_logs, get_user_by_id, update_user_password
# Слой репозиториев: UI больше не пишет SQL напрямую (см. repositories.py)
import repositories as repo
import photo_storage
from constants import ROLES, ADMIN_ROLE, DEFAULT_ROLE, EDITABLE_STUDENT_FIELDS
from pages.registry import get_page
from pages import shell
from utils import show_snack, to_int, session_get
from utils_logger import log_except


def session_username(page_obj):
    return session_get(page_obj, "username") or "system"


class PersonalFilePage(ft.Column):
    def _wrap_control(self, control):
        """Возвращает контрол для показа: внутри каркаса — через shell
        (боковое меню сохраняется), автономно — как раньше."""
        from pages import shell as _shell
        sh = _shell.get_shell()
        if sh is not None and self._page is not None:
            sh.open_standalone(type(control).__name__, control)
            return None
        return control

    def _ensure_picker(self):
        """Лениво создаёт FilePicker в overlay страницы (один раз)."""
        picker = getattr(self, "_pdf_picker", None)
        if picker is not None:
            return picker
        picker = ft.FilePicker()
        try:
            if picker not in self._page.overlay:
                self._page.overlay.append(picker)
        except Exception:
            log_except("personal_file_page: блок на строке 44")
        self._pdf_picker = picker
        return picker

    def print_personal_file_pdf(self, e=None):
        """Печатает личное дело курсанта в PDF (шаблон Road Map) и
        открывает диалог сохранения файла."""
        sid = to_int(getattr(self, "selected_student_id", None))
        if sid is None:
            show_snack(self._page, ft.Text("Сначала выберите курсанта."))
            return
        try:
            from personal_file_pdf import generate_personal_file_pdf
            path = generate_personal_file_pdf(sid)
        except RuntimeError as err:      # reportlab не установлен
            show_snack(self._page, ft.Text(str(err)))
            return
        except Exception as err:
            show_snack(self._page, ft.Text(f"Ошибка формирования PDF: {err}"))
            return
        log_action(session_username(self._page),
                   f"Печать личного дела (PDF): student_id={sid}")
        # Десктоп: открыть стандартной программой + предложить сохранить.
        try:
            import subprocess, sys
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            log_except("personal_file_page: блок на строке 76")
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            self._ensure_picker().save_file(
                dialog_title="Сохранить личное дело (PDF)",
                file_name=os.path.basename(path),
                src_bytes=data)
        except Exception:
            log_except("personal_file_page: блок на строке 85")
        show_snack(self._page, ft.Text(
            f"Личное дело сохранено в PDF: {os.path.basename(path)}"))
        self._safe_update()

    def _safe_update(self):
        try:
            self._page.update()
        except Exception:
            log_except("personal_file_page: блок на строке 94")

    def __init__(self, page, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO)
        self._page = page

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

        # Печать личного дела в PDF (шаблон Road Map)
        self.print_pdf_button = ft.FilledButton(
            "Печать личного дела (PDF)", icon=ft.Icons.PRINT,
            on_click=self.print_personal_file_pdf)

        # Пакетная печать: несколько личных дел одним PDF
        self.batch_ids = []                      # student_id -> Checkbox
        self.batch_checkboxes = {}
        self.batch_list_col = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO,
                                        height=300, visible=False, width=560)
        self.batch_panel = ft.Container(
            visible=False, width=580, padding=14, bgcolor="#ffffff",
            border=ft.Border.all(1, "#e2e8f0"), border_radius=12,
            content=ft.Column([
                ft.Text("Пакетная печать личных дел (один PDF)", size=15,
                        weight="bold"),
                ft.Row([
                    ft.TextField(label="Группа (фильтр)", width=200,
                                 hint_text="напр. 1 рота",
                                 on_change=self._batch_filter_changed),
                    ft.TextField(label="Курс (фильтр)", width=120,
                                 hint_text="напр. 2",
                                 on_change=self._batch_filter_changed),
                    ft.Text("", size=12, color="#64748b"),
                ], spacing=10),
                ft.Container(
                    content=self.batch_list_col,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
                ft.Row([
                    ft.FilledButton("Сформировать PDF", icon=ft.Icons.PRINT,
                                    on_click=self.batch_print_confirm),
                    ft.TextButton("Отмена", on_click=self.batch_print_cancel),
                ], spacing=10)
            ], spacing=12),
        )

        self.batch_toggle_button = ft.OutlinedButton(
            "Пакетная печать дел", icon=ft.Icons.COLLECTIONS,
            on_click=self.batch_print_open)

        # Определяем порядок элементов, как в примере
        self.controls = [
            ft.Text("Личное дело курсанта", size=20, weight="bold"),
            self.student_search_field,
            self.student_dropdown,
            ft.Divider(),  # Добавляем разделитель
            self.student_info_container,
            ft.Row([self.print_pdf_button, self.batch_toggle_button,
                             self.back_button], spacing=12),
            self.batch_panel,
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

            # Создаем контейнер для фотографии
            photo_container = ft.Column()

            # Фото читается через photo_storage: новое хранение — имя файла в
            # PHOTOS_DIR, старое — base64 в колонке (обратная совместимость).
            # Индекс o_photo берём из схемы, а не хардкод [24] (SELECT * тянет
            # порядок колонок за собой — любой ALTER ломал бы карточку).
            photo_value = ""
            try:
                cols = [d[0] for d in repo.get_student_columns()]
                photo_value = student_data[cols.index("o_photo")] or ""
            except (ValueError, IndexError):
                photo_value = student_data[24] if len(student_data) > 24 else ""

            src = photo_storage.photo_src(photo_value)
            if src:
                photo_container.controls.append(
                    ft.Image(src=src, width=300, height=400,
                             fit=ft.BoxFit.COVER, border_radius=10)
                )
            elif photo_value and not photo_storage.looks_like_base64(photo_value):
                photo_container.controls.append(
                    ft.Text("Ошибка: файл фотографии не найден", color="red")
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
    def _wrap_control(self, control):
        """Возвращает контрол для показа: внутри каркаса — через shell
        (боковое меню сохраняется), автономно — как раньше."""
        from pages import shell as _shell
        sh = _shell.get_shell()
        if sh is not None and self._page is not None:
            sh.open_standalone(type(control).__name__, control)
            return None
        return control



    # ==================================================================
    # Пакетная печать личных дел — несколько курсантов одним PDF
    # ==================================================================
    def _batch_all_students(self):
        """Список (id, фио, группа, курс) всех курсантов."""
        try:
            from database import get_students
            rows = get_students() or []
        except Exception:
            return []
        out = []
        for r in rows:
            try:
                sid = to_int(r["id"])
                if sid is None:
                    continue
                fio = " ".join(str(x).strip() for x in
                               (r["o_surname"], r["o_name"], r["o_lastname"])
                               if x not in (None, ""))
                out.append((sid, fio, str(r["o_group_name"] or ""),
                            str(r["o_course"] or "")))
            except Exception as e:
                log_except(f"personal_file_page: строка курсанта id={sid} в списке пакетной печати", e)
                continue
        return out

    def batch_print_open(self, e=None):
        self.batch_panel.visible = True
        self._batch_filter_changed(None)
        self._safe_update()

    def batch_print_cancel(self, e=None):
        self.batch_panel.visible = False
        self._safe_update()

    def _batch_filter_changed(self, e):
        """Пересобирает список чекбоксов по фильтрам группа/курс."""
        try:
            grp = (self.batch_panel.content.controls[1].controls[0].value or "").strip().lower()
            crs = (self.batch_panel.content.controls[1].controls[1].value or "").strip().lower()
        except Exception:
            grp = crs = ""
        col = self.batch_list_col
        col.controls.clear()
        self.batch_checkboxes = {}
        count = 0
        for sid, fio, group, course in self._batch_all_students():
            if grp and grp not in group.lower():
                continue
            if crs and crs != course.lower():
                continue
            cb = ft.Checkbox(label=f"{fio}  ·  гр. {group or '—'} · {course}-й курс",
                             value=False)
            self.batch_checkboxes[sid] = cb
            col.controls.append(cb)
            count += 1
        col.visible = True
        counter = self.batch_panel.content.controls[1].controls[2]
        try:
            counter.value = f"Найдено: {count}"
        except Exception:
            log_except("personal_file_page: блок на строке 546")
        self._safe_update()

    def batch_print_confirm(self, e=None):
        ids = [sid for sid, cb in self.batch_checkboxes.items() if cb.value]
        if not ids:
            show_snack(self._page, ft.Text("Отметьте хотя бы одного курсанта."))
            return
        try:
            from personal_file_pdf import generate_batch_personal_files_pdf
            path = generate_batch_personal_files_pdf(ids)
        except RuntimeError as err:
            show_snack(self._page, ft.Text(str(err)))
            return
        except Exception as err:
            show_snack(self._page, ft.Text(f"Ошибка пакетной печати: {err}"))
            return
        log_action(session_username(self._page),
                   f"Пакетная печать личных дел (PDF): {len(ids)} шт.")
        try:
            import subprocess, sys
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            log_except("personal_file_page: блок на строке 574")
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            self._ensure_picker().save_file(
                dialog_title="Сохранить пакет личных дел (PDF)",
                file_name=os.path.basename(path),
                src_bytes=data)
        except Exception:
            log_except("personal_file_page: блок на строке 583")
        self.batch_panel.visible = False
        show_snack(self._page, ft.Text(
            f"Готово: {len(ids)} личныx дел в одном PDF "
            f"({os.path.basename(path)})"))
        self._safe_update()


    def back_click(self, e):
        shell.back_to_app(self._page)
