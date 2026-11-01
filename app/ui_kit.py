"""Единый UI-кит «Канцлер Про».

Цель — убрать дублирование (6 копий _wrap_control, разбросанные цвета/отступы)
и сделать все страницы визуально согласованными: карточки, поля форм в сетке,
пустые состояния, заголовки разделов, адаптивные кнопки действий.

Ничего не знает о БД — только presentation-компоненты на Flet.
"""

from __future__ import annotations

import flet as ft

# ---------------------------------------------------------------------------
# Дизайн-токены (единственная точка правки палитры/типографики)
# ---------------------------------------------------------------------------
PRIMARY = "#3b82f6"
PRIMARY_DARK = "#1e293b"
MUTED = "#64748b"
BG_SOFT = "#f1f5f9"
CARD_BG = "#ffffff"
BORDER = "#e2e8f0"
SUCCESS = "#16a34a"
WARNING = "#d97706"
DANGER = "#dc2626"

GAP = 12          # базовый отступ между блоками
PAD_CARD = 18     # внутренний отступ карточки


def _all(color):
    """Рамка со всех сторон (в Flet 1.x — classmethod Border.all)."""
    return ft.Border.all(1, color)


# ---------------------------------------------------------------------------
# Базовые контейнеры
# ---------------------------------------------------------------------------
def card(content, *, padding=PAD_CARD, border=True, bgcolor=CARD_BG):
    """Белая карточка с мягкой тенью — универсальный блок контента."""
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=bgcolor,
        border_radius=12,
        border=_all(BORDER) if border else None,
        shadow=ft.BoxShadow(
            blur_radius=10, spread_radius=0,
            color="#0f172a14", offset=ft.Offset(0, 2),
        ),
    )


def section_title(text: str, *, icon=None, subtitle=None, right_slot=None):
    """Заголовок раздела: иконка + название (+ подзаголовок и слот справа)."""
    left_controls = []
    if icon is not None:
        left_controls.append(ft.Icon(icon, size=22, color=PRIMARY))
    col_body = [ft.Text(text, size=19, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK)]
    if subtitle:
        col_body.append(ft.Text(subtitle, size=12, color=MUTED))
    left = ft.Column(col_body, spacing=2)
    row_controls = [left]
    if right_slot is not None:
        row_controls.append(ft.Container(expand=True))
        row_controls.append(right_slot)
    return ft.Row(row_controls, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def empty_state(message: str, *, icon=ft.Icons.SEARCH, hint=None):
    """Понятное «пустое» состояние вместо молчаливой пустой области."""
    controls = [
        ft.Icon(icon, size=42, color=MUTED),
        ft.Text(message, size=14, color=MUTED, text_align=ft.TextAlign.CENTER),
    ]
    if hint:
        controls.append(ft.Text(hint, size=12, color=MUTED,
                                text_align=ft.TextAlign.CENTER))
    return ft.Container(
        content=ft.Column(controls, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                          alignment=ft.MainAxisAlignment.CENTER, spacing=8),
        padding=30,
        alignment=ft.alignment.center,
    )


def info_chip(label: str, value, *, color=PRIMARY):
    """Небольшой чип «подпись: значение» для карточек-фишек."""
    return ft.Container(
        content=ft.Row(
            [ft.Text(label, size=11, color=MUTED),
             ft.Text(str(value or "—"), size=12, weight=ft.FontWeight.W_600,
                     color=PRIMARY_DARK)],
            spacing=5,
        ),
        padding=ft.padding.symmetric(horizontal=10, vertical=6),
        bgcolor=BG_SOFT,
        border_radius=8,
    )


def badge(text: str, *, color=PRIMARY):
    """Цветной бейдж статуса («Черновик», «Подтверждено» …)."""
    return ft.Container(
        content=ft.Text(text, size=11, weight=ft.FontWeight.W_600, color="white"),
        bgcolor=color,
        padding=ft.padding.symmetric(horizontal=8, vertical=3),
        border_radius=999,
    )


def notice(text: str, *, kind: str = "info"):
    """Инлайн-уведомление об ошибке/успехе рядом с формой.

    kind: info | success | warning | error
    """
    colors = {"info": PRIMARY, "success": SUCCESS,
              "warning": WARNING, "error": DANGER}
    icons = {"info": ft.Icons.INFO_OUTLINE, "success": ft.Icons.CHECK_CIRCLE,
             "warning": ft.Icons.WARNING_AMBER, "error": ft.Icons.ERROR_OUTLINE}
    c = colors.get(kind, PRIMARY)
    box = ft.Container(
        content=ft.Row([ft.Icon(icons.get(kind, ft.Icons.INFO_OUTLINE),
                                size=18, color=c),
                        ft.Text(text, size=13, color=c, expand=True)],
                       spacing=8,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
        visible=bool(text),
        bgcolor=f"{c}14",
        border=_all(f"{c}55"),
        border_radius=10,
        padding=ft.padding.symmetric(horizontal=12, vertical=9),
    )
    return box


class NoticeBox:
    """Управление видимостью одного notice-контейнера (show/hide/clear)."""

    def __init__(self):
        self.control = notice("")

    def show(self, text: str, kind: str = "info"):
        new = notice(text, kind=kind)
        self.control.content = new.content
        self.control.bgcolor = new.bgcolor
        self.control.border = new.border
        self.control.visible = True

    def clear(self):
        self.control.visible = False


# ---------------------------------------------------------------------------
# Адаптивные сетки полей
# ---------------------------------------------------------------------------
def wrap_field(field, min_width=280, max_width=420):
    """Поле растягивается от min до max ширины (адаптив вместо жёстких width).

    Единая реализация — ранее была скопирована в 6 страницах.
    """
    field.width = None
    field.expand = 1
    return ft.Container(
        content=field,
        expand={"min": min_width, "max": max_width},
    )


def form_grid(fields, *, columns=2, row_spacing=GAP, col_spacing=GAP):
    """Раскладывает список полей по N колонок; последний ряд дополняется."""
    rows = []
    fields = list(fields)
    for i in range(0, len(fields), columns):
        chunk = fields[i:i + columns]
        # дополняем короткий хвост пустыми заглушками, чтобы ширина не скакала
        while len(chunk) < columns and len(fields) > columns:
            chunk.append(ft.Container(expand={"min": 280, "max": 420}))
        rows.append(ft.Row(chunk, wrap=False,
                           spacing=col_spacing,
                           vertical_alignment=ft.CrossAxisAlignment.START))
    return ft.Column(rows, spacing=row_spacing)


def action_row(buttons, *, spacing=10, wrap=True):
    """Ряд кнопок; при узком окне аккуратно переносится."""
    return ft.Row(buttons, spacing=spacing, wrap=wrap,
                  run_spacing=8,
                  alignment=ft.MainAxisAlignment.START)


# ---------------------------------------------------------------------------
# Таблицы со «шляпой» и пустым состоянием
# ---------------------------------------------------------------------------
def data_table(header_cells: list[str], body_rows: list[ft.TableRow],
               *, column_widths: dict[int, int] | None = None,
               numeric_cols: set[int] | None = None):
    """Таблица с sticky-подобной жирной шапкой и единым стилем."""
    numeric_cols = numeric_cols or set()
    header = ft.TableRow(
        cells=[ft.Container(
            ft.Text(h, weight=ft.FontWeight.BOLD, size=12, color=PRIMARY_DARK),
            padding=8,
        ) for h in header_cells],
    )
    return ft.Table(
        column_widths=column_widths or {},
        rows=[header, *body_rows],
        border=_all(BORDER),
        border_radius=10,
        horizontal_lines=ft.BorderSide(1, BORDER),
    )


def cell(text, *, bold=False, align_right=False, color=None, size=13):
    """Ячейка текста для таблиц/карточек."""
    t = ft.Text(str(text if text is not None else "—"),
               size=size,
               weight=ft.FontWeight.W_600 if bold else ft.FontWeight.NORMAL,
               color=color or PRIMARY_DARK)
    return ft.Container(t, padding=8,
                        alignment=ft.alignment.center_right if align_right
                        else ft.alignment.center_left)


# ---------------------------------------------------------------------------
# Быстрая навигация
# ---------------------------------------------------------------------------
def tile_button(title: str, subtitle: str, on_click, *,
                icon=ft.Icons.ARROW_FORWARD_IOS, color=PRIMARY, width=240):
    """Крупная плитка-действие (замена простреливым спискам кнопок)."""
    return ft.Container(
        content=ft.Column(
            [
                ft.Row([ft.Icon(icon, size=22, color=color),
                        ft.Text(title, size=15, weight=ft.FontWeight.BOLD,
                                color=PRIMARY_DARK)], spacing=8),
                ft.Text(subtitle, size=12, color=MUTED),
            ],
            spacing=4,
        ),
        width=width,
        padding=14,
        bgcolor=CARD_BG,
        border=_all(BORDER),
        border_radius=12,
        ink=True,
        on_click=on_click,
    )
