"""Генератор отчётных форм Дорожной карты (перенос из MKR).

Формы (как в оригинальном MKR, но поверх схемы KanzlerPro):
  Р-1 — индивидуальный отчёт курсанта за семестр (xlsx / pdf);
  Р-2 — ведомость семестрового рейтинга группы (xlsx / pdf);
  Р-3 — сводный отчёт по группе: ступени + блоки достижений (xlsx / pdf);
  Р-4 — сводный академический отчёт по системе (план/факт) (xlsx / pdf);
  Р-5 — отчёт о ходе выполнения ИПР (xlsx / pdf).

Экспорт в Excel использует openpyxl, в PDF — reportlab с подбором
кириллического шрифта (Windows / Linux / macOS).
"""

import os
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from config import REPORTS_DIR
from roadmap_rating import build_rating, rating_summary, STEPS_ORDER

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.units import inch
    from reportlab.lib import colors as rl_colors
    from reportlab.platypus import (SimpleDocTemplate, Table as RlTable,
                                    TableStyle, Paragraph, Spacer)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _register_cyrillic_font():
    candidates = [
        "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/times.ttf",
        "C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/verdana.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("CyrillicFont", path))
                return "CyrillicFont"
            except Exception:
                continue
    return "Helvetica"


if REPORTLAB_AVAILABLE:
    CYRILLIC_FONT = _register_cyrillic_font()
    _styles = getSampleStyleSheet()
    STYLE_NORMAL = ParagraphStyle(
        "N", parent=_styles["Normal"], fontName=CYRILLIC_FONT, fontSize=9)
    STYLE_HEADING = ParagraphStyle(
        "H", parent=_styles["Heading4"], fontName=CYRILLIC_FONT, fontSize=11)
    STYLE_TITLE = ParagraphStyle(
        "T", parent=_styles["Title"], fontName=CYRILLIC_FONT,
        alignment=TA_CENTER, fontSize=15)

STATUS_RU = {"pending": "На проверке", "approved": "Подтверждено",
             "rejected": "Отклонено"}


# ---------------------------------------------------------------------------
# Данные
# ---------------------------------------------------------------------------

def _student_row(student_id):
    from database import execute_query
    rows = execute_query(
        "SELECT id, o_surname, o_name, o_lastname, o_group_name, o_course "
        "FROM students WHERE id = ?", (student_id,), fetch=True)
    return rows[0] if rows else None


def _full_name(s):
    return " ".join(x for x in (s["o_surname"], s["o_name"], s["o_lastname"])
                    if x)


def _reviews_of(student_id, semester=None):
    from database import get_reviews
    return get_reviews(student_id=student_id, semester=semester)


def _points_sum(reviews, only_approved=True, up_to_semester=None):
    total = 0
    for r in reviews:
        if only_approved and r["status"] != "approved":
            continue
        if up_to_semester is not None and (r["semester"] or 0) > up_to_semester:
            continue
        total += r["final_points"] or 0
    return total


def _block_names():
    from database import BLOCK_NAMES
    return BLOCK_NAMES


def ensure_output_dir():
    os.makedirs(REPORTS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Стили Excel
# ---------------------------------------------------------------------------

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
TITLE_FONT = Font(bold=True, size=13)
THIN_BORDER = Border(*[Side(style="thin", color="B0B0B0")] * 4)


def _style_sheet(ws, header_row, cols):
    for col in range(1, cols + 1):
        c = ws.cell(header_row, col)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
    for row in ws.iter_rows(min_row=header_row + 1, max_col=cols):
        for c in row:
            c.border = THIN_BORDER
    widths = {}
    for row in ws.iter_rows(max_col=cols):
        for c in row:
            if c.value is not None:
                widths[c.column] = max(widths.get(c.column, 10),
                                       min(len(str(c.value)) + 2, 60))
    from openpyxl.utils import get_column_letter
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w


# ---------------------------------------------------------------------------
# Р-1: индивидуальный отчёт курсанта
# ---------------------------------------------------------------------------

def generate_R1(student_id, semester, fmt="xlsx"):
    ensure_output_dir()
    s = _student_row(student_id)
    if not s:
        raise ValueError("Курсант не найден")
    ext = "pdf" if fmt == "pdf" else "xlsx"
    path = os.path.join(
        REPORTS_DIR, f"R1_{_full_name(s)}_sem{semester or 'all'}.{ext}")
    all_rev = _reviews_of(student_id)
    semesters = ([semester] if semester else
                 sorted({r["semester"] for r in all_rev if r["semester"]}))

    if ext == "xlsx":
        wb = openpyxl.Workbook()
        if not semesters:
            ws = wb.active
            ws.title = "Нет данных"
            ws["A1"] = "Нет достижений ни за один семестр"
        else:
            wb.remove(wb.active)
            for sem in semesters:
                ws = wb.create_sheet(title=f"Семестр {sem}")
                _fill_R1(ws, s, sem, all_rev)
        wb.save(path)
    else:
        _pdf_R1(path, s, semesters, all_rev)
    return path


def _fill_R1(ws, s, semester, all_rev):
    sem_rev = [r for r in all_rev if r["semester"] == semester]
    approved = [r for r in sem_rev if r["status"] == "approved"]
    points_sum = _points_sum(sem_rev)
    total_cum = _points_sum(all_rev)

    ws["A1"] = "Р-1: Индивидуальный отчёт обучающегося"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:F1")
    info = [("ФИО", _full_name(s)), ("Группа", s["o_group_name"]),
            ("Курс", s["o_course"]),
            ("Баллы за семестр", points_sum),
            ("Накопленный балл", total_cum)]
    row = 3
    for k, v in info:
        ws.cell(row, 1, k).font = Font(bold=True)
        ws.cell(row, 2, v)
        row += 1
    row += 1
    headers = ["№", "Достижение", "Базовые баллы", "Итоговый балл",
               "Статус", "Комментарий"]
    for col, h in enumerate(headers, 1):
        ws.cell(row, col, h)
    header_row = row
    row += 1
    for idx, r in enumerate(sem_rev, 1):
        ws.cell(row, 1, idx)
        ws.cell(row, 2, r["ach_name"] or "")
        ws.cell(row, 3, r["points"])
        ws.cell(row, 4, r["final_points"] if r["final_points"] is not None else "")
        ws.cell(row, 5, STATUS_RU.get(r["status"], r["status"]))
        ws.cell(row, 6, r["expert_comment"] or "")
        row += 1
    _style_sheet(ws, header_row, len(headers))


def _pdf_R1(path, s, semesters, all_rev):
    doc = SimpleDocTemplate(path, pagesize=letter)
    story = [Paragraph("Р-1: Индивидуальный отчёт обучающегося", STYLE_TITLE),
             Spacer(1, 0.2 * inch),
             Paragraph(f"<b>{_full_name(s)}</b> | группа {s['o_group_name']}",
                       STYLE_NORMAL),
             Spacer(1, 0.2 * inch)]
    for sem in semesters:
        sem_rev = [r for r in all_rev if r["semester"] == sem]
        story.append(Paragraph(f"Семестр {sem}. Сумма баллов: "
                               f"{_points_sum(sem_rev)}", STYLE_HEADING))
        data = [["№", "Достижение", "Итог", "Статус"]]
        for i, r in enumerate(sem_rev, 1):
            data.append([str(i), Paragraph(str(r["ach_name"] or ""),
                                           STYLE_NORMAL),
                         str(r["final_points"] or ""),
                         STATUS_RU.get(r["status"], r["status"])])
        t = RlTable(data, colWidths=[0.4 * inch, 3.4 * inch, 0.8 * inch,
                                     1.4 * inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), CYRILLIC_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1F4E78")),
            ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, rl_colors.grey),
        ]))
        story += [t, Spacer(1, 0.3 * inch)]
    if not semesters:
        story.append(Paragraph("Нет достижений ни за один семестр",
                               STYLE_NORMAL))
    doc.build(story)


# ---------------------------------------------------------------------------
# Р-2: ведомость семестрового рейтинга
# ---------------------------------------------------------------------------

def generate_R2(group_name, semester, fmt="xlsx"):
    ensure_output_dir()
    rows = [r for r in build_rating(semester) if not group_name
            or r["group"] == group_name]
    ext = "pdf" if fmt == "pdf" else "xlsx"
    safe = (group_name or "все группы").replace("/", "-")
    path = os.path.join(REPORTS_DIR, f"R2_{safe}_sem{semester}.{ext}")

    headers = ["№", "ФИО", "Группа", "Р_сем", "Р_накоп", "Ступень"]
    if ext == "xlsx":
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Рейтинг"
        ws["A1"] = (f"Р-2: Ведомость семестрового рейтинга "
                    f"({safe}, семестр {semester})")
        ws["A1"].font = TITLE_FONT
        row = 3
        for col, h in enumerate(headers, 1):
            ws.cell(row, col, h)
        header_row = row
        row += 1
        for r in rows:
            for col, val in enumerate(
                    [r["place"], r["full_name"], r["group"], r["points_sem"],
                     r["points_cum"], r["status"]], 1):
                ws.cell(row, col, val)
            row += 1
        _style_sheet(ws, header_row, len(headers))
        wb.save(path)
    else:
        data = [headers] + [[str(r["place"]), r["full_name"], r["group"],
                             str(r["points_sem"]), str(r["points_cum"]),
                             r["status"]] for r in rows]
        _pdf_table(path, f"Р-2: Рейтинг группы {safe} (семестр {semester})",
                   data, [0.4, 2.6, 1.0, 0.7, 0.9, 1.0])
    return path


# ---------------------------------------------------------------------------
# Р-3: сводный отчёт по группе (ступени + блоки)
# ---------------------------------------------------------------------------

def generate_R3(group_name, semester, fmt="xlsx"):
    ensure_output_dir()
    from database import execute_query
    rows = [r for r in build_rating(semester) if not group_name
            or r["group"] == group_name]
    block_names = _block_names()
    block_sums = {i: 0 for i in block_names}
    for r in rows:
        revs = _reviews_of(r["student_id"], semester)
        for rev in revs:
            if rev["status"] != "approved":
                continue
            ach = execute_query(
                "SELECT block FROM achievements_catalog WHERE id = ?",
                (rev["achievement_id"],), fetch=True)
            if ach:
                b = ach[0]["block"]
                block_sums[b] = block_sums.get(b, 0) + (rev["final_points"] or 0)

    counts = {step: sum(1 for r in rows if r["status"] == step)
              for step in STEPS_ORDER}
    ext = "pdf" if fmt == "pdf" else "xlsx"
    safe = (group_name or "все группы").replace("/", "-")
    path = os.path.join(REPORTS_DIR, f"R3_{safe}_sem{semester}.{ext}")

    if ext == "xlsx":
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Сводный отчёт"
        ws["A1"] = f"Р-3: Сводный отчёт ({safe}, семестр {semester})"
        ws["A1"].font = TITLE_FONT
        row = 3
        ws.cell(row, 1, "Ступени").font = Font(bold=True)
        row += 1
        hdr = ["Ступень", "Количество"]
        for col, h in enumerate(hdr, 1):
            ws.cell(row, col, h)
        hr = row
        row += 1
        for step in STEPS_ORDER:
            ws.cell(row, 1, step)
            ws.cell(row, 2, counts[step])
            row += 1
        _style_sheet(ws, hr, 2)
        row += 1
        ws.cell(row, 1, "Баллы по блокам достижений").font = Font(bold=True)
        row += 1
        for col, h in enumerate(["Блок", "Баллы"], 1):
            ws.cell(row, col, h)
        hr2 = row
        row += 1
        for b, name in block_names.items():
            ws.cell(row, 1, name)
            ws.cell(row, 2, block_sums.get(b, 0))
            row += 1
        _style_sheet(ws, hr2, 2)
        wb.save(path)
    else:
        data = [["Ступень", "Кол-во"]] + [[s, str(counts[s])]
                                          for s in STEPS_ORDER]
        data += [["", ""], ["Блок", "Баллы"]]
        data += [[n, str(block_sums.get(b, 0))]
                 for b, n in block_names.items()]
        _pdf_table(path, f"Р-3: Сводный отчёт {safe} (семестр {semester})",
                   data, [3.0, 1.5])
    return path


# ---------------------------------------------------------------------------
# Р-4: сводный академический отчёт (план/факт)
# ---------------------------------------------------------------------------

TARGET_ACTIVISTS = 1000   # план к дек. 2026 (значения из MKR)
TARGET_CANDIDATES = 200
TARGET_RESIDENTS = 50


def generate_R4(semester, fmt="xlsx"):
    ensure_output_dir()
    summary = rating_summary(semester)
    counts = summary["counts"]
    rows_data = [
        ["Охват", "100%", f"{summary['coverage']}%",
         f"{summary['coverage']}%"],
        ["Активисты (>=75)", TARGET_ACTIVISTS, counts["Активист"],
         f"{round(counts['Активист'] / TARGET_ACTIVISTS * 100, 1)}%"],
        ["Кандидаты (>=150)", TARGET_CANDIDATES, counts["Кандидат"],
         f"{round(counts['Кандидат'] / TARGET_CANDIDATES * 100, 1)}%"],
        ["Резиденты (>=250)", TARGET_RESIDENTS, counts["Резидент"],
         f"{round(counts['Резидент'] / TARGET_RESIDENTS * 100, 1)}%"],
    ]
    ext = "pdf" if fmt == "pdf" else "xlsx"
    path = os.path.join(REPORTS_DIR, f"R4_sem{semester or 'all'}.{ext}")
    headers = ["Показатель", "План", "Факт", "% выполнения"]

    if ext == "xlsx":
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Сводный отчёт"
        ws["A1"] = "Р-4: Сводный академический отчёт по системе ПРО.ВМедА"
        ws["A1"].font = TITLE_FONT
        ws["A2"] = f"Семестр: {semester if semester else 'Все'}"
        row = 4
        for col, h in enumerate(headers, 1):
            ws.cell(row, col, h)
        hr = row
        row += 1
        for d in rows_data:
            for col, val in enumerate(d, 1):
                ws.cell(row, col, val)
            row += 1
        _style_sheet(ws, hr, len(headers))
        wb.save(path)
    else:
        data = [headers] + [[str(v) for v in d] for d in rows_data]
        _pdf_table(path, "Р-4: Сводный академический отчёт", data,
                   [2.0, 1.2, 1.2, 1.4])
    return path


# ---------------------------------------------------------------------------
# Р-5: отчёт по ИПР
# ---------------------------------------------------------------------------

def generate_R5(student_id, semester, fmt="xlsx"):
    ensure_output_dir()
    from database import get_individual_plan
    s = _student_row(student_id)
    if not s:
        raise ValueError("Курсант не найден")
    plan = get_individual_plan(student_id, semester)
    ext = "pdf" if fmt == "pdf" else "xlsx"
    path = os.path.join(REPORTS_DIR,
                        f"R5_{_full_name(s)}_sem{semester}.{ext}")
    tasks = ([line.strip() for line in plan["plan_text"].split("\n")
              if line.strip()] if plan else [])

    if ext == "xlsx":
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "ИПР"
        ws["A1"] = "Р-5: Отчёт о ходе выполнения индивидуального плана"
        ws["A1"].font = TITLE_FONT
        meta = [("Студент", _full_name(s)), ("Группа", s["o_group_name"]),
                ("Семестр", semester),
                ("Статус плана", plan["status"] if plan else "нет ИПР"),
                ("Утверждён", (plan["approved_by"] or "") if plan else "")]
        row = 3
        for k, v in meta:
            ws.cell(row, 1, k).font = Font(bold=True)
            ws.cell(row, 2, v)
            row += 1
        row += 1
        headers = ["№", "Задача", "Плановый срок", "Отметка о выполнении"]
        for col, h in enumerate(headers, 1):
            ws.cell(row, col, h)
        hr = row
        row += 1
        for i, task in enumerate(tasks, 1):
            ws.cell(row, 1, i)
            ws.cell(row, 2, task)
            row += 1
        _style_sheet(ws, hr, len(headers))
        wb.save(path)
    else:
        data = [["№", "Задача"]] + [[str(i), Paragraph(t, STYLE_NORMAL)]
                                    for i, t in enumerate(tasks, 1)]
        story_intro = (_full_name(s) +
                       (f" | статус плана: {plan['status']}" if plan
                        else " | ИПР не найден"))
        _pdf_table(path, f"Р-5: Отчёт по ИПР (семестр {semester})", data,
                   [0.5, 4.5], subtitle=story_intro)
    return path


# ---------------------------------------------------------------------------
# Общая печать PDF-таблицы
# ---------------------------------------------------------------------------

def _pdf_table(path, title, data, widths_inch, subtitle=None):
    doc = SimpleDocTemplate(path, pagesize=landscape(letter))
    story = [Paragraph(title, STYLE_TITLE), Spacer(1, 0.15 * inch)]
    if subtitle:
        story += [Paragraph(subtitle, STYLE_NORMAL), Spacer(1, 0.15 * inch)]
    t = RlTable(data, colWidths=[w * inch for w in widths_inch])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), CYRILLIC_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1F4E78")),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, rl_colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"Сформирован: "
                           f"{datetime.now().strftime('%d.%m.%Y %H:%M')}",
                           STYLE_NORMAL))
    doc.build(story)


FORMS_INFO = [
    ("R1", "Индивидуальный отчёт курсанта", True, True),
    ("R2", "Ведомость семестрового рейтинга", False, True),
    ("R3", "Сводный отчёт по группе", False, True),
    ("R4", "Сводный академический отчёт (план/факт)", False, True),
    ("R5", "Отчёт по выполнению ИПР", True, True),
]
