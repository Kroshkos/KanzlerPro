"""Печать личного дела курсанта в PDF (шаблон по форме MKR).

Документ формируется движком reportlab с кириллическим шрифтом и состоит
из разделов:

  * титульная страница «ЛИЧНОЕ ДЕЛО» (ФИО, группа, курс, период обучения);
  * основные сведения (дата/место рождения, гражданство, семейное
    положение, состояние здоровья, вредные привычки);
  * контакты;
  * документы (паспорт, военный билет);
  * образование и служебные данные (должность, звание — из истории
    кадровых приказов);
  * успеваемость (последние результаты сессий);
  * поощрения и взыскания;
  * Дорожная карта: накопленные баллы, статусы семестров, ИПР.

Функция ``generate_personal_file_pdf`` возвращает путь к созданному файлу в
каталоге data/reports.
"""

import os
from datetime import datetime

import repositories as repo
from config import REPORTS_DIR
from database import (
    BLOCK_NAMES,
    execute_query,
    get_encouragements_by_student,
    get_individual_plan,
    get_penalties_by_student,
    get_reviews,
    get_semester_status,
    get_student_total_points,
)
from utils import to_int

try:
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

if REPORTLAB_AVAILABLE:
    from report_generator import CYRILLIC_FONT
else:
    CYRILLIC_FONT = "Helvetica"


def _val(row, key):
    """Безопасное чтение поля строки-результата."""
    try:
        v = row[key]
    except (KeyError, IndexError, TypeError):
        v = None
    return str(v).strip() if v not in (None, "") else "—"


def _full_name(s):
    return " ".join(x for x in [_val(s, "o_surname"), _val(s, "o_name"),
                                _val(s, "o_lastname")] if x != "—") or "—"


def generate_personal_file_pdf(student_id):
    """Собирает личное дело курсанта в PDF; возвращает путь к файлу."""
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("Для печати PDF установите зависимость: pip install reportlab")

    s = repo.get_student_full(student_id)
    if not s:
        raise ValueError("Курсант не найден")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    fname = f"L_D_{_val(s, 'o_surname')}_{_val(s, 'o_name')}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    path = os.path.join(REPORTS_DIR, fname)

    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=15 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Личное дело — {_full_name(s)}")
    story = _collect_personal_file_flowables(s, student_id, doc)
    doc.build(story)
    return path


def generate_batch_personal_files_pdf(student_ids):
    """Пакетная печать: несколько личных дел одним PDF-документом.

    Каждое дело начинается с новой страницы; в начале документа — оглавление
    со списком курсантов. Возвращает путь к созданному файлу.
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("Для печати PDF установите зависимость: pip install reportlab")
    ids = [i for i in (to_int(x) for x in (student_ids or [])) if i is not None]
    if not ids:
        raise ValueError("Не выбран ни один курсант")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    fname = f"L_D_paket_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    path = os.path.join(REPORTS_DIR, fname)

    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=15 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Личные дела (пакет) — {len(ids)} шт.")

    st_title = ParagraphStyle("bt", fontName=CYRILLIC_FONT, fontSize=15,
                              leading=19, alignment=1)
    st_body = ParagraphStyle("bb", fontName=CYRILLIC_FONT, fontSize=9.5,
                             leading=13)

    story = []
    ok_ids = []
    # Оглавление пакета
    story.append(Paragraph("ЛИЧНЫЕ ДЕЛА (ПАКЕТНЫЙ ДОКУМЕНТ)", st_title))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"Всего курсантов: {len(ids)} · "
                           f"Дата формирования: {datetime.now():%d.%m.%Y}",
                           st_body))
    story.append(Spacer(1, 4 * mm))
    toc_rows = []
    for sid in ids:
        s = repo.get_student_full(sid)
        if not s:
            continue
        ok_ids.append(sid)
        toc_rows.append([str(len(toc_rows) + 1), _full_name(s),
                         _val(s, "o_group_name"), _val(s, "o_course")])
    if toc_rows:
        data = [[Paragraph(f"<b>{h}</b>", st_body)
                 for h in ["№", "Фамилия И.О.", "Группа", "Курс"]]]
        data += [[Paragraph(str(c), st_body) for c in r] for r in toc_rows]
        t = Table(data, colWidths=[12 * mm, 90 * mm, 45 * mm, 30 * mm],
                  repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.4, rl_colors.HexColor("#cbd5e1")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    # Сами дела: каждое с новой страницы
    from reportlab.platypus import PageBreak
    for n, sid in enumerate(ok_ids, start=1):
        story.append(PageBreak())
        s = repo.get_student_full(sid)
        story.extend(_collect_personal_file_flowables(
            s, sid, doc, label=f"ЛИЧНОЕ ДЕЛО — №{n} из {len(ok_ids)}"))

    if not ok_ids:
        story.append(Paragraph("Ни одного курсанта не найдено.", st_body))

    doc.build(story)
    return path


def _collect_personal_file_flowables(s, student_id, doc, label=None):
    """Собирает flowables одного личного дела (для одиночной и пакетной печати)."""
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("Для печати PDF установите зависимость: pip install reportlab")

    st_title = ParagraphStyle("t", fontName=CYRILLIC_FONT, fontSize=15,
                              leading=19, alignment=1)
    st_h2 = ParagraphStyle("h2", fontName=CYRILLIC_FONT, fontSize=12,
                           leading=16, spaceBefore=10, spaceAfter=4,
                           textColor=rl_colors.HexColor("#1e293b"))
    st_body = ParagraphStyle("b", fontName=CYRILLIC_FONT, fontSize=9.5,
                             leading=13)
    st_small = ParagraphStyle("s", fontName=CYRILLIC_FONT, fontSize=8.5,
                              leading=11,
                              textColor=rl_colors.HexColor("#64748b"))

    story = []

    def section(title):
        story.append(Paragraph(title, st_h2))
        story.append(HRFlowable(width="100%", thickness=0.7,
                                color=rl_colors.HexColor("#cbd5e1"),
                                spaceAfter=4))

    def kv_table(pairs):
        rows = [[Paragraph(k, st_body), Paragraph(v, st_body)]
                for k, v in pairs]
        t = Table(rows, colWidths=[55 * mm, 122 * mm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4,
             rl_colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    def simple_table(headers, rows, widths=None):
        data = [[Paragraph(f"<b>{h}</b>", st_body) for h in headers]]
        for r in rows:
            data.append([Paragraph(str(c), st_body) for c in r])
        w = widths or [None] * len(headers)
        t = Table(data, colWidths=w, repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0),
             rl_colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.4,
             rl_colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        t.setStyle(TableStyle(style))
        story.append(t)

    # ---------------- Титульный лист ----------------
    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph(label or "ЛИЧНОЕ ДЕЛО", st_title))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(_full_name(s), st_title))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        f"Группа {_val(s, 'o_group_name')} · {_val(s, 'o_course')}-й курс",
        ParagraphStyle("sub", parent=st_body, alignment=1)))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"Дата формирования: {datetime.now():%d.%m.%Y}", st_small))
    story.append(Spacer(1, 6 * mm))

    # ---------------- Основные сведения ----------------
    section("1. Основные сведения")
    kv_table([
        ("Фамилия, имя, отчество", _full_name(s)),
        ("Дата рождения", _val(s, "o_date_of_birth")),
        ("Место рождения", _val(s, "o_place_of_birth")),
        ("Гражданство", _val(s, "o_citizenship")),
        ("Национальность", _val(s, "o_nationality")),
        ("Семейное положение", _val(s, "o_marital_status")),
        ("Состояние здоровья", _val(s, "o_health_status")),
        ("Вредные привычки", _val(s, "o_bad_habits")),
        ("Интересы", _val(s, "o_interests")),
        ("Навыки", _val(s, "o_skills")),
    ])

    # ---------------- Контакты ----------------
    section("2. Контактные данные")
    kv_table([
        ("Адрес проживания", _val(s, "kontact_residential_address")),
        ("Телефон", _val(s, "kontact_number")),
        ("Электронная почта", _val(s, "kontact_email")),
    ])

    # ---------------- Документы ----------------
    section("3. Документы")
    passport = " ".join(x for x in [
        _val(s, "ld_passport_series"), _val(s, "ld_passport_number")]
        if x != "—")
    vb = " ".join(x for x in [
        _val(s, "ld_vb_series"), _val(s, "ld_vb_number")] if x != "—")
    kv_table([
        ("Паспорт (серия/номер)", passport),
        ("Паспорт: кем и когда выдан",
         f"{_val(s, 'ld_passport_place_given')} · {_val(s, 'ld_passport_date_given')}"),
        ("Военный билет (серия/номер)", vb),
        ("Личный номер В/Б", _val(s, "ld_vb_personal_number")),
        ("Дата призыва", _val(s, "ld_vb_vs_date_of_conscription")),
    ])

    # ---------------- Служебные данные ----------------
    section("4. Служебные данные")
    pos_row = repo.get_last_position_row(student_id)
    rank = repo.get_last_rank(student_id)
    pos = ""
    if pos_row is not None:
        try:
            pos = pos_row["position"] or ""
        except Exception:
            pos = str(pos_row[0] if len(pos_row) else "")
    kv_table([
        ("Должность (актуальная)", pos or "—"),
        ("Звание (актуальное)", rank or "—"),
        ("Образование до службы",
         _val(s, "o_occupation_before_military_service")),
    ])

    # ---------------- Успеваемость ----------------
    section("5. Результаты сессий")
    sr_rows = execute_query(
        "SELECT subject, type_exam, grade, date FROM session_results "
        "WHERE student_id = ? ORDER BY date DESC LIMIT 20",
        (student_id,), fetch=True)
    if sr_rows:
        simple_table(
            ["Дисциплина", "Вид", "Оценка", "Дата"],
            [[_val(r, "subject"), _val(r, "type_exam"),
              _val(r, "grade"), _val(r, "date")] for r in sr_rows],
            widths=[70 * mm, 30 * mm, 25 * mm, 40 * mm])
    else:
        story.append(Paragraph("Результатов пока нет.", st_body))

    # ---------------- Поощрения / взыскания ----------------
    section("6. Дисциплинарная практика")
    enc = get_encouragements_by_student(student_id) or []
    pen = get_penalties_by_student(student_id) or []
    if enc:
        story.append(Paragraph("Поощрения:", st_body))
        simple_table(["Тип", "Основание", "Дата", "Приказ"],
                     [[_val(r, "encouragement_type"), _val(r, "reason"),
                       _val(r, "date_obj"), _val(r, "order_number")]
                      for r in enc],
                     widths=[35 * mm, 65 * mm, 25 * mm, 30 * mm])
    if pen:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Взыскания:", st_body))
        simple_table(["Тип", "Основание", "Дата", "Приказ"],
                     [[_val(r, "penalty_type"), _val(r, "reason"),
                       _val(r, "date_obj"), _val(r, "order_number")]
                      for r in pen],
                     widths=[35 * mm, 65 * mm, 25 * mm, 30 * mm])
    if not enc and not pen:
        story.append(Paragraph("Поощрений и взысканий нет.", st_body))

    # ---------------- Дорожная карта ----------------
    section("7. Дорожная карта (Road Map)")
    total = get_student_total_points(student_id)
    reviews = get_reviews(student_id=student_id, status="approved") or []
    block_names = dict(BLOCK_NAMES)
    per_block = {}
    for r in reviews:
        ach = execute_query(
            "SELECT block FROM achievements_catalog WHERE id = ?",
            (r["achievement_id"],), fetch=True)
        if ach:
            b = ach[0]["block"]
            per_block[b] = per_block.get(b, 0) + (r["final_points"] or 0)
    kv_table([
        ("Накоплено баллов (одобрено)", str(total)),
        ("Одобренных достижений", str(len(reviews))),
    ])
    if per_block:
        story.append(Spacer(1, 2 * mm))
        simple_table(["Блок достижений", "Баллы"],
                     [[block_names.get(int(b), f"Блок {b}"), str(p)]
                      for b, p in sorted(per_block.items())],
                     widths=[120 * mm, 55 * mm])

    sems = sorted({to_int(r["semester"]) for r in reviews
                   if to_int(r["semester"]) is not None})
    if sems:
        story.append(Spacer(1, 3 * mm))
        rows = []
        for sem in sems:
            st = get_semester_status(student_id, sem) or {}
            try:
                cand = bool(st.get("is_candidate")) if st else False
                res = bool(st.get("is_resident")) if st else False
            except AttributeError:
                cand = res = False
            pts = get_student_total_points(student_id, semester=sem)
            rows.append([str(sem), str(pts),
                         "Да" if cand else "Нет",
                         "Да" if res else "Нет"])
        simple_table(["Семестр", "Баллы за семестр",
                      "Кандидат", "Резидент"], rows,
                     widths=[30 * mm, 60 * mm, 40 * mm, 40 * mm])

    plan = get_individual_plan(student_id, sems[-1]) if sems else None
    if plan:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Индивидуальный план развития "
                               f"(семестр {sems[-1]}):", st_body))
        plan_text = ""
        try:
            plan_text = plan["plan_text"] or ""
        except (KeyError, TypeError):
            plan_text = str(plan[0]) if len(plan) else ""
        if plan_text.strip():
            story.append(Paragraph(plan_text.replace("\n", "<br/>"), st_body))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "Подпись командира (начальника) ______________________ / ____________ /",
        st_body))

    return story
