"""Рейтинг Дорожной карты (перенос рейтинга из MKR).

Таблица мест по накопленным баллам с фильтром по семестру, ступенями
(Участник / Активист / Кандидат / Резидент) и сводными карточками.
Данные берутся из общей базы KanzlerPro (курсанты + expert-решения).
"""

import flet as ft
from roadmap_rating import (
    ACTIVIST_THRESHOLD,
    CANDIDATE_THRESHOLD,
    RESIDENT_THRESHOLD,
    STEPS_ORDER,
    build_rating,
    get_semesters_with_data,
    rating_summary,
)
from theme import PRIMARY, SUCCESS, TEXT_DARK, TEXT_MUTED, VIOLET, WARNING, card, stat_card
from utils import to_int

STEP_COLORS = {
    "Участник": TEXT_MUTED,
    "Активист": SUCCESS,
    "Кандидат": WARNING,
    "Резидент": VIOLET,
}


class RoadmapRatingPage(ft.Column):
    def __init__(self, page, parent=None):
        super().__init__()
        self._fpage = page
        self.nav_parent = parent
        self.width = 1160
        self.expand_width = True
        self.spacing = 14
        self.controls = [
            ft.Text("Рейтинг Дорожной карты", size=24, weight="bold",
                    color=TEXT_DARK),
            ft.Text(f"Ступени: Активист ≥ {ACTIVIST_THRESHOLD} баллов за "
                    f"семестр · Кандидат ≥ {CANDIDATE_THRESHOLD} · "
                    f"Резидент ≥ {RESIDENT_THRESHOLD} (накопленные)",
                    size=13, color=TEXT_MUTED),
            self._build_filters(),
            ft.Row(spacing=10, wrap=True),   # сводные карточки (заполняет refresh)
            card(ft.Column([], spacing=8), expand=True),  # таблица (заполняет refresh)
        ]
        self._summary_row = self.controls[2]
        self._table_card = self.controls[3]
        self.refresh(None)

    # ---------------- фильтры ----------------
    def _build_filters(self):
        semesters = get_semesters_with_data()
        self.sem_dd = ft.Dropdown(
            label="Семестр", width=180, dense=True,
            options=[ft.dropdown.Option(key="", text="Все семестры")] +
                    [ft.dropdown.Option(key=str(s), text=f"Семестр {s}")
                     for s in semesters],
            value="", on_select=self.refresh)
        self.group_tf = ft.TextField(
            label="Группа (фильтр)", width=200, dense=True,
            border_radius=10, on_change=self.refresh)
        self.name_tf = ft.TextField(
            label="ФИО (фильтр)", width=260, dense=True,
            border_radius=10, on_change=self.refresh)
        return ft.Row([
            self.sem_dd, self.group_tf, self.name_tf,
            ft.IconButton(ft.Icons.REFRESH, tooltip="Обновить",
                          on_click=self.refresh),
        ], spacing=10, wrap=True)

    # ---------------- тело ----------------
    def _selected_semester(self):
        return to_int(self.sem_dd.value)

    def _step_chip(self, step):
        color = STEP_COLORS.get(step, TEXT_MUTED)
        return ft.Container(
            content=ft.Text(step, size=11, color=color, weight="bold"),
            bgcolor=f"{color}1a", border_radius=999,
            padding=ft.Padding(10, 4, 10, 4))

    def refresh(self, e):
        semester = self._selected_semester()
        rows = build_rating(semester)
        group_f = (self.group_tf.value or "").strip().lower()
        name_f = (self.name_tf.value or "").strip().lower()
        if group_f:
            rows = [r for r in rows if group_f in r["group"].lower()]
        if name_f:
            rows = [r for r in rows if name_f in r["full_name"].lower()]
        summary = rating_summary(semester)

        # Сводные карточки по ступеням
        icons = {"Участник": ft.Icons.PERSON, "Активист": ft.Icons.WHATSHOT,
                 "Кандидат": ft.Icons.BOLT, "Резидент": ft.Icons.DIAMOND}
        cards = []
        for step in STEPS_ORDER:
            cards.append(stat_card(step, summary["counts"][step],
                                   icons[step], STEP_COLORS[step]))
        cards.append(stat_card("Охват", f"{summary['coverage']}%",
                               ft.Icons.DONUT_LARGE, PRIMARY))
        self._summary_row.controls = cards
        self._summary_row.wrap = True

        # Таблица
        header_cells = ["Место", "ФИО", "Группа", "Баллы семестра",
                        "Накоплено", "Ступень"]
        header = ft.Row(
            controls=[
                ft.Container(ft.Text(h, size=12, weight="bold",
                                     color=TEXT_DARK),
                             width=w, expand=(i == 1))
                for i, (h, w) in enumerate(zip(header_cells,
                                               [70, 0, 110, 140, 110, 130]))],
            spacing=6)
        body = []
        medal = {1: ft.Icons.EMOJI_EVENTS, 2: ft.Icons.STAR, 3: ft.Icons.STAR_BORDER}
        for r in rows[:400]:
            place_txt = (ft.Icon(medal[r["place"]], size=18, color=WARNING)
                         if r["place"] in medal else
                         ft.Text(str(r["place"]), size=13, weight="bold",
                                 color=TEXT_MUTED))
            row = ft.Row(
                controls=[
                    ft.Container(place_txt, width=70, alignment="center"),
                    ft.Container(ft.Text(r["full_name"], size=13,
                                         color=TEXT_DARK), expand=True),
                    ft.Container(ft.Text(r["group"], size=13,
                                         color=TEXT_MUTED), width=110),
                    ft.Container(ft.Text(str(r["points_sem"]), size=13,
                                         color=TEXT_DARK), width=140),
                    ft.Container(ft.Text(str(r["points_cum"]), size=13,
                                         weight="bold", color=PRIMARY),
                                 width=110),
                    ft.Container(self._step_chip(r["status"]), width=130),
                ], spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER)
            body.append(row)
        if not rows:
            body = [ft.Text("Нет данных — добавьте курсантов и одобренные "
                            "экспертные решения.", size=13, color=TEXT_MUTED)]

        self._table_card.content = ft.Column(
            [header, ft.Divider(height=1, color="#e2e8f0")] + body,
            spacing=8, scroll=ft.ScrollMode.AUTO, height=520)
        try:
            self.update()
        except RuntimeError:
            pass  # страница ещё не добавлена на page (первичная сборка)
