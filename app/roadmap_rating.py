"""Рейтинг Дорожной карты (перенос аналитики из MKR: dashboard/analytics).

Пороги ступеней (наследие MKR):
  Активист   >= 75 баллов за семестр
  Кандидат   >= 150 накопленных баллов (плюс заявка)
  Резидент   >= 250 накопленных баллов (плюс утверждение)
"""

ACTIVIST_THRESHOLD = 75
CANDIDATE_THRESHOLD = 150
RESIDENT_THRESHOLD = 250

STEPS_ORDER = ["Участник", "Активист", "Кандидат", "Резидент"]


def get_semesters_with_data():
    from database import execute_query
    rows = execute_query(
        "SELECT DISTINCT semester FROM roadmap_reviews "
        "WHERE semester IS NOT NULL ORDER BY semester", fetch=True)
    return [r["semester"] for r in rows]


def _points_sql(semester=None, cumulative=False):
    """SQL-выражение суммарных баллов и параметры для него."""
    if semester is None:
        where = "status = 'approved' AND final_points IS NOT NULL"
        params = []
        if not cumulative:
            pass  # все семестры = накопленные
    else:
        sem = int(semester)
        if cumulative:
            where = "status = 'approved' AND final_points IS NOT NULL AND semester <= ?"
            params = [sem]
        else:
            where = "status = 'approved' AND final_points IS NOT NULL AND semester = ?"
            params = [sem]
    return where, params


def status_for(student_id, points_sem, points_cum, ss_row):
    """Ступень курсанта по баллам и статусам student_semester_status."""
    is_resident = bool(ss_row and ss_row["is_resident"])
    is_candidate = bool(ss_row and ss_row["is_candidate"])
    if is_resident or points_cum >= RESIDENT_THRESHOLD:
        return "Резидент"
    if is_candidate or points_cum >= CANDIDATE_THRESHOLD:
        return "Кандидат"
    if points_sem >= ACTIVIST_THRESHOLD:
        return "Активист"
    return "Участник"


def build_rating(semester=None):
    """Список строк рейтинга: ФИО, группа, баллы семестра, накопленные, ступень.

    semester=None -> рейтинг по всем семестрам (накопленным).
    """
    from database import execute_query

    students = execute_query(
        "SELECT id, o_surname, o_name, o_lastname, o_group_name "
        "FROM students ORDER BY o_surname, o_name", fetch=True)

    where_sem, p_sem = _points_sql(semester, cumulative=False)
    per_sem = {r["student_id"]: r["p"] for r in execute_query(
        f"SELECT student_id, SUM(final_points) p FROM roadmap_reviews "
        f"WHERE {where_sem} GROUP BY student_id", tuple(p_sem), fetch=True)}

    where_cum, p_cum = _points_sql(semester, cumulative=True)
    per_cum = {r["student_id"]: r["p"] for r in execute_query(
        f"SELECT student_id, SUM(final_points) p FROM roadmap_reviews "
        f"WHERE {where_cum} GROUP BY student_id", tuple(p_cum), fetch=True)}

    if semester is not None:
        ss_map = {r["student_id"]: r for r in execute_query(
            "SELECT * FROM student_semester_status WHERE semester = ?",
            (int(semester),), fetch=True)}
    else:
        ss_map = {}
        for r in execute_query(
                "SELECT * FROM student_semester_status", fetch=True):
            prev = ss_map.get(r["student_id"])
            if prev is None or (r["is_resident"] and not prev["is_resident"]) \
                    or (r["is_candidate"] and not prev["is_candidate"]):
                ss_map[r["student_id"]] = r

    rows = []
    for s in students:
        ps = per_sem.get(s["id"], 0) or 0
        pc = per_cum.get(s["id"], 0) or 0
        name = " ".join(x for x in
                        (s["o_surname"], s["o_name"], s["o_lastname"]) if x)
        rows.append({
            "student_id": s["id"],
            "full_name": name,
            "group": s["o_group_name"] or "",
            "points_sem": ps,
            "points_cum": pc,
            "status": status_for(s["id"], ps, pc, ss_map.get(s["id"])),
        })
    rows.sort(key=lambda r: (-r["points_cum"], r["full_name"]))
    for i, r in enumerate(rows, 1):
        r["place"] = i
    return rows


def rating_summary(semester=None):
    """Сводка по ступеням: {'Участник': n, ...} + охват."""
    rows = build_rating(semester)
    counts = {step: 0 for step in STEPS_ORDER}
    with_reviews = set()
    for r in rows:
        counts[r["status"]] += 1
        if r["points_cum"] > 0:
            with_reviews.add(r["student_id"])
    total = len(rows)
    coverage = round(len(with_reviews) / total * 100, 1) if total else 0
    return {"counts": counts, "total": total, "coverage": coverage}
