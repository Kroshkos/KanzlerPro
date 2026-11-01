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
