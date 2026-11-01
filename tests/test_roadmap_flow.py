"""Тесты формулы расчёта итоговых баллов (calculate_final_points) и жизненного
цикла заявок Road Map (add_review / update_review / delete_review).

Мотивация аудита:
  * T-3 — финансовые расчёты (баллы → премии) должны быть покрыты табличными
    тестами: коэффициенты, нулевые сроки, отрицательные бонусы;
  * T-5 — регрессия на исправленные баги: add_review проставляет created_at,
    delete_review реально удаляет строку (раньше «удаление» через
    update_review(status='deleted') лишь скрывало запись — тихая порча данных),
    get_reviews не падает без колонки created_at.
"""

import pytest

# ---------- Формула итоговых баллов ----------

class TestCalculateFinalPoints:
    def test_avg_score_passthrough(self, db):
        """Тип 'avg_score' возвращает базовые баллы без коэффициентов."""
        assert db.calculate_final_points("avg_score", 42, k_ur=2.0, k_role=3.0) == 42

    def test_grant_ignores_coefficients(self, db):
        """Грант — фиксированная сумма, коэффициенты не применяются."""
        assert db.calculate_final_points("grant", 10, grant_amount=5000,
                                         k_ur=2.0) == 5000

    def test_multiplicative_coefficients(self, db):
        """Базовые баллы умножаются на все коэффициенты подряд."""
        got = db.calculate_final_points("ms", 100, k_ur=1.5, k_role=1.2,
                                       k_vn=1.1, k_st=1.0)
        assert got == round(100 * 1.5 * 1.2 * 1.1)

    def test_month_multiplies_by_duration(self, db):
        """Тип 'month': произведение коэффициентов умножается на число месяцев."""
        got = db.calculate_final_points("month", 10, k_ur=1.0, k_role=1.0,
                                        k_vn=1.0, k_st=1.0, duration_months=4)
        assert got == 40

    def test_zero_duration_clamped_to_one(self, db):
        """duration_months <= 0 не обнуляет результат (min = 1 месяц)."""
        for bad in (0, -5, None):
            assert db.calculate_final_points("month", 7, duration_months=bad) == 7

    def test_ip_bonus_added_after_rounding(self, db):
        """Бонус за ИПР прибавляется к итогу (после применения коэффициентов)."""
        got = db.calculate_final_points("ms", 10, k_ur=1.0, ip_bonus=5)
        assert got == 15

    def test_none_and_empty_inputs_are_safe(self, db):
        """None/пустые значения коэффициентов трактуются как нейтральные."""
        assert db.calculate_final_points("ms", None) == 0
        assert db.calculate_final_points("ms", 50, k_ur=None, k_role=None,
                                         k_vn=None, k_st=None) == 50

    def test_negative_bonus_allowed(self, db):
        """Отрицательный бонус (вычет) корректно уменьшает итог."""
        assert db.calculate_final_points("ms", 100, ip_bonus=-30) == 70


# ---------- Жизненный цикл заявок на экспертизу ----------

@pytest.fixture()
def seeded(db):
    """Курсант + достижение в каталоге (10 баллов, тип ms)."""
    sid = db.add_student({"o_surname": "Петров", "o_name": "Иван",
                          "o_lastname": "Иванович", "o_course": 1,
                          "o_group_name": "А-1"})
    db.add_achievement("A1", 1, "Меткий выстрел", 10,
                       version="", calc_type="ms",
                       actor_role=db.ADMIN_ROLE)
    return db, sid


class TestReviewLifecycle:
    def test_add_review_sets_created_at(self, seeded):
        """Регрессия: заявка обязана получать created_at (колонка добавлена
        миграцией; без неё запрос уведомлений тихо падал)."""
        db, sid = seeded
        db.add_review(sid, "A1", semester=1, status="pending", actor_role=db.ADMIN_ROLE)
        row = db.execute_query(
            "SELECT created_at FROM roadmap_reviews", fetch=True)[0]
        assert row["created_at"]  # непустое значение времени создания

    def test_approved_review_gets_final_points(self, seeded):
        db, sid = seeded
        db.add_review(sid, "A1", semester=1, status="approved", k_ur=1.5, actor_role=db.ADMIN_ROLE)
        rows = db.get_reviews(student_id=sid, status="approved")
        assert rows[0]["final_points"] == round(10 * 1.5)

    def test_pending_review_has_no_final_points(self, seeded):
        db, sid = seeded
        db.add_review(sid, "A1", semester=1, status="pending", actor_role=db.ADMIN_ROLE)
        rows = db.get_reviews(student_id=sid, status="pending")
        assert rows[0]["final_points"] is None

    def test_delete_review_removes_row(self, seeded):
        """Регрессия на тихую порчу данных: удаление — физический DELETE,
        а не мягкая отметка status='deleted'."""
        db, sid = seeded
        db.add_review(sid, "A1", semester=1, status="pending", actor_role=db.ADMIN_ROLE)
        rid = db.get_reviews(student_id=sid)[0]["id"]
        db.delete_review(rid, actor_role=db.ADMIN_ROLE)
        assert db.get_reviews(student_id=sid) == []
        left = db.execute_query(
            "SELECT COUNT(*) AS c FROM roadmap_reviews WHERE id = ?",
            (rid,), fetch=True)[0]["c"]
        assert left == 0

    def test_count_pending_reviews(self, seeded):
        db, sid = seeded
        assert db.count_pending_reviews() == 0
        db.add_review(sid, "A1", semester=1, status="pending", actor_role=db.ADMIN_ROLE)
        db.add_review(sid, "A1", semester=2, status="approved", actor_role=db.ADMIN_ROLE)
        assert db.count_pending_reviews() == 1

    def test_total_points_only_approved(self, seeded):
        """В суммарный рейтинг курсанта попадают только подтверждённые заявки."""
        db, sid = seeded
        db.add_review(sid, "A1", semester=1, status="pending", actor_role=db.ADMIN_ROLE)
        assert db.get_student_total_points(sid, semester=1) == 0
        rid = db.get_reviews(student_id=sid)[0]["id"]
        db.update_review(rid, "approved", final_points=10, actor_role=db.ADMIN_ROLE)
        assert db.get_student_total_points(sid, semester=1) == 10
