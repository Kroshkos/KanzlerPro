"""T-1 из BACKLOG: сквозные сценарии навигации и RBAC (unit-подобные).

Инструмент — интеграционные тесты слоя доступа без рендера GUI (как
tests/test_authz.py, но сквозные «сценарии пользователя»):

  1. Вход студентом/обычным пользователем → страницы админа закрыты
     (require_admin возвращает заглушку, ADMIN_ONLY_PAGES не открывается);
  2. Вход администратором → те же страницы доступны;
  3. Начисление баллов возможно только через экспертизу заявки:
     прямой вызов update_review ролью «Пользователь» отбит на сервере
     (PermissionDeniedError) И данные останутся нетронутыми; полный
     цикл pending → approved ролью «Администратор» даёт финальные баллы;
  4. Мутации учётных записей, справочника достижений и личного дела
     запрещены анониму (сессия не проброшена) при ALLOW_UNSCOPED=False;
  5. Журнал действий: недоступен обычному пользователю в UI, а запись
     в него ведётся с проверкой хеш-цепочки (B-5).
"""

import types

import access
import authz
import pytest
from constants import ADMIN_ROLE, DEFAULT_ROLE


# ---------- стабы окружения Flet (без рендера) ----------

class _FakeStore:
    def __init__(self, data=None):
        self._data = dict(data or {})

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value

    def clear(self):
        self._data.clear()


def _logged_page(role):
    """Стаб ft.Page сразу после успешного входа login_page."""
    return types.SimpleNamespace(session=_FakeStore({"role": role,
                                                     "username": "tester"}))


def _anonymous_page():
    return types.SimpleNamespace(session=_FakeStore())


# ---------- сценарий 1–2: навигация по ролям ----------

@pytest.mark.parametrize("page_name", sorted(authz.ADMIN_ONLY_PAGES))
class TestAdminOnlyNavigation:

    def test_user_blocked(self, page_name):
        denied = authz.require_admin(_logged_page(DEFAULT_ROLE),
                                     message=f"Нет доступа: {page_name}")
        assert denied is not None, f"{page_name} должна быть закрыта для роли «{DEFAULT_ROLE}»"

    def test_anonymous_blocked(self, page_name):
        assert authz.require_admin(_anonymous_page()) is not None

    def test_admin_allowed(self, page_name):
        assert authz.require_admin(_logged_page(ADMIN_ROLE)) is None


def test_login_as_student_then_navigation(db):
    """Вход существующим пользователем → роль в сессии → карта прав."""
    db.add_user("student_one", "study-pass-1", DEFAULT_ROLE, actor_role=ADMIN_ROLE)
    result = db.check_user("student_one", "study-pass-1")
    assert result is not None
    _uid, _username, role = result[0]
    page = _logged_page(role)                       # так заполняет сессию login_page
    assert authz.is_admin(page) is False
    for name in ("UsersPage", "LogsPage", "RoadmapExpertPage"):
        assert name in authz.ADMIN_ONLY_PAGES
        assert authz.require_admin(page) is not None


def test_login_as_admin_then_navigation(db, monkeypatch):
    """Вход администратором (KANZLER_ADMIN_PASSWORD) → все страницы открыты."""
    monkeypatch.setenv("KANZLER_ADMIN_PASSWORD", "admin-e2e-pass")
    # admin создаётся только при первой инициализации БД — удаляем
    # сгенерированную фикстурой учётку и инициализируем заново.
    db.execute_query("DELETE FROM users WHERE username = 'admin'")
    db.init_db()
    result = db.check_user("admin", "admin-e2e-pass")
    assert result is not None, "вход администратора должен быть успешен"
    _, _, role = result[0]
    assert role == ADMIN_ROLE
    page = _logged_page(role)
    assert authz.is_admin(page) is True
    assert authz.require_admin(page) is None


# ---------- сценарий 3: баллы — только через экспертизу ----------

@pytest.fixture()
def ipr_env(db):
    """Курсант + достижение + неподтверждённая заявка (pending).

    add_review ничего не возвращает (историческое поведение слоя БД),
    поэтому id заявки читается прямым SELECT по student_id.
    """
    student_id = db.add_student({"o_surname": "Тестов", "o_name": "Тест",
                                 "o_lastname": "Тестович", "o_group_name": "1-1",
                                 "o_course": "1"}, actor_role=ADMIN_ROLE)
    db.add_achievement("900", 1, "Тестовое достижение", 100,
                       actor_role=ADMIN_ROLE)
    db.add_review(student_id, "900", semester=1, actor_role=ADMIN_ROLE)
    row = db.execute_query(
        "SELECT id FROM roadmap_reviews WHERE student_id = ?",
        (student_id,), fetch=True)[0]
    return db, student_id, row["id"]


def test_direct_point_grant_by_user_role_is_denied_and_data_intact(ipr_env):
    db, _, review_id = ipr_env
    with pytest.raises(access.PermissionDeniedError):
        db.update_review(review_id, "approved", final_points=999,
                         actor_role=DEFAULT_ROLE)
    row = db.execute_query(
        "SELECT status, final_points FROM roadmap_reviews WHERE id = ?",
        (review_id,), fetch=True)[0]
    assert row["status"] == "pending", "отказ не должен менять статус заявки"
    assert row["final_points"] is None, "начисление баллов мимо экспертизы невозможно"


def test_full_cycle_pending_to_approved_by_admin(ipr_env):
    db, student_id, review_id = ipr_env
    # формула из слоя БД: база * коэффициенты (тип 'ms' — без месяцев)
    final = db.calculate_final_points("ms", 100, k_ur=1.0, k_role=1.0,
                                      k_vn=1.0, k_st=1.0)
    db.update_review(review_id, "approved", comment="Зачтено",
                     final_points=final, actor_role=ADMIN_ROLE)
    rows = db.get_reviews(student_id=student_id, status="approved")
    assert len(rows) == 1
    assert int(rows[0]["final_points"]) == final


def test_anonymous_cannot_touch_reviews_or_students(ipr_env):
    db, _, review_id = ipr_env
    assert access.ALLOW_UNSCOPED is False, "строгий режим B-1 должен быть включён"
    with pytest.raises(access.PermissionDeniedError):
        db.update_review(review_id, "approved", final_points=500)  # без роли
    with pytest.raises(access.PermissionDeniedError):
        db.add_student({"o_surname": "Никто"})                     # без роли
    with pytest.raises(access.PermissionDeniedError):
        db.delete_review(review_id)                                # без роли
    # данные не изменились
    row = db.execute_query(
        "SELECT status FROM roadmap_reviews WHERE id = ?",
        (review_id,), fetch=True)[0]
    assert row["status"] == "pending"


# ---------- сценарий 4: мутации учеток и справочников ----------

def test_user_role_cannot_manage_accounts(db):
    with pytest.raises(access.PermissionDeniedError):
        db.add_user("hacker", "password123", actor_role=DEFAULT_ROLE)
    with pytest.raises(access.PermissionDeniedError):
        db.delete_user(1, actor_role=DEFAULT_ROLE)
    rows = db.execute_query("SELECT COUNT(*) c FROM users", fetch=True)[0]
    assert rows["c"] == 1, "в БД остался только admin — отказ ничего не записал"


def test_user_role_cannot_edit_achievements_catalog(db):
    with pytest.raises(access.PermissionDeniedError):
        db.add_achievement("901", 1, "Накрутка", 1000, actor_role=DEFAULT_ROLE)
    assert db.count_achievements() == 0


# ---------- сценарий 5: журнал действий доступен только админу ----------

def test_logs_ui_hidden_for_user_visible_for_admin(db):
    db.log_action("tester", "тестовое действие")
    assert authz.require_admin(_logged_page(DEFAULT_ROLE)) is not None
    assert authz.require_admin(_logged_page(ADMIN_ROLE)) is None
    # сам слой данных пишет корректно и цепочка цела (B-5)
    problems = db.verify_logs_chain()
    assert not problems, f"hash-цепочка журнала повреждена: {problems}"
