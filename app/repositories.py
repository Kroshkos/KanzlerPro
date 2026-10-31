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

from typing import List, Optional, Tuple

from database import execute_query

Row = Tuple


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


def get_position_history(student_id: int) -> List[Row]:
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


def get_rank_history(student_id: int) -> List[Row]:
    # Исправлено: исторически запрос читал колонку position из rank_history,
    # что падало на SQLite >= 3.25 (CTE-алиасы теперь запрещены в SELECT).
    return execute_query(
        """SELECT rank, assigned_by, date, order_number
           FROM rank_history WHERE student_id = ?""",
        (student_id,),
        fetch=True,
    ) or []


def get_last_position_row(student_id: int) -> Optional[Row]:
    """Последняя запись должности: (position, date, order_number)."""
    rows = execute_query(
        """SELECT position, date, order_number FROM position_history
           WHERE student_id = ? ORDER BY date DESC LIMIT 1""",
        (student_id,),
        fetch=True,
    )
    return rows[0] if rows else None


def get_last_rank(student_id: int) -> Optional[str]:
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


def list_groups_like(fragment: str) -> List[str]:
    """Названия групп, содержащие фрагмент. Шаблон LIKE формируется здесь,
    значение передаётся параметром (безопасно)."""
    return [r[0] for r in execute_query(
        "SELECT DISTINCT o_group_name FROM students WHERE o_group_name LIKE ?",
        (f"%{fragment}%",),
        fetch=True,
    ) or []]


def list_students_by_group(group_name: str) -> List[Row]:
    return execute_query(
        """SELECT id, o_surname, o_name, o_lastname FROM students
           WHERE o_group_name = ?""",
        (group_name,),
        fetch=True,
    ) or []


def get_first_statement_result(student_id: int, subject_name: str,
                               exam_type: str, semester: str) -> Optional[Row]:
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
                                            exam_type: str, semester: str) -> List[Row]:
    """Результаты по первой и повторной-1 ведомостям: [(grade, attendance, allowance), ...]."""
    return execute_query(
        """SELECT grade, attendance, allowance FROM session_results
           WHERE student_id = ? AND subject = ? AND type_exam = ?
             AND semester = ? AND (statement_tip = 'Первая' OR statement_tip = 'Повторная 1')""",
        (student_id, subject_name, exam_type, semester),
        fetch=True,
    ) or []


def find_student_id_by_full_name(full_name: str) -> Optional[int]:
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


def list_students_by_course(course: int) -> List[Row]:
    """(id, фамилия, имя, отчество, личный номер, должность из личного дела)."""
    return execute_query(
        """SELECT id, o_surname, o_name, o_lastname,
                  ld_vb_personal_number, ld_vb_post_post
           FROM students WHERE o_course = ?""",
        (course,),
        fetch=True,
    ) or []


def list_penalties_in_period(student_id: int,
                             start_date: str, end_date: str) -> List[Row]:
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


def list_latest_session_results(student_id: int, semester: str) -> List[Row]:
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


# ---------- Личное дело (PersonalFilePage) ----------


def get_student_full(student_id: int) -> Optional[Row]:
    rows = execute_query(
        "SELECT * FROM students WHERE id = ?",
        (student_id,),
        fetch=True,
    )
    return rows[0] if rows else None


def update_student_fields(student_id: int, fields: dict) -> bool:
    """Частичное обновление личного дела через белый список STUDENT_FIELDS."""
    from database import update_student

    return update_student(student_id, fields)
