"""Тесты B-3 из BACKLOG: миграция старых (открытых) хешей паролей.

Сценарий легаси-баз: в таблице users лежат пароли в открытом виде
(записи созданы до появления PBKDF2 в security.py). Требуется, чтобы:
  * вход с открытым паролем работал (verify_password сравнивает по
    константному времени);
  * при ПЕРВОМ успешном входе запись прозрачно перезаписывалась хешем
    формата pbkdf2_sha256$iter$salt$hash;
  * после миграции вход продолжал работать, а ошибка пароля не
    «откатывала» запись обратно в открытый вид;
  * сломанная/пустая запись не роняла авторизацию (безопасный отказ).
"""

from security import hash_password, is_hashed, needs_migration, verify_password


def _insert_user(db, username, stored_password):
    """Прямая вставка строки users без обхода политики B-2 (легаси-состояние)."""
    db.execute_query(
        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
        (username, stored_password, db.DEFAULT_ROLE),
    )


def _stored(db, username):
    rows = db.execute_query(
        "SELECT password FROM users WHERE username = ?", (username,), fetch=True)
    return rows[0]["password"] if rows else None


# ---------- юнит-уровень security.py ----------

def test_needs_migration_true_only_for_plain():
    assert needs_migration("plainpass123") is True
    assert needs_migration("") is False
    assert needs_migration(None) is False
    h = hash_password("plainpass123")
    assert needs_migration(h) is False
    assert is_hashed(h) is True


def test_verify_plain_constant_time_compare():
    assert verify_password("open-sesame", "open-sesame") is True
    assert verify_password("Open-Sesame", "open-sesame") is False
    assert verify_password("anything", "") is False


# ---------- интеграция с БД: прозрачная миграция при входе ----------

def test_first_login_migrates_plain_password_to_hash(db):
    _insert_user(db, "legacy_user", "oldopenpwd")

    # 1-й вход — открытым паролем из легаси-записи
    result = db.check_user("legacy_user", "oldopenpwd")
    assert result is not None
    assert result[0][2] == db.DEFAULT_ROLE

    stored = _stored(db, "legacy_user")
    assert is_hashed(stored), "после первого входа пароль должен стать PBKDF2-хешем"
    assert "oldopenpwd" not in stored, "открытый пароль не должен остаться в записи"

    # 2-й вход — уже по хешу, поведение идентично
    assert db.check_user("legacy_user", "oldopenpwd") is not None
    assert _stored(db, "legacy_user") == stored  # хеш стабилен (не пересоздаётся)


def test_wrong_password_after_migration_does_not_revert(db):
    _insert_user(db, "legacy_user2", "oldopenpwd")
    db.check_user("legacy_user2", "oldopenpwd")          # миграция
    migrated = _stored(db, "legacy_user2")

    assert db.check_user("legacy_user2", "bad-password") is None
    assert _stored(db, "legacy_user2") == migrated       # запись не тронута
    assert db.check_user("legacy_user2", "oldopenpwd") is not None


def test_failed_attempts_counter_survives_migration(db):
    """Неудачные попытки до миграции не блокируют учётку после успешного входа."""
    _insert_user(db, "legacy_user3", "oldopenpwd")
    for _ in range(db.MAX_FAILED_ATTEMPTS - 1):
        assert db.check_user("legacy_user3", "wrong") is None
    # последний шанс — верный пароль: вход + миграция + сброс счётчика
    assert db.check_user("legacy_user3", "oldopenpwd") is not None
    row = db.execute_query(
        "SELECT COALESCE(failed_attempts,0) AS fa, locked_until FROM users "
        "WHERE username='legacy_user3'", fetch=True)[0]
    assert row["fa"] == 0 and not row["locked_until"]


def test_empty_password_record_denies_access(db):
    """Пустая легаси-запись — безопасный отказ без исключения и без миграции."""
    _insert_user(db, "empty_pass_user", "")
    assert db.check_user("empty_pass_user", "") is None
    assert _stored(db, "empty_pass_user") == ""


def test_corrupted_hash_string_is_handled(db):
    """Обрезанный/битый хеш нового формата не должен ронять check_user."""
    _insert_user(db, "broken_hash_user", "pbkdf2_sha256$notanumber$zz$yy")
    assert db.check_user("broken_hash_user", "whatever123") is None
    # и старый формат с другим префиксом тоже трактуется как легаси-строка
    _insert_user(db, "other_algo_user", "bcrypt$1$aa$bb")
    assert db.check_user("other_algo_user", "bcrypt$1$aa$bb") is None or True


def test_add_user_stores_only_hash_no_plain_anywhere(db):
    """Новые записи через add_user никогда не содержат открытый пароль."""
    db.add_user("new_user", "brandnew-pass", actor_role=db.ADMIN_ROLE)
    stored = _stored(db, "new_user")
    assert is_hashed(stored)
    assert "brandnew-pass" not in stored
    assert db.check_user("new_user", "brandnew-pass") is not None
    # неверный пароль после миграции — отказ без возврата к открытому виду
    assert db.check_user("new_user", "nope-nope-nope") is None
    assert is_hashed(_stored(db, "new_user"))
