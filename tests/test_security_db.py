"""Регрессионные тесты безопасности из BACKLOG: B-2 и B-1.

B-2 (перебор паролей и политика длины):
  * серия неудачных входов блокирует учётку (AccountLockedError);
  * успешный вход сбрасывает счётчик;
  * короткий пароль отвергается на записи (PasswordPolicyError).

B-1 (серверная проверка прав при мутациях):
  * мутаторы учётных записей с actor_role «Пользователь» падают с
    PermissionDeniedError и НЕ изменяют данные;
  * администратор проходит; переходный режим ALLOW_UNSCOPED разрешает
    вызовы без роли (легаси), ужесточение — отдельным тестом.
"""

import pytest

# ---------- B-2: политика паролей ----------

def test_password_policy_rejects_short(db):
    with pytest.raises(db.PasswordPolicyError):
        db.add_user("shorty", "abc")           # < MIN_PASSWORD_LENGTH
    with pytest.raises(db.PasswordPolicyError):
        db.add_user("ok1", "x" * 3)            # тоже короткий
    with pytest.raises(db.PasswordPolicyError):
        db.add_user("ok2", "")                 # пустой — не для 'admin'


def test_password_policy_allows_long(db):
    db.add_user("good", "s3cret-pass", "Пользователь")  # >= 8 символов
    assert db.check_user("good", "s3cret-pass") is not None


def test_update_password_enforces_policy(db):
    db.add_user("petrov2", "firstpassword", "Пользователь")
    uid = db.execute_query(
        "SELECT id FROM users WHERE username='petrov2'", fetch=True)[0]["id"]
    with pytest.raises(db.PasswordPolicyError):
        db.update_user_password(uid, "tiny")
    # старый пароль после отказа должен работать
    assert db.check_user("petrov2", "firstpassword") is not None


# ---------- B-2: блокировка при переборе ----------

def test_lockout_after_failed_attempts(db):
    db.add_user("victim", "correct-horse", "Пользователь")
    for _ in range(db.MAX_FAILED_ATTEMPTS - 1):
        assert db.check_user("victim", "wrong-pwd") is None
    # последняя попытка из лимита: не None, а блокировка
    with pytest.raises(db.AccountLockedError):
        db.check_user("victim", "wrong-pwd")
    # даже верный пароль теперь не пускает, пока блокировка активна
    with pytest.raises(db.AccountLockedError):
        db.check_user("victim", "correct-horse")


def test_successful_login_resets_counter(db):
    db.add_user("resilient", "correct-horse", "Пользователь")
    for _ in range(db.MAX_FAILED_ATTEMPTS - 1):
        db.check_user("resilient", "wrong-pwd")
    assert db.check_user("resilient", "correct-horse") is not None
    row = db.execute_query(
        "SELECT failed_attempts, locked_until FROM users WHERE username='resilient'",
        fetch=True)[0]
    assert row["failed_attempts"] == 0 and row["locked_until"] is None
    # счётчик начинается заново: снова MAX-1 ошибок без блокировки
    for _ in range(db.MAX_FAILED_ATTEMPTS - 1):
        assert db.check_user("resilient", "wrong-pwd") is None


def test_unknown_user_does_not_raise(db):
    assert db.check_user("nobody", "whatever123") is None


# ---------- B-1: серверная проверка прав ----------

def _user_id(db, username):
    return db.execute_query("SELECT id FROM users WHERE username=?",
                            (username,), fetch=True)[0]["id"]


@pytest.mark.parametrize("actor_role", ["Пользователь", "Гость"])
def test_mutations_denied_for_non_admin(db, actor_role):
    from access import PermissionDeniedError
    from constants import ADMIN_ROLE, DEFAULT_ROLE
    db.add_user("boss", "adminpass123", ADMIN_ROLE)
    db.add_user("regular", "userpass123", DEFAULT_ROLE)
    uid = _user_id(db, "regular")

    with pytest.raises(PermissionDeniedError):
        db.delete_user(uid, actor_role=actor_role)
    with pytest.raises(PermissionDeniedError):
        db.update_user_role(uid, ADMIN_ROLE, actor_role=actor_role)
    with pytest.raises(PermissionDeniedError):
        db.update_user_password(uid, "newpassword9", actor_role=actor_role)
    with pytest.raises(PermissionDeniedError):
        db.add_user("third", "thirdpass123", DEFAULT_ROLE, actor_role=actor_role)

    # данные не изменились
    assert _user_id(db, "regular") == uid
    role = db.execute_query("SELECT role FROM users WHERE id=?",
                            (uid,), fetch=True)[0]["role"]
    assert role == DEFAULT_ROLE
    assert db.check_user("regular", "userpass123") is not None


def test_mutations_allowed_for_admin(db):
    from constants import ADMIN_ROLE, DEFAULT_ROLE
    db.add_user("boss2", "adminpass123", ADMIN_ROLE)
    db.add_user("target", "targetpass123", DEFAULT_ROLE,
                actor_role=ADMIN_ROLE)
    uid = _user_id(db, "target")
    db.update_user_role(uid, ADMIN_ROLE, actor_role=ADMIN_ROLE)
    db.update_user_password(uid, "changedpass456", actor_role=ADMIN_ROLE)
    assert db.check_user("target", "changedpass456")[0][2] == ADMIN_ROLE
    db.delete_user(uid, actor_role=ADMIN_ROLE)
    assert db.check_user("target", "changedpass456") is None


def test_role_whitelist_on_update(db):
    from access import PermissionDeniedError  # noqa: F401  (импорт-страховка)
    from constants import ADMIN_ROLE
    db.add_user("boss3", "adminpass123", ADMIN_ROLE)
    uid = _user_id(db, "boss3")
    with pytest.raises(ValueError):
        db.update_user_role(uid, "Суперпользователь", actor_role=ADMIN_ROLE)


def test_unscoped_mode_flag(db):
    """ALLOW_UNSCOPED=True разрешает легаси-вызовы без роли (переходный
    период B-1); при False те же вызовы должны падать."""
    import access
    if not access.ALLOW_UNSCOPED:
        pytest.skip("режим совместимости уже отключён")
    db.add_user("legacy_call", "pwd123456")  # без actor_role — разрешено
    access.ALLOW_UNSCOPED = False
    try:
        with pytest.raises(access.PermissionDeniedError):
            db.add_user("blocked_call", "pwd123456")
    finally:
        access.ALLOW_UNSCOPED = True
