import flet as ft
import ui_kit as k

import repositories as repo
from pages import shell

# Поля, доступные для расширенного поиска (единый список вместо 17 if/elif)
_EXTRA_FIELDS = [
    "Имя", "Отчество", "Группа", "Курс", "Возраст", "Пол",
    "Дата рождения", "Место рождения", "Гражданство", "Национальность",
    "Вероисповедание", "Семейное положение", "Место жительства",
    "Вредные привычки", "Состояние здоровья", "Интересы", "Навыки",
]

# Отображаемое имя поля -> имя kwarg-аргумента функции поиска
_PARAM_MAP = {
    "Имя": "name", "Отчество": "lastname", "Группа": "group_name",
    "Курс": "course", "Возраст": "age", "Пол": "gender",
    "Дата рождения": "birthday", "Место рождения": "birthplace",
    "Гражданство": "citizenship", "Национальность": "nationality",
    "Вероисповедание": "religion", "Семейное положение": "marital_status",
    "Место жительства": "residence", "Вредные привычки": "bad_habits",
    "Состояние здоровья": "health_status", "Интересы": "interests",
    "Навыки": "skills",
}


class SearchPage(ft.Column):
    """Поиск курсантов: быстрое ФИО + необязательные уточняющие поля."""

    def __init__(self, page, parent=None):
        super().__init__(scroll=ft.ScrollMode.AUTO, expand=True)
        self._page = page
        page.bgcolor = k.BG_SOFT

        # Основное поле — фамилия (Enter сразу ищет)
        self.search_surname = ft.TextField(
            label="Фамилия",
            hint_text="Начните вводить фамилию…",
            prefix_icon=ft.Icons.SEARCH,
            border_radius=10,
            autofocus=True,
            on_submit=self.perform_search,
        )

        # Выпадающий список для добавления дополнительных полей
        self.additional_fields_dropdown = ft.Dropdown(
            label="+ Добавить критерий поиска",
            options=[ft.dropdown.Option(f) for f in _EXTRA_FIELDS],
            border_radius=10,
            width=320,
            on_select=self.add_additional_field,
        )

        self.additional_fields_container = ft.Row(wrap=True, spacing=8,
                                                  run_spacing=8)
        self.clear_button = ft.TextButton("Сбросить критерии",
                                          icon=ft.Icons.CLEAR,
                                          on_click=self.clear_filters)
        self.search_button = ft.FilledButton("Искать", icon=ft.Icons.SEARCH,
                                             on_click=self.perform_search)
        self.back_button = ft.OutlinedButton("Назад", icon=ft.Icons.ARROW_BACK,
                                             on_click=self.back_to_main)
        self.results_container = ft.Column(spacing=8)

        # Словарь активных дополнительных полей {имя_поля: TextField}
        self.additional_fields: dict[str, ft.TextField | None] = {
            f: None for f in _EXTRA_FIELDS
        }

        form = k.card(ft.Column([
            k.section_title("Поиск курсантов", icon=ft.Icons.PERSON_SEARCH,
                            subtitle="Укажите фамилию и, при необходимости, "
                                    "дополнительные критерии"),
            ft.Row([k.wrap_field(self.search_surname, 240, 360),
                    self.additional_fields_dropdown],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self.additional_fields_container,
            ft.Divider(height=1, color=k.BORDER),
            k.action_row([self.search_button, self.clear_button,
                          self.back_button]),
        ]))

        self.controls = [form, self.results_container]

    # ------------------------------------------------------------------
    def add_additional_field(self, e):
        selected_field = self.additional_fields_dropdown.value
        if not selected_field or self.additional_fields.get(selected_field):
            return  # поле уже добавлено
        field = ft.TextField(label=selected_field, border_radius=10,
                             on_submit=self.perform_search)
        self.additional_fields[selected_field] = field
        self.additional_fields_container.controls.append(
            k.wrap_field(field, 220, 300))
        # даём возможность убрать отдельное поле
        remove = ft.IconButton(ft.Icons.CLOSE, tooltip=f"Убрать «{selected_field}»",
                               icon_size=14,
                               on_click=lambda ev, n=selected_field:
                               self.remove_field(n))
        self.additional_fields_container.controls.append(remove)
        self.additional_fields_dropdown.value = None
        self._page.update()

    def remove_field(self, name):
        field = self.additional_fields.get(name)
        if not field:
            return
        # удаляем само поле и его кнопку-крестик из контейнера
        self.additional_fields_container.controls[:] = [
            c for c in self.additional_fields_container.controls
            if not (isinstance(c, ft.Container) and c.content is field)
            and not (isinstance(c, ft.IconButton)
                     and c.tooltip == f"Убрать «{name}»")
        ]
        self.additional_fields[name] = None
        self._page.update()

    def clear_filters(self, e):
        for name in list(self.additional_fields):
            self.additional_fields[name] = None
        self.additional_fields_container.controls.clear()
        self.search_surname.value = ""
        self.results_container.controls.clear()
        self._page.update()

    # ------------------------------------------------------------------
    def _collect_kwargs(self):
        kwargs = {}
        surname = (self.search_surname.value or "").strip()
        if surname:
            kwargs["surname"] = surname
        for label, field in self.additional_fields.items():
            if field is None:
                continue
            value = (field.value or "").strip()
            if value:
                kwargs[_PARAM_MAP[label]] = value
        return kwargs

    def perform_search(self, e):
        kwargs = self._collect_kwargs()
        self.results_container.controls.clear()

        if not kwargs:
            self.results_container.controls.append(k.card(
                k.empty_state("Введите хотя бы один критерий поиска",
                              icon=ft.Icons.FILTER_ALT,
                              hint="Например, фамилию — или добавьте уточнения "
                                   "через «+ Добавить критерий»")))
            self._page.update()
            return

        students = repo.search_students_like(**kwargs)
        self.results_container.controls.clear()

        if not students:
            self.results_container.controls.append(k.card(
                k.empty_state("Курсанты не найдены",
                              icon=ft.Icons.PERSON_OFF,
                              hint="Попробуйте уменьшить число критериев или "
                                   "указать фамилию частично")))
            self._page.update()
            return

        count = len(students)
        header = ft.Row([
            ft.Text(f"Найдено курсантов: {count}", size=15,
                    weight=ft.FontWeight.BOLD, color=k.PRIMARY_DARK),
            ft.Container(expand=True),
        ])
        self.results_container.controls.append(header)

        # Карточки результатов: клик открывает личное дело сразу
        cards_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, height=520)
        for st in students[:200]:  # защита от гигантского списка
            sid, first, middle, last = st[0], st[1], st[2], st[3]
            course, group = st[4], st[5]
            fio = " ".join(x for x in (last, first, middle) if x)
            c = k.card(
                ft.Row([
                    ft.Icon(ft.Icons.ACCOUNT_CIRCLE, size=34, color=k.PRIMARY),
                    ft.Column([
                        ft.Text(fio, size=14, weight=ft.FontWeight.W_600,
                                color=k.PRIMARY_DARK),
                        ft.Text(f"Группа: {group or '—'} · Курс: {course or '—'}",
                                size=12, color=k.MUTED),
                    ], spacing=2, expand=True),
                    ft.Icon(ft.Icons.OPEN_IN_NEW, size=18, color=k.MUTED),
                ], spacing=10),
                padding=12,
            )
            c.ink = True
            c.tooltip = "Открыть личное дело"
            c.on_click = lambda ev, i=sid, n=fio: self.open_student(i, n)
            cards_col.controls.append(c)
        if count > 200:
            cards_col.controls.append(ft.Text(
                f"Показаны первые 200 из {count}. Уточните критерии поиска.",
                size=12, color=k.WARNING))
        self.results_container.controls.append(cards_col)
        self._page.update()

    def open_student(self, student_id, fio):
        """Переход в личное дело выбранного курсанта."""
        from pages.registry import get_page
        pf = get_page("PersonalFilePage")(self._page)
        pf.selected_student_id = int(student_id)
        pf.student_search_field.value = fio
        pf.load_student_data(int(student_id))
        sh = shell.get_shell()
        if sh is not None:
            sh.open_standalone("PersonalFilePage", pf)
        else:
            self._page.controls.clear()
            self._page.add(pf)
            self._page.update()

    def back_to_main(self, e):
        shell.back_to_app(self._page)
