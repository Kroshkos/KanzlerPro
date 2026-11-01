"""Табличные тесты чистых расчётных функций (BACKLOG T-3).

Две формулы вынесены из UI в модули без Flet/БД и покрываются
parametrized-тестами:
  * database.calculate_final_points — итоговые баллы рейтинга Road Map;
  * pages.premia_calc.compute_premia — размер премии курсанта.

Особые случаи зафиксированы значениями «как в проде»: None-коэффициенты,
нулевой срок, приоритет дисциплинарных оснований над оценками.
"""

import pytest


# ---------- calculate_final_points ----------

POINTS_CASES = [
    # (calc_type, base, kwargs, expected)
    ("ms", 100, {"k_ur": 1.5, "k_role": 1.2, "k_vn": 1.0, "k_st": 1.0}, 180),
    ("ms", 100, {}, 100),                                   # все k=1
    ("month", 10, {"duration_months": 3}, 30),              # база * месяцы
    ("month", 10, {"duration_months": 0}, 10),              # нулевой срок = 1 мес
    ("month", 10, {"duration_months": None}, 10),           # None = 1 мес
    ("avg_score", 42, {"k_ur": 2.0, "k_role": 3.0}, 42),    # коэффициенты не влияют
    ("grant", 10, {"grant_amount": 5000}, 5000),            # считается сумма гранта
    ("grant", 10, {}, 0),                                   # гранта нет -> 0
    ("ms", 100, {"ip_bonus": 15}, 115),                     # бонус за ИПР
    ("ms", None, {}, 0),                                    # None-база как 0
    ("ms", 100, {"k_ur": None}, 100),                       # None-коэф. как 1.0
    ("ms", 73, {"k_ur": 1.0, "ip_bonus": 0}, 73),           # без округления
    ("ms", 10, {"k_ur": 1.15}, 12),                         # 11.5 -> banker's round
]


@pytest.mark.parametrize("calc_type,base,kwargs,expected", POINTS_CASES)
def test_calculate_final_points_table(db, calc_type, base, kwargs, expected):
    assert db.calculate_final_points(calc_type, base, **kwargs) == expected


# ---------- compute_premia ----------

POS_CMDR1 = ("Командир 1 отделения", "2024-09-01", "123")
POS_KURSANT = ("курсант", "2024-09-01", "1")


def _premia(**kw):
    from pages import premia_calc
    args = dict(min_grade=None, has_penalties=False, last_position=None,
                has_failed_subjects=False, has_session_results=True)
    args.update(kw)
    return premia_calc.compute_premia(**args)


PREMIA_CASES = [
    # (kwargs, ожидаемый размер, ожидаемое основание в причине)
    (dict(min_grade="5"), 25, ""),
    (dict(min_grade="4"), 15, ""),
    (dict(min_grade="3"), 5, ""),
    (dict(min_grade="2"), 1, "Неудовлетворительный результат сессии"),
    # провал любого предмета за любую сессию — всегда 1% (наивысший приоритет)
    (dict(min_grade="5", has_failed_subjects=True), 1,
     "Не допущен, отсутствовал или оценка 2"),
    # взыскание перекривает хорошую оценку, но не перекрывает провал предмета
    (dict(min_grade="5", has_penalties=True), 1,
     "Наличие дисциплинарного взыскания"),
    (dict(min_grade="2", has_penalties=True), 1,
     "Неудовлетворительный результат сессии"),
    # нет данных о сессии выбранного семестра
    (dict(min_grade=None, has_session_results=False), "???", "Нет данных о сессии"),
    (dict(min_grade=None), "???", "Нет данных о сессии"),
    # должность сверх курсанта/слушателя -> 25% с приказом в причине
    (dict(min_grade="3", last_position=POS_CMDR1), 25,
     "Занимает должность командира 1 отделения"),
    (dict(min_grade="3", last_position=POS_KURSANT), 5, ""),
    # должность НЕ перекривает взыскание и провал
    (dict(min_grade="4", has_penalties=True, last_position=POS_CMDR1), 1,
     "Наличие дисциплинарного взыскания"),
    (dict(min_grade="4", has_failed_subjects=True, last_position=POS_CMDR1), 1,
     "Не допущен, отсутствовал или оценка 2"),
]


@pytest.mark.parametrize("kwargs,size,reason_part", PREMIA_CASES)
def test_compute_premia_sizes(kwargs, size, reason_part):
    got_size, got_reason, _ = _premia(**kwargs)
    assert got_size == size
    assert reason_part in got_reason


@pytest.mark.parametrize("kwargs,size,reason_part", PREMIA_CASES)
def test_compute_premia_session_result(kwargs, size, reason_part):
    """Результат сессии для колонки таблицы: 'неудовлетворительно' при
    провале предмета, иначе — по минимальной оценке."""
    _, _, session_result = _premia(**kwargs)
    if kwargs.get("has_failed_subjects"):
        assert session_result == "неудовлетворительно"
    elif not kwargs.get("has_session_results", True) or \
            kwargs.get("min_grade") is None:
        assert session_result == "нет данных"
    else:
        assert session_result in (
            "неудовлетворительно", "удовлетворительно", "хорошо", "отлично")


def test_position_genitive_mapping():
    from pages import premia_calc
    assert premia_calc.format_position_genitive(
        "Заместитель командира взвода") == "заместителя командира взвода"
    assert premia_calc.format_position_genitive("Курсант") is None
