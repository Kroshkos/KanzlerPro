"""Общие визуальные константы «Канцлер Про» — единая тема оформления.

Модуль используется новыми страницами (дашборд, дорожная карта) и главным
каркасом приложения KantslerApp для единообразных карточек, цветов и статусов.
"""

import flet as ft

# Палитра (flat / light)
PRIMARY = "#3b82f6"
BG = "#f1f5f9"
CARD_BG = "#ffffff"
TEXT_DARK = "#1e293b"
TEXT_MUTED = "#64748b"
SUCCESS = "#16a34a"
WARNING = "#d97706"
DANGER = "#dc2626"
INFO = "#0ea5e9"
VIOLET = "#8b5cf6"

STATUS_LABELS = {
    "pending": ("На рассмотрении", WARNING),
    "approved": ("Одобрено", SUCCESS),
    "rejected": ("Отклонено", DANGER),
}


def card(content, width=None, expand=False, padding=20):
    """Белая карточка с мягкой тенью — базовый строительный блок UI."""
    return ft.Container(
        content=content,
        bgcolor=CARD_BG,
        border_radius=16,
        padding=padding,
        width=width,
        expand=expand,
        shadow=ft.BoxShadow(
            blur_radius=16,
            spread_radius=1,
            color="#1a0f172a",  # полупрозрачная тень ARGB
            offset=ft.Offset(0, 4),
        ),
    )


def stat_card(title, value, icon, color=PRIMARY, subtitle=""):
    """Карточка показателя для дашборда."""
    return card(
        ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, color=color, size=28),
                    bgcolor=f"{color}1a",  # 10% прозрачности
                    border_radius=12,
                    padding=12,
                ),
                ft.Column(
                    controls=[
                        ft.Text(str(value), size=24, weight="bold", color=TEXT_DARK),
                        ft.Text(title, size=13, color=TEXT_MUTED),
                    ] + ([ft.Text(subtitle, size=11, color=TEXT_MUTED)] if subtitle else []),
                    spacing=2,
                ),
            ],
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=True,
    )


def section_title(text, sub=None):
    controls = [ft.Text(text, size=20, weight="bold", color=TEXT_DARK)]
    if sub:
        controls.append(ft.Text(sub, size=13, color=TEXT_MUTED))
    return ft.Column(controls, spacing=2)


def status_chip(status):
    label, color = STATUS_LABELS.get(status, (status or "?", TEXT_MUTED))
    return ft.Container(
        content=ft.Text(label, size=11, color=color, weight="bold"),
        bgcolor=f"{color}1a",
        border_radius=999,
        padding=ft.Padding(10, 4, 10, 4),
    )


def page_header(page_obj, title, on_back=None, actions=None):
    """Единая шапка внутренних страниц: кнопка «назад», заголовок, действия."""
    left = []
    if on_back:
        left.append(ft.IconButton(ft.Icons.ARROW_BACK_ROUNDED, tooltip="В главное меню",
                                  on_click=on_back))
    left.append(ft.Text(title, size=22, weight="bold", color=TEXT_DARK))
    row = ft.Row(left, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    if actions:
        row.controls.append(ft.Container(expand=True))
        row.controls.extend(actions)
    return row


def navigate(page_obj, cls_name):
    """Переход к странице внутри ft.Page (используется новыми страницами)."""
    from pages.registry import get_page
    page_obj.controls.clear()
    page_obj.add(get_page(cls_name)(page_obj))
    page_obj.update()
