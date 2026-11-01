"""Слой репозиториев приложения «Канцлер».

Архитектурное решение: весь SQL, работающий с пользовательскими данными,
вынесен из UI-слоя (ui.py) в репозитории. Каждый метод:

  * принимает типизированные аргументы вместо «сырых» строк запросов;
  * передаёт ВСЕ значения только как параметры sqlite3 (?, ?) — никакого
    подстановочного конкатенирования, то есть классическая защита от
    SQL-инъекций;
  * возвращает кортежи строк (или None/пустой список).

Модуль database.py остаётся низкоуровневым драйвером (соединение, init_db,
execute_query); ui.py обращается к данным через репозитории, а не через
execute_query напрямую.

ВНИМАНИЕ: имена колонок соответствуют реальной схеме kanzler.db
(position_history.date, session_results.subject/type_exam/statement_tip/
allowance и т.д.).
"""


from database import execute_query

Row = tuple


# ---------- Позиции (PositionChangePage) ----------


def add_position(student_id: int, position: str, assigned_by: str,
                 date_str: str, order_number: str) -> None:
    """Добавляет запись об изменении должности."""
    execute_query(
        """INSERT INTO position_history
           (student_id, position, assigned_by, date, order_number)
           VALUES (?, ?, ?, ?, ?)""",
        (student_id, position, assigned_by, date_str, order_number),
    )


def get_position_history(student_id: int) -> list[Row]:
    return execute_query(
        """SELECT position, assigned_by, date, order_number
           FROM position_history WHERE student_id = ?""",
        (student_id,),
        fetch=True,
    ) or []


# ---------- Воинские звания (RankChangePage) ----------


def add_rank(student_id: int, rank: str, assigned_by: str,
             date_str: str, order_number: str) -> None:
    """Добавляет запись об изменении воинского звания."""
    execute_query(
        """INSERT INTO rank_history
           (student_id, rank, assigned_by, date, order_number)
           VALUES (?, ?, ?, ?, ?)""",
        (student_id, rank, assigned_by, date_str, order_number),
    )


def get_rank_history(student_id: int) -> list[Row]:
    # Исправлено: исторически запрос читал колонку position из rank_history,
    # что падало на SQLite >= 3.25 (CTE-алиасы теперь запрещены в SELECT).
    return execute_query(
        """SELECT rank, assigned_by, date, order_number
           FROM rank_history WHERE student_id = ?""",
        (student_id,),
        fetch=True,
    ) or []


def get_last_position_row(student_id: int) -> Row | None:
    """Последняя запись должности: (position, date, order_number)."""
    rows = execute_query(
        """SELECT position, date, order_number FROM position_history
           WHERE student_id = ? ORDER BY date DESC LIMIT 1""",
        (student_id,),
        fetch=True,
    )
    return rows[0] if rows else None


def get_last_rank(student_id: int) -> str | None:
    rows = execute_query(
        """SELECT rank FROM rank_history
           WHERE student_id = ? ORDER BY date DESC LIMIT 1""",
        (student_id,),
        fetch=True,
    )
    return rows[0][0] if rows else None


# ---------- Сессии / ведомости (SessionResultsPage) ----------


def count_session_results(group_name: str, subject_name: str, date_str: str) -> int:
    return execute_query(
        """SELECT COUNT(*) FROM session_results
           WHERE group_name = ? AND subject = ? AND date = ?""",
        (group_name, subject_name, date_str),
        fetch=True,
    )[0][0]


def list_groups_like(fragment: str) -> list[str]:
    """Названия групп, содержащие фрагмент. Шаблон LIKE формируется здесь,
    значение передаётся параметром (безопасно)."""
    return [r[0] for r in execute_query(
        "SELECT DISTINCT o_group_name FROM students WHERE o_group_name LIKE ?",
        (f"%{fragment}%",),
        fetch=True,
    ) or []]


def list_students_by_group(group_name: str) -> list[Row]:
    return execute_query(
        """SELECT id, o_surname, o_name, o_lastname FROM students
           WHERE o_group_name = ?""",
        (group_name,),
        fetch=True,
    ) or []


def get_first_statement_result(student_id: int, subject_name: str,
                               exam_type: str, semester: str) -> Row | None:
    """Результат по первой ведомости: (grade, attendance, allowance)."""
    rows = execute_query(
        """SELECT grade, attendance, allowance FROM session_results
           WHERE student_id = ? AND subject = ? AND type_exam = ?
             AND semester = ? AND statement_tip = 'Первая'""",
        (student_id, subject_name, exam_type, semester),
        fetch=True,
    )
    return rows[0] if rows else None


def get_statement_results_first_and_repeat1(student_id: int, subject_name: str,
                                            exam_type: str, semester: str) -> list[Row]:
    """Результаты по первой и повторной-1 ведомостям: [(grade, attendance, allowance), ...]."""
    return execute_query(
        """SELECT grade, attendance, allowance FROM session_results
           WHERE student_id = ? AND subject = ? AND type_exam = ?
             AND semester = ? AND (statement_tip = 'Первая' OR statement_tip = 'Повторная 1')""",
        (student_id, subject_name, exam_type, semester),
        fetch=True,
    ) or []


def find_student_id_by_full_name(full_name: str) -> int | None:
    rows = execute_query(
        """SELECT id FROM students
           WHERE o_surname || ' ' || o_name || ' ' || o_lastname = ?""",
        (full_name,),
        fetch=True,
    )
    return rows[0][0] if rows else None


def session_result_exists(student_id: int, subject_name: str, exam_type: str,
                          statement_number: str, statement_type: str) -> bool:
    rows = execute_query(
        """SELECT COUNT(*) FROM session_results
           WHERE student_id = ? AND subject = ? AND type_exam = ?
             AND statement_number = ? AND statement_tip = ?""",
        (student_id, subject_name, exam_type, statement_number, statement_type),
        fetch=True,
    )
    return bool(rows and rows[0][0] > 0)


def add_session_result(group_name: str, subject_name: str, exam_type: str,
                       date_str: str, statement_number: str, statement_type: str,
                       student_id: int, admission: str, attendance: str,
                       grade: str, semester: str) -> None:
    execute_query(
        """INSERT INTO session_results
           (group_name, subject, type_exam, date, statement_number,
            statement_tip, student_id, allowance, attendance, grade, semester)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (group_name, subject_name, exam_type, date_str, statement_number,
         statement_type, student_id, admission, attendance, grade, semester),
    )


# ---------- Премии / сводки (PremiaWorkPage) ----------


def list_students_by_course(course: int) -> list[Row]:
    """(id, фамилия, имя, отчество, личный номер, должность из личного дела)."""
    return execute_query(
        """SELECT id, o_surname, o_name, o_lastname,
                  ld_vb_personal_number, ld_vb_post_post
           FROM students WHERE o_course = ?""",
        (course,),
        fetch=True,
    ) or []


def list_penalties_in_period(student_id: int,
                             start_date: str, end_date: str) -> list[Row]:
    """(penalty_type, issued_by, date) за период."""
    return execute_query(
        """SELECT penalty_type, issued_by, date FROM penalties
           WHERE student_id = ? AND date BETWEEN ? AND ?""",
        (student_id, start_date, end_date),
        fetch=True,
    ) or []


def has_failed_subjects(student_id: int) -> bool:
    """Есть ли предмет, по которому ПОСЛЕДНЯЯ оценка — «2», отсутствие
    или недопуск (по всем семестрам)."""
    rows = execute_query(
        """SELECT COUNT(*) FROM (
               SELECT subject, grade, allowance, attendance,
                   ROW_NUMBER() OVER (PARTITION BY subject ORDER BY date DESC) AS rn
               FROM session_results
               WHERE student_id = ?
           ) AS latest_grades
           WHERE rn = 1 AND (allowance = 'Не допущен' OR attendance = 'Отсутствовал' OR grade = '2')""",
        (student_id,),
        fetch=True,
    )
    return bool(rows and rows[0][0] > 0)


def list_latest_session_results(student_id: int, semester: str) -> list[Row]:
    """Последние результаты по каждому предмету за семестр: (subject, grade, allowance, attendance)."""
    return execute_query(
        """SELECT subject, grade, allowance, attendance FROM (
               SELECT subject, grade, allowance, attendance, date,
                   ROW_NUMBER() OVER (PARTITION BY subject ORDER BY date DESC) AS rn
               FROM session_results
               WHERE student_id = ? AND semester = ?
           ) AS latest_grades
           WHERE rn = 1""",
        (student_id, semester),
        fetch=True,
    ) or []


# ---------- Премии (PremiaWorkPage): батчевые версии N+1-запросов ----------
# show_results_click раньше для каждого курсанта курса выполнял 4 отдельных
# запроса (должность, звание, взыскания, сессия). При 100+ курсантов это
# сотни open/close соединения. Ниже — те же выборки одним запросом на весь
# курс; ключ словарей — student_id.


def map_last_positions(student_ids: list[int]) -> dict:
    """{student_id: (position, date, order_number)} — последняя должность."""
    if not student_ids:
        return {}
    marks = ",".join("?" * len(student_ids))
    rows = execute_query(
        f"""SELECT student_id, position, date, order_number FROM (
               SELECT student_id, position, date, order_number,
                      ROW_NUMBER() OVER (PARTITION BY student_id
                                         ORDER BY date DESC) AS rn
               FROM position_history WHERE student_id IN ({marks})
           ) WHERE rn = 1""",
        tuple(student_ids), fetch=True) or []
    return {r["student_id"]: (r["position"], r["date"], r["order_number"])
            for r in rows}


def map_last_ranks(student_ids: list[int]) -> dict:
    """{student_id: rank} — последнее воинское звание."""
    if not student_ids:
        return {}
    marks = ",".join("?" * len(student_ids))
    rows = execute_query(
        f"""SELECT student_id, rank FROM (
               SELECT student_id, rank,
                      ROW_NUMBER() OVER (PARTITION BY student_id
                                         ORDER BY date DESC) AS rn
               FROM rank_history WHERE student_id IN ({marks})
           ) WHERE rn = 1""",
        tuple(student_ids), fetch=True) or []
    return {r["student_id"]: r["rank"] for r in rows}


def map_penalties_in_period(student_ids: list[int],
                            start_date: str, end_date: str) -> dict:
    """{student_id: [(penalty_type, issued_by, date), ...]} за период."""
    if not student_ids:
        return {}
    marks = ",".join("?" * len(student_ids))
    rows = execute_query(
        f"""SELECT student_id, penalty_type, issued_by, date FROM penalties
            WHERE student_id IN ({marks}) AND date BETWEEN ? AND ?""",
        (*student_ids, start_date, end_date), fetch=True) or []
    out: dict = {}
    for r in rows:
        out.setdefault(r["student_id"], []).append(
            (r["penalty_type"], r["issued_by"], r["date"]))
    return out


def map_failed_subjects(student_ids: list[int]) -> set:
    """Множество student_id, у которых есть провальный последний результат."""
    if not student_ids:
        return set()
    marks = ",".join("?" * len(student_ids))
    rows = execute_query(
        f"""SELECT DISTINCT student_id FROM (
               SELECT student_id, grade, allowance, attendance,
                      ROW_NUMBER() OVER (PARTITION BY student_id, subject
                                         ORDER BY date DESC) AS rn
               FROM session_results WHERE student_id IN ({marks})
           ) WHERE rn = 1 AND (allowance = 'Не допущен'
                              OR attendance = 'Отсутствовал' OR grade = '2')""",
        tuple(student_ids), fetch=True) or []
    return {r["student_id"] for r in rows}


def map_latest_session_results(student_ids: list[int],
                               semester: str) -> dict:
    """{student_id: [(subject, grade, allowance, attendance), ...]} за семестр."""
    if not student_ids:
        return {}
    marks = ",".join("?" * len(student_ids))
    rows = execute_query(
        f"""SELECT student_id, subject, grade, allowance, attendance FROM (
               SELECT student_id, subject, grade, allowance, attendance,
                      ROW_NUMBER() OVER (PARTITION BY student_id, subject
                                         ORDER BY date DESC) AS rn
               FROM session_results
               WHERE student_id IN ({marks}) AND semester = ?
           ) WHERE rn = 1""",
        (*student_ids, semester), fetch=True) or []
    out: dict = {}
    for r in rows:
        out.setdefault(r["student_id"], []).append(
            (r["subject"], r["grade"], r["allowance"], r["attendance"]))
    return out


# ---------- Личное дело (PersonalFilePage) ----------


def get_student_full(student_id: int) -> Row | None:
    rows = execute_query(
        "SELECT * FROM students WHERE id = ?",
        (student_id,),
        fetch=True,
    )
    return rows[0] if rows else None


def update_student_fields(student_id: int, fields: dict,
                          actor_role=None) -> bool:
    """Частичное обновление личного дела через белый список STUDENT_FIELDS."""
    from database import update_student

    return update_student(student_id, fields, actor_role=actor_role)


def get_student_columns() -> list:
    """Имена колонок таблицы students в порядке SELECT * (PRAGMA table_info).

    Нужен UI-слою, чтобы не хардкодить индексы вроде student_data[24]:
    порядок колонок меняется при любом ALTER TABLE.
    """
    rows = execute_query("PRAGMA table_info(students)", fetch=True) or []
    return [r[1] for r in rows]


def add_student(student_data: dict, actor_role=None) -> int:
    """Создать курсанта по плоскому dict колонок students.

    Тонкая обёртка над database.add_student(): INSERT со строго параметризованным
    списком колонок (белый список STUDENT_FIELDS), возврат lastrowid.
    Вызывающая сторона (форма kadri_page) передаёт данные, собранные и
    нормализованные через FIELD_ALIASES/_validated_form_data.
    """
    from database import add_student as _db_add_student

    return _db_add_student(student_data, actor_role=actor_role)


def delete_student(student_id: int) -> bool:
    """Полностью удалить курсанта и связанные записи (каскад вручную).

    Используется там, где нужен РЕАЛЬНЫЙ DELETE (например, отклонённая заявка
    с status="deleted"), а не мягкое удаление флагом. Дочерние таблицы без FK-
    каскада чистятся явно, чтобы не оставлять сиротские строки. Файл фото —
    через photo_storage.delete_photo() (вызывающая сторона передаёт o_photo).
    """
    from database import connect_to_db

    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        for table in ("position_history", "rank_history", "encouragements",
                      "penalties", "session_results", "roadmap_reviews",
                      "individual_plans", "manual_scores"):
            try:
                cursor.execute(f"DELETE FROM {table} WHERE student_id = ?",
                               (student_id,))
            except Exception:
                # Таблица может отсутствовать в старых БД — удаляем запись
                # о курсанте в любом случае, но ошибку логируем, не глотаем.
                from utils_logger import log_except
                log_except(f"delete_student: таблица {table}")
        cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()
