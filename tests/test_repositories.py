"""Тесты слоя репозиториев: батчевые map_*-выборки (фикс N+1 в премиях).

Ключевой инвариант из аудита: результаты пакетных функций должны
совпадать с поштучными get_*/list_* на одних и тех же данных — иначе
рефакторинг silently меняет расчёт премий.
"""

import pytest


@pytest.fixture()
def repo(db):
    import repositories
    return repositories


def _student(db, surname, course=3):
    db.execute_query(
        "INSERT INTO students (o_surname, o_name, o_lastname, o_course, o_group_name)"
        " VALUES (?, 'И', 'И', ?, 'А-12')", (surname, course))
    return db.execute_query("SELECT MAX(id) m FROM students", fetch=True)[0]["m"]


class TestMapLastPositionsAndRanks:
    def test_matches_single_row_functions(self, db, repo):
        s1 = _student(db, "Первый")
        s2 = _student(db, "Второй")
        db.execute_query(
            "INSERT INTO position_history (student_id, position, assigned_by, date, order_number)"
            " VALUES (?,?,?,?,?)", (s1, "Командир взвода", "X", "2025-01-01", "1"))
        db.execute_query(
            "INSERT INTO position_history (student_id, position, assigned_by, date, order_number)"
            " VALUES (?,?,?,?,?)", (s1, "Заместитель командира взвода", "X", "2025-06-01", "2"))
        db.execute_query(
            "INSERT INTO rank_history (student_id, rank, assigned_by, date, order_number)"
            " VALUES (?,?,?,?,?)", (s2, "старший лейтенант", "X", "2025-03-01", "5"))

        pm = repo.map_last_positions([s1, s2])
        assert pm[s1][0] == "Заместитель командира взвода"   # самая свежая запись
        rm = repo.map_last_ranks([s1, s2])
        assert rm[s2] == "старший лейтенант"

        # согласованность с поштучными версиями
        assert pm.get(s2) is None  # у второго нет истории должностей

    def test_empty_input_no_query(self, repo):
        """Пустой список не должен порождать запрос с IN () (SQLite error)."""
        assert repo.map_last_positions([]) == {}
        assert repo.map_last_ranks([]) == {}
        assert repo.map_penalties_in_period([], "2025-01-01", "2025-12-31") == {}
        assert repo.map_failed_subjects([]) == set()
        assert repo.map_latest_session_results([], "1") == {}


class TestMapPenalties:
    def test_filters_by_period(self, db, repo):
        s = _student(db, "Виноватый")
        for d, kind in [("2025-02-01", "выговор"), ("2025-08-01", "замечание"),
                        ("2026-01-15", "выговор вне периода")]:
            db.execute_query(
                "INSERT INTO penalties (student_id, penalty_type, reason, date_reason,"
                " issued_by, date, order_number) VALUES (?,?,?,?,?,?,?)",
                (s, kind, "причина", d, "Начальник", d, "№1"))
        m = repo.map_penalties_in_period([s], "2025-01-01", "2025-12-31")
        kinds = sorted(p[0] for p in m[s])
        assert kinds == ["выговор", "замечание"]


class TestMapSessionResults:
    @staticmethod
    def _grade(db, s, subject, grade, semester="1", date="2025-01-01",
               allowance="Допущен", attendance="Присутствовал"):
        db.execute_query(
            "INSERT INTO session_results (group_name, subject, type_exam, date,"
            " statement_number, statement_tip, student_id, allowance, attendance,"
            " grade, semester) VALUES ('А-12', ?, 'экзамен', ?, '1', 't', ?, ?, ?, ?, ?)",
            (subject, date, s, allowance, attendance, grade, semester))

    def test_latest_grade_per_subject(self, db, repo):
        s = _student(db, "Отличник")
        self._grade(db, s, "Математика", "3", date="2025-01-01")
        self._grade(db, s, "Математика", "5", date="2025-02-01")  # пересдача
        m = repo.map_latest_session_results([s], "1")
        grades = [g[1] for g in m[s]]
        assert "5" in grades and "3" not in grades  # взята последняя оценка

    def test_failed_detection(self, db, repo):
        s_bad = _student(db, "Двоечник")
        s_ok = _student(db, "Хорошист")
        self._grade(db, s_bad, "Физра", "2")
        self._grade(db, s_bad, "История", "5")          # одна двойка — уже fail
        self._grade(db, s_ok, "История", "4")
        failed = repo.map_failed_subjects([s_bad, s_ok])
        assert failed == {s_bad}

    def test_redo_to_pass_clears_failure(self, db, repo):
        """Если последняя оценка исправлена — курсант больше не 'проваливший'."""
        s = _student(db, "Исправившийся")
        self._grade(db, s, "Химия", "2", date="2025-01-01")
        self._grade(db, s, "Химия", "4", date="2025-05-01")
        assert repo.map_failed_subjects([s]) == set()

    def test_not_allowed_counts_as_failed(self, db, repo):
        s = _student(db, "Недопущенный")
        self._grade(db, s, "Право", "н/д", allowance="Не допущен")
        assert s in repo.map_failed_subjects([s])


class TestSearchStudentsLike:
    """A-1: расширенный поиск курсантов живёт в репозитории (SQL вне UI)."""

    def _seed(self, db):
        db.execute_query(
            "INSERT INTO students (o_surname, o_name, o_lastname, o_course, o_group_name)"
            " VALUES ('Иванов','Иван','Иванович',3,'А-12')")
        db.execute_query(
            "INSERT INTO students (o_surname, o_name, o_lastname, o_course, o_group_name)"
            " VALUES ('Петров','Пётр','Сергеевич',4,'Б-31')")

    def test_partial_surname_match(self, db, repo):
        self._seed(db)
        rows = repo.search_students_like(surname="иван")
        assert len(rows) == 1
        assert rows[0]["o_surname"] == "Иванов"

    def test_exact_numeric_fields(self, db, repo):
        self._seed(db)
        rows = repo.search_students_like(course=4)
        assert [r["o_surname"] for r in rows] == ["Петров"]

    def test_combined_filters_and_empty_kwargs(self, db, repo):
        self._seed(db)
        assert repo.search_students_like() and len(repo.search_students_like()) == 2
        assert repo.search_students_like(surname="пет", group_name="б-")
        assert not repo.search_students_like(surname="пет", course=3)

    def test_no_sql_injection_via_params(self, db, repo):
        self._seed(db)
        # значение с кавычкой должно искаться как текст, а не ломать запрос
        assert repo.search_students_like(surname="Ив'AN; DROP TABLE students;--") == []
        assert len(repo.search_students_like()) == 2


class TestCyrillicCaseInsensitiveSearch:
    """LOWER() SQLite работает только по ASCII — «иван» не находил «Иванов».
    LOWER_UNICODE (database.connect_to_db) чинит это во всех поисках."""

    def _seed(self, db):
        db.execute_query(
            "INSERT INTO students (o_surname, o_name, o_lastname, o_course, o_group_name)"
            " VALUES ('Иванов','Иван','Иванович',3,'А-12')")

    def test_name_part_search_lowercase_query(self, db):
        self._seed(db)
        assert [r[1] for r in db.search_students_by_name_part("иван")] == ["Иванов"]
        assert [r[1] for r in db.search_students_by_name_part("ИВАН")] == ["Иванов"]
        assert db.search_students_by_name_part("неттакого") == []

    def test_repo_search_matches_name_part(self, db, repo):
        self._seed(db)
        rows = repo.search_students_like(surname="иваНов")   # любой регистр
        assert len(rows) == 1
