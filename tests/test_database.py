"""Интеграционные тесты слоя БД: пользователи, RBAC-данные, Дорожная карта.

Проверяют поведение, за которым стоят находки аудита:
  * check_user возвращает роль «Администратор» (именно то значение, с которым
    работает authz.is_admin — раньше home_page сверял с "admin" и ломался);
  * прозрачная миграция открытых паролей в хеши;
  * roadmap_reviews.created_at существует после init_db (баг колокольчика:
    запрос уведомлений падал в except из-за отсутствующей колонки);
  * add_review проставляет created_at;
  * delete_review реально удаляет строку (раньше «удаление» через
    update_review(status='deleted') лишь скрывало запись — тихая порча данных).
"""



# ---------- Пользователи ----------

def test_add_user_stores_hash_not_plaintext(db):
    # Пароль >= MIN_PASSWORD_LENGTH — политика B-2
    db.add_user("ivanov", "S3cret!passw0rd", db.DEFAULT_ROLE, actor_role=db.ADMIN_ROLE)
    row = db.execute_query(
        "SELECT password FROM users WHERE username = ?", ("ivanov",), fetch=True)[0]
    assert not str(row["password"]).startswith("S3cret")
    assert row["password"].startswith("pbkdf2_sha256$")


def test_check_user_returns_role(db):
    from constants import ADMIN_ROLE, DEFAULT_ROLE
    # Пароли >= MIN_PASSWORD_LENGTH — политика B-2
    db.add_user("admin1", "strongpwd1", ADMIN_ROLE, actor_role=db.ADMIN_ROLE)
    db.add_user("user1", "strongpwd1", DEFAULT_ROLE, actor_role=db.ADMIN_ROLE)

    assert db.check_user("admin1", "strongpwd1")[0][2] == ADMIN_ROLE
    assert db.check_user("user1", "strongpwd1")[0][2] == DEFAULT_ROLE
    assert db.check_user("user1", "wrongpassword") is None
    assert db.check_user("ghost", "strongpwd1") is None


def test_legacy_plaintext_password_migrates_on_login(db):
    """Открытый пароль пускает владельца и перезаписывается хешем."""
    db.execute_query("INSERT INTO users (username, password, role) VALUES (?,?,?)",
                     ("old_user", "legacy_pass", "Пользователь"))
    result = db.check_user("old_user", "legacy_pass")
    assert result is not None
    stored = db.execute_query(
        "SELECT password FROM users WHERE username = 'old_user'", fetch=True)[0]["password"]
    assert stored.startswith("pbkdf2_sha256$")
    # после миграции вход всё ещё работает
    assert db.check_user("old_user", "legacy_pass") is not None


def test_update_user_password_rehashes(db):
    db.add_user("petrov", "oldpassword1", "Пользователь", actor_role=db.ADMIN_ROLE)
    uid = db.execute_query("SELECT id FROM users WHERE username='petrov'",
                           fetch=True)[0]["id"]
    db.update_user_password(uid, "newpassword2", actor_role=db.ADMIN_ROLE)
    assert db.check_user("petrov", "oldpassword1") is None
    assert db.check_user("petrov", "newpassword2") is not None


# ---------- Схема MKR / created_at ----------

def test_roadmap_reviews_has_created_at(db):
    """Колонка добавляется идемпотентной миграцией ensure_column."""
    assert "created_at" in db.table_columns("roadmap_reviews")


def test_init_db_is_idempotent(db):
    db.init_db()   # второй вызов не должен падать
    db.init_db()


def test_get_recent_pending_reviews_works(db):
    """Запрос колокольчика не падает и находит pending-заявку по created_at."""
    sid = _add_student(db)
    _seed_achievement(db)
    db.add_review(sid, "ach_test_1", semester=1, actor_role=db.ADMIN_ROLE)
    rows = db.get_recent_pending_reviews(limit=5)
    ids = [r["student_id"] if hasattr(r, "keys") else r[1] for r in rows]
    assert sid in ids


# ---------- Заявки Road Map ----------

def _add_student(db):
    db.execute_query(
        "INSERT INTO students (o_surname, o_name, o_lastname, o_course, o_group_name)"
        " VALUES ('Иванов','Иван','Иванович',3,'А-12')")
    return db.execute_query("SELECT MAX(id) m FROM students", fetch=True)[0]["m"]


def _seed_achievement(db):
    db.execute_query(
        "INSERT OR IGNORE INTO achievements_catalog (id, block, name, points, calc_type)"
        " VALUES ('ach_test_1', 1, 'Тестовое достижение', 10, 'ms')")


def test_add_review_sets_created_at(db):
    sid = _add_student(db)
    _seed_achievement(db)
    db.add_review(sid, "ach_test_1", semester=1, actor_role=db.ADMIN_ROLE)
    row = db.execute_query(
        "SELECT created_at, status FROM roadmap_reviews WHERE student_id = ?",
        (sid,), fetch=True)[0]
    assert row["created_at"]           # не NULL — исправление бага аудита
    assert row["status"] == "pending"


def test_delete_review_removes_row(db):
    sid = _add_student(db)
    _seed_achievement(db)
    db.add_review(sid, "ach_test_1", semester=1, actor_role=db.ADMIN_ROLE)
    rid = db.execute_query("SELECT id FROM roadmap_reviews LIMIT 1", fetch=True)[0]["id"]
    db.delete_review(rid, actor_role=db.ADMIN_ROLE)
    left = db.execute_query("SELECT COUNT(*) c FROM roadmap_reviews", fetch=True)[0]["c"]
    assert left == 0


def test_update_review_approves_with_points(db):
    sid = _add_student(db)
    _seed_achievement(db)
    db.add_review(sid, "ach_test_1", semester=1, actor_role=db.ADMIN_ROLE)
    rid = db.execute_query("SELECT id FROM roadmap_reviews LIMIT 1", fetch=True)[0]["id"]
    db.update_review(rid, "approved", final_points=12, actor_role=db.ADMIN_ROLE)
    row = db.execute_query("SELECT status, final_points FROM roadmap_reviews WHERE id=?",
                           (rid,), fetch=True)[0]
    assert row["status"] == "approved"
    assert row["final_points"] == 12


def test_log_action_and_get_logs(db):
    db.log_action("tester", "тестовое действие")
    logs = db.get_logs()
    assert any("тестовое действие" in str(l["action"] if hasattr(l, "keys") else l[2])
               for l in logs)


# ---------- F-3: уведомления о сроках (семестровые статусы, баллы) ----------

def test_students_missing_semester_status(db):
    """Курсант без статуса попадает в список; закрытый семестр — исчезает."""
    sid1 = _add_student(db)
    sid2 = db.execute_query(
        "INSERT INTO students (o_surname, o_name, o_lastname, o_course,"
        " o_group_name) VALUES ('Петров','Пётр','Петрович',3,'А-12')"
        " RETURNING id", fetch=True)[0]["id"]

    rows = db.students_missing_semester_status(semester=1)
    ids = {r["student_id"] for r in rows}
    assert sid1 in ids and sid2 in ids
    assert db.count_students_missing_semester_status(semester=1) == 2

    db.set_semester_status(sid1, 1, is_candidate=True, actor_role=db.ADMIN_ROLE)
    rows = db.students_missing_semester_status(semester=1)
    ids = {r["student_id"] for r in rows}
    assert sid1 not in ids and sid2 in ids
    assert db.count_students_missing_semester_status(semester=1) == 1


def test_count_unresolved_reviews_scoped_by_semester(db):
    """Счётчик неподтверждённых баллов учитывает только указанный семестр."""
    sid = _add_student(db)
    _seed_achievement(db)
    db.add_review(sid, "ach_test_1", semester=2, actor_role=db.ADMIN_ROLE)
    assert db.count_unresolved_reviews(semester=2) == 1
    assert db.count_unresolved_reviews(semester=1) == 0
    # без ограничения — все pending
    assert db.count_unresolved_reviews() == 1


def test_notifications_functions_survive_empty_db(db):
    """На пустой базе функции уведомлений возвращают нули/пусто, не падая."""
    db.execute_query("DELETE FROM students")
    assert db.students_missing_semester_status() == []
    assert db.count_students_missing_semester_status() == 0
    assert db.count_unresolved_reviews() == 0
