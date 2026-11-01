import os
import re
import sqlite3
from datetime import datetime

# Абсолютный путь к файлу базы данных (не зависит от текущей директории,
# из которой запущено приложение — раньше БД «терялась» при запуске из другой папки)
from config import DB_PATH  # единая база приложения kanzler_pro.db
from constants import ADMIN_ROLE, DEFAULT_ROLE
from security import hash_password, needs_migration, verify_password

# Имя таблицы только из разрешённых символов — защита от SQL-инъекций
# в служебных запросах PRAGMA (имя колонки подставить параметром нельзя).
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def table_columns(table):
    """Возвращает множество имён колонок таблицы (для лёгких миграций)."""
    if not _IDENTIFIER_RE.match(table):
        raise ValueError(f"Некорректное имя таблицы: {table!r}")
    conn = connect_to_db()
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def ensure_column(table, column, decl="TEXT"):
    """Добавляет колонку в таблицу, если её ещё нет (идемпотентно).

    Используется миграциями схемы: старые файлы kanzler.db создавались без
    части полей личного дела, и без этого шага сохранение курсанта падало бы
    с «no such column». SQLite не поддерживает IF NOT EXISTS для ADD COLUMN,
    поэтому проверка выполняется через PRAGMA table_info.
    """
    if not (_IDENTIFIER_RE.match(table) and _IDENTIFIER_RE.match(column)):
        raise ValueError(f"Некорректные идентификаторы: {table!r}.{column!r}")
    if column not in table_columns(table):
        execute_query(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        return True  # колонка была добавлена
    return False


# Подключение к базе данных SQLite
def connect_to_db():
    conn = sqlite3.connect(DB_PATH)  # Файл базы данных
    conn.execute("PRAGMA foreign_keys = ON")  # включаем контроль внешних ключей
    return conn

# Функция для выполнения SQL-запросов
def execute_query(query, params=None, fetch=False):
    conn = connect_to_db()
    # sqlite3.Row поддерживает и доступ по индексу (row[0]), и по имени
    # колонки (row["o_surname"]) — обратная совместимость сохранена.
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(query, params or ())
    if fetch:
        result = cursor.fetchall()
    else:
        conn.commit()
        result = None
    cursor.close()
    conn.close()
    return result

# Инициализация базы данных (создание таблиц)
def init_db():
    # Создание таблицы students
    query_students = """
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        o_surname TEXT NOT NULL,
        o_name TEXT NOT NULL,
        o_lastname TEXT NOT NULL,
        o_course INTEGER NOT NULL,
        o_group_name TEXT NOT NULL,
        o_gender TEXT,
        o_age INTEGER,
        o_date_of_birth TEXT,
        o_place_of_birth TEXT, 
        o_citizenship TEXT,
        o_nationality TEXT,
        o_religion TEXT,
        o_marital_status TEXT,
        o_occupation_before_military_service TEXT,
        o_bad_habits TEXT,
        o_health_status TEXT,
        o_sports_categories TEXT,
        o_interests TEXT,
        o_skills TEXT,
        o_sociometric_indicators TEXT,
        kontact_residential_address TEXT,
        kontact_number TEXT,
        kontact_email TEXT,
        o_photo TEXT,
        ld_passport_series INTEGER,
        ld_passport_number INTEGER,
        ld_passport_date_given TEXT,
        ld_passport_unit_code_given TEXT,
        ld_passport_place_given TEXT,
        ld_passport_children TEXT,
        ld_vb_personal_number TEXT,
        ld_vb_series TEXT,
        ld_vb_number INTEGER,
        ld_vb_date_given TEXT,
        ld_vb_place_given TEXT,
        ld_vb_vs_date_of_conscription TEXT,
        ld_vb_vs_called_upon TEXT,
        ld_vb_post_post TEXT,
        ld_vb_post_assigned TEXT,
        ld_vb_post_date_assigned TEXT,
        ld_vb_post_number_order TEXT,
        ld_vb_rank_rank TEXT,
        ld_vb_rank_assigned TEXT,
        ld_vb_rank_date_assigned TEXT,
        ld_vb_rank_number_order TEXT,
        ld_vb_fingerprinting_date TEXT,
        ld_vb_fingerprinting_place TEXT,
        ld_vb_contract_number INTEGER,
        ld_vb_contract_term TEXT,
        ld_vb_contract_date TEXT,
        ld_vb_contract_number_order TEXT,
        ld_vb_period_of_service TEXT,
        ld_inn TEXT,
        ld_snils TEXT,
        ld_oms TEXT,
        ld_education_tip TEXT,
        ld_education_level TEXT,
        ld_education_series TEXT,
        ld_education_number INTEGER,
        ld_education_date_given TEXT,
        ld_education_name_given TEXT,
        ld_education_city TEXT,
        ld_education_qualification TEXT,
        ld_education_specialization TEXT,
        ld_education_form TEXT,
        ld_drl_series TEXT,
        ld_drl_number INTEGER,
        ld_drl_date_given TEXT,
        ld_drl_date_end TEXT,
        ld_drl_unit_code_given TEXT,
        ld_drl_category TEXT,
        ld_ccv_series TEXT,
        ld_ccv_number INTEGER,
        ld_ccv_date_given TEXT,
        ld_pvk_date_counted TEXT,
        ld_pvk_address TEXT,
        ld_pvk_type_property TEXT,
        ld_pvk_additional_number TEXT,
        ld_pvk_messenger_main TEXT,
        ld_pvk_messenger_additional TEXT,
        if_social_origin TEXT,
        if_family_composition TEXT,
        if_number_of_children INTEGER,
        if_dysfunctional_relatives TEXT,
        da_score_chemistry INTEGER,
        da_score_biology INTEGER,
        da_score_rusian INTEGER,
        da_score_fp INTEGER,
        da_summary_score INTEGER,
        da_group_number INTEGER,
        da_score_diploma TEXT,
        da_additional_education TEXT,
        rd_father_surname TEXT,
        rd_father_name TEXT,
        rd_father_lastname TEXT,
        rd_father_date_of_birth TEXT,
        rd_father_place_of_birth TEXT,
        rd_father_citizenship TEXT,
        rd_father_passport_series TEXT,
        rd_father_passport_number TEXT,
        rd_father_passport_date_given TEXT,
        rd_father_passport_place_given TEXT,
        rd_father_passport_unit_code_given TEXT,
        rd_father_number TEXT,
        rd_mother_surname TEXT,
        rd_mother_name TEXT,
        rd_mother_lastname TEXT,
        rd_mother_date_of_birth TEXT,
        rd_mother_place_of_birth TEXT,
        rd_mother_citizenship TEXT,
        rd_mother_passport_series TEXT,
        rd_mother_passport_number TEXT,
        rd_mother_passport_date_given TEXT,
        rd_mother_passport_place_given TEXT,
        rd_mother_passport_unit_code_given TEXT,
        rd_mother_number TEXT,
        rd_other_info TEXT
    );
    """
    execute_query(query_students)
    init_mkr_tables()  # таблицы Дорожной карты (MKR) в той же базе

    # Обновленная таблица users с полем role
    query_users = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'Пользователь'
    );
    """
    execute_query(query_users)

    # Новая таблица logs для журнала действий
    query_logs = """
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        username TEXT NOT NULL,
        action TEXT NOT NULL
    );
    """
    execute_query(query_logs)

   # Создание таблицы session_results
    query_session_results = """
    CREATE TABLE IF NOT EXISTS session_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_name TEXT NOT NULL,
        subject TEXT NOT NULL,
        type_exam TEXT NOT NULL,
        date TEXT NOT NULL,
        statement_number TEXT NOT NULL,
        statement_tip TEXT NOT NULL,
        student_id INTEGER NOT NULL,
        allowance TEXT NOT NULL,
        attendance TEXT NOT NULL,
        grade TEXT NOT NULL,
        semester TEXT NOT NULL,  -- Добавляем поле для семестра
        FOREIGN KEY (student_id) REFERENCES students (id)
    );
    """
    execute_query(query_session_results)

    # Создание таблицы encouragements (поощерения)
    query_encouragements = """
    CREATE TABLE IF NOT EXISTS encouragements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        encouragement_type TEXT NOT NULL,
        reason TEXT NOT NULL,
        issued_by TEXT NOT NULL,
        date TEXT NOT NULL,
        order_number TEXT NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students (id)
    );
    """
    execute_query(query_encouragements)

    # Создание таблицы penalties (взыскания)
    query_penalties = """
    CREATE TABLE IF NOT EXISTS penalties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        penalty_type TEXT NOT NULL,
        reason TEXT NOT NULL,
        date_reason TEXT NOT NULL,
        issued_by TEXT NOT NULL,
        date TEXT NOT NULL,
        order_number TEXT NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students (id)
    );
    """
    execute_query(query_penalties)

    # Создание таблицы position_history (история изменений должностей)
    query_position_history = """
    CREATE TABLE IF NOT EXISTS position_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        position TEXT NOT NULL,
        assigned_by TEXT NOT NULL,
        date TEXT NOT NULL,
        order_number TEXT NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students (id)
    );
    """
    execute_query(query_position_history)

    # Создание таблицы rank_history (история изменений должностей)
    query_rank_history = """
    CREATE TABLE IF NOT EXISTS rank_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        rank TEXT NOT NULL,
        assigned_by TEXT NOT NULL,
        date TEXT NOT NULL,
        order_number TEXT NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students (id)
    );
    """
    execute_query(query_rank_history)

    # Создание таблицы subjects (учебные предметы)
    query_subjects = """
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_name TEXT NOT NULL UNIQUE
    );
    """
    execute_query(query_subjects)

    # Миграция схемы: доводим старые файлы БД к актуальному списку полей.
    migrate_schema()

    # Добавление администратора по умолчанию (если его нет).
    # Пароль задаётся переменной окружения KANZLER_ADMIN_PASSWORD,
    # иначе генерируется случайный и выводится один раз при создании.
    test_user_query = "SELECT * FROM users WHERE username = 'admin'"
    if not execute_query(test_user_query, fetch=True):
        admin_password = os.environ.get("KANZLER_ADMIN_PASSWORD")
        if not admin_password:
            import secrets
            admin_password = secrets.token_urlsafe(12)
            print("[Канцлер] Создан пользователь 'admin'. "
                  f"Задайте свой пароль через меню 'Пользователи' или переменную "
                  f"KANZLER_ADMIN_PASSWORD. Временный пароль: {admin_password}")
        add_user("admin", admin_password, ADMIN_ROLE)

# Логирование действия
def log_action(username, action):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    query = "INSERT INTO logs (timestamp, username, action) VALUES (?, ?, ?)"
    execute_query(query, (timestamp, username, action))

# Проверка пользователя с возвратом роли
# Возвращает список кортежей (id, username, role) либо None, если пользователь не найден.
# Пароли хранятся в виде PBKDF2-хешей; устаревшие открытые пароли
# прозрачно мигрируются в хеши при первой успешной авторизации.
def check_user(username, password):
    rows = execute_query(
        "SELECT id, username, role, password FROM users WHERE username = ?",
        (username,), fetch=True)
    if not rows:
        return None
    user_id, db_username, role, stored_password = rows[0]
    if not verify_password(password, stored_password):
        return None
    if needs_migration(stored_password):
        execute_query("UPDATE users SET password = ? WHERE id = ?",
                      (hash_password(password), user_id))
    return [(user_id, db_username, role)]

# Добавление нового пользователя (пароль сохраняется только как хеш)
def add_user(username, password, role=DEFAULT_ROLE):
    query = "INSERT INTO users (username, password, role) VALUES (?, ?, ?)"
    execute_query(query, (username, hash_password(password), role))

# Смена пароля пользователя
def update_user_password(user_id, new_password):
    query = "UPDATE users SET password = ? WHERE id = ?"
    execute_query(query, (hash_password(new_password), user_id))

# Удаление пользователя
def delete_user(user_id):
    query = "DELETE FROM users WHERE id = ?"
    execute_query(query, (user_id,))

# Изменение роли пользователя
def update_user_role(user_id, new_role):
    query = "UPDATE users SET role = ? WHERE id = ?"
    execute_query(query, (new_role, user_id))

# Получение одного пользователя по id (без поля пароля)
def get_user_by_id(user_id):
    rows = execute_query(
        "SELECT id, username, role FROM users WHERE id = ?", (user_id,), fetch=True)
    return rows[0] if rows else None

# Получение списка пользователей
def get_users():
    query = "SELECT id, username, role FROM users"
    return execute_query(query, fetch=True)

# Получение записей журнала
def get_logs():
    query = "SELECT timestamp, username, action FROM logs ORDER BY timestamp DESC"
    return execute_query(query, fetch=True)

def search_students_by_multiple_params(surname=None, name=None, lastname=None, group_name=None, course=None, age=None, gender=None, birthday=None, birthplace=None, citizenship=None, nationality=None, religion=None, marital_status=None, residence=None, bad_habits=None, health_status=None, interests=None, skills=None):
    conn = connect_to_db()
    cursor = conn.cursor()
    
    # Базовый запрос
    query = "SELECT * FROM students WHERE 1=1"
    params = []
    
    # Добавляем условия в зависимости от переданных параметров
    if surname:
        query += " AND o_surname = ?"  # Точное совпадение по фамилии
        params.append(surname)
    if name:
        query += " AND o_name = ?"  # Точное совпадение по имени
        params.append(name)
    if lastname:
        query += " AND o_lastname = ?"  # Точное совпадение по отчеству
        params.append(lastname)
    if group_name:
        query += " AND o_group_name = ?"  # Точное совпадение по группе
        params.append(group_name)
    if course:
        query += " AND o_course = ?"  # Точное совпадение по курсу
        params.append(course)
    if age:
        query += " AND o_age = ?"  # Точное совпадение по возрасту
        params.append(age)
    if gender:
        query += " AND o_gender = ?"  # Точное совпадение по полу
        params.append(gender)
    if birthday:
        query += " AND o_date_of_birth = ?"  # Точное совпадение по дате рождения
        params.append(birthday)
    if birthplace:
        query += " AND o_place_of_birth = ?"  # Точное совпадение по месту рождения
        params.append(birthplace)
    if citizenship:
        query += " AND o_citizenship = ?"  # Точное совпадение по гражданству
        params.append(citizenship)
    if nationality:
        query += " AND o_nationality = ?"  # Точное совпадение по национальности
        params.append(nationality)
    if religion:
        query += " AND o_religion = ?"  # Точное совпадение по вероисповеданию
        params.append(religion)
    if marital_status:
        query += " AND o_marital_status = ?"  # Точное совпадение по семейному положению
        params.append(marital_status)
    if residence:
        query += " AND o_occupation_before_military_service = ?"  # Точное совпадение по месту жительства
        params.append(residence)
    if bad_habits:
        query += " AND o_bad_habits = ?"  # Точное совпадение по вредным привычкам
        params.append(bad_habits)
    if health_status:
        query += " AND o_health_status = ?"  # Точное совпадение по состоянию здоровья
        params.append(health_status)
    if interests:
        query += " AND o_interests = ?"  # Точное совпадение по интересам
        params.append(interests)
    if skills:
        query += " AND o_skills = ?"  # Точное совпадение по навыкам
        params.append(skills)
    
    cursor.execute(query, params)
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result

# Добавление студента
# Единственный источник истины об обновляемых полях личного дела курсанта.
# Порядок и состав строго соответствуют колонкам INSERT в add_student.
STUDENT_FIELDS = [
    "o_surname", "o_name", "o_lastname", "o_course", "o_group_name",
    "o_gender", "o_age", "o_date_of_birth", "o_place_of_birth",
    "o_citizenship", "o_nationality", "o_religion", "o_marital_status",
    "o_occupation_before_military_service", "o_bad_habits",
    "o_health_status", "o_sports_categories", "o_interests", "o_skills",
    "o_sociometric_indicators", "kontact_residential_address",
    "kontact_number", "kontact_email", "o_photo",
    "ld_passport_series", "ld_passport_number", "ld_passport_date_given",
    "ld_passport_unit_code_given", "ld_passport_place_given",
    "ld_passport_children", "ld_vb_personal_number", "ld_vb_series",
    "ld_vb_number", "ld_vb_date_given", "ld_vb_place_given",
    "ld_vb_vs_date_of_conscription", "ld_vb_vs_called_upon",
    "ld_vb_post_post", "ld_vb_post_assigned", "ld_vb_post_date_assigned",
    "ld_vb_post_number_order", "ld_vb_rank_rank", "ld_vb_rank_assigned",
    "ld_vb_rank_date_assigned", "ld_vb_rank_number_order",
    "ld_vb_fingerprinting_date", "ld_vb_fingerprinting_place",
    "ld_vb_contract_number", "ld_vb_contract_term", "ld_vb_contract_date",
    "ld_vb_contract_number_order", "ld_vb_period_of_service",
    "ld_inn", "ld_snils", "ld_oms",
    "ld_education_tip", "ld_education_level", "ld_education_series",
    "ld_education_number", "ld_education_date_given",
    "ld_education_name_given", "ld_education_city",
    "ld_education_qualification", "ld_education_specialization",
    "ld_education_form", "ld_drl_series", "ld_drl_number",
    "ld_drl_date_given", "ld_drl_date_end", "ld_drl_unit_code_given",
    "ld_drl_category", "ld_ccv_series", "ld_ccv_number",
    "ld_ccv_date_given", "ld_pvk_date_counted", "ld_pvk_address",
    "ld_pvk_type_property", "ld_pvk_additional_number",
    "ld_pvk_messenger_main", "ld_pvk_messenger_additional",
    "if_social_origin", "if_family_composition", "if_number_of_children",
    "if_dysfunctional_relatives", "da_score_chemistry",
    "da_score_biology", "da_score_rusian", "da_score_fp",
    "da_summary_score", "da_group_number", "da_score_diploma",
    "da_additional_education", "rd_father_surname", "rd_father_name",
    "rd_father_lastname", "rd_father_date_of_birth",
    "rd_father_place_of_birth", "rd_father_citizenship",
    "rd_father_passport_series", "rd_father_passport_number",
    "rd_father_passport_date_given", "rd_father_passport_place_given",
    "rd_father_passport_unit_code_given", "rd_father_number",
    "rd_mother_surname", "rd_mother_name", "rd_mother_lastname",
    "rd_mother_date_of_birth", "rd_mother_place_of_birth",
    "rd_mother_citizenship", "rd_mother_passport_series",
    "rd_mother_passport_number", "rd_mother_passport_date_given",
    "rd_mother_passport_place_given", "rd_mother_passport_unit_code_given",
    "rd_mother_number", "rd_other_info",
]


def migrate_schema():
    """Лёгкая миграция схемы: добавляет в старые БД недостающие колонки.

    Идемпотентна и безопасна для повторных запусков: ensure_column проверяет
    наличие колонки через PRAGMA table_info перед ALTER TABLE. Вызывается из
    init_db() после создания таблиц.
    """
    added = []
    for field in STUDENT_FIELDS:
        if ensure_column("students", field):
            added.append(field)
    if added:
        print(f"[Канцлер] Миграция схемы: добавлено колонок в students: {len(added)}")
    return added


def update_student(student_id, student_data):
    """Обновляет личное дело курсанта.

    Обновляются только те поля из STUDENT_FIELDS, которые присутствуют в
    student_data (частичное обновление). Имена колонок берутся из белого
    списка STUDENT_FIELDS — произвольные строки в SQL не попадают.
    Возвращает True, если запись найдена и обновлена.
    """
    fields = [f for f in STUDENT_FIELDS if f in student_data]
    if not fields:
        return False
    set_clause = ", ".join(f"{f} = ?" for f in fields)
    query = f"UPDATE students SET {set_clause} WHERE id = ?"
    params = tuple(student_data[f] for f in fields) + (student_id,)

    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def add_student(student_data):
    conn = connect_to_db()  # Открываем соединение с базой данных
    cursor = conn.cursor()  # Создаем курсор

    try:
        query = """
        INSERT INTO students (
            o_surname, 
            o_name, 
            o_lastname, 
            o_course, 
            o_group_name, 
            o_gender, 
            o_age, 
            o_date_of_birth,
            o_place_of_birth, 
            o_citizenship, 
            o_nationality, 
            o_religion, 
            o_marital_status,
            o_occupation_before_military_service, 
            o_bad_habits, 
            o_health_status, 
            o_sports_categories, 
            o_interests, 
            o_skills, 
            o_sociometric_indicators,
            kontact_residential_address,
            kontact_number, 
            kontact_email,
            o_photo,
            ld_passport_series, 
            ld_passport_number, 
            ld_passport_date_given,
            ld_passport_unit_code_given, 
            ld_passport_place_given, 
            ld_passport_children, 
            ld_vb_personal_number,
            ld_vb_series, 
            ld_vb_number, 
            ld_vb_date_given, 
            ld_vb_place_given,
            ld_vb_vs_date_of_conscription,
            ld_vb_vs_called_upon, 
            ld_vb_post_post, 
            ld_vb_post_assigned,
            ld_vb_post_date_assigned, 
            ld_vb_post_number_order, 
            ld_vb_rank_rank, 
            ld_vb_rank_assigned,
            ld_vb_rank_date_assigned, 
            ld_vb_rank_number_order, 
            ld_vb_fingerprinting_date, 
            ld_vb_fingerprinting_place,
            ld_vb_contract_number, 
            ld_vb_contract_term, 
            ld_vb_contract_date, 
            ld_vb_contract_number_order,
            ld_vb_period_of_service,
            ld_inn, 
            ld_snils, 
            ld_oms, 
            ld_education_tip, 
            ld_education_level,
            ld_education_series, 
            ld_education_number, 
            ld_education_date_given, 
            ld_education_name_given,
            ld_education_city, 
            ld_education_qualification, 
            ld_education_specialization, 
            ld_education_form,
            ld_drl_series, 
            ld_drl_number, 
            ld_drl_date_given, 
            ld_drl_date_end, 
            ld_drl_unit_code_given,
            ld_drl_category, 
            ld_ccv_series, 
            ld_ccv_number, 
            ld_ccv_date_given, 
            ld_pvk_date_counted, 
            ld_pvk_address,
            ld_pvk_type_property, 
            ld_pvk_additional_number, 
            ld_pvk_messenger_main, 
            ld_pvk_messenger_additional,
            if_social_origin, 
            if_family_composition, 
            if_number_of_children, 
            if_dysfunctional_relatives,
            da_score_chemistry, 
            da_score_biology, 
            da_score_rusian, 
            da_score_fp, 
            da_summary_score, 
            da_group_number,
            da_score_diploma, 
            da_additional_education, 
            rd_father_surname, 
            rd_father_name, 
            rd_father_lastname,
            rd_father_date_of_birth, 
            rd_father_place_of_birth, 
            rd_father_citizenship, 
            rd_father_passport_series,
            rd_father_passport_number, 
            rd_father_passport_date_given, 
            rd_father_passport_place_given,
            rd_father_passport_unit_code_given, 
            rd_father_number, 
            rd_mother_surname, 
            rd_mother_name,
            rd_mother_lastname, 
            rd_mother_date_of_birth, 
            rd_mother_place_of_birth, 
            rd_mother_citizenship,
            rd_mother_passport_series, 
            rd_mother_passport_number, 
            rd_mother_passport_date_given,
            rd_mother_passport_place_given, 
            rd_mother_passport_unit_code_given, 
            rd_mother_number, 
            rd_other_info
        ) VALUES (
            ?,
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?, 
            ?
        );
        """
        # Словарь параметров: берём только те ключи, что реально есть в словаре
        # вызывающей стороны (защита от KeyError при неполных данных),
        # порядок строго соответствует списку колонок запроса ниже.
        _data = {k: v for k, v in student_data.items()}
        _defaults = {"o_surname": "", "o_name": "", "o_lastname": "",
                     "o_course": 0, "o_group_name": ""}
        for k, v in _defaults.items():
            _data.setdefault(k, v)

        _ordered_keys = STUDENT_FIELDS
        assert len(_ordered_keys) == query.count("?"), (
            f"Несовпадение колонки/параметры: {len(_ordered_keys)} vs {query.count('?')}"
        )
        params = tuple(_data.get(k, "") for k in _ordered_keys)
        cursor.execute(query, params)
    
        student_id = cursor.lastrowid
        
        if student_data.get("ld_vb_post_post"):
            position_query = """
            INSERT INTO position_history (student_id, position, assigned_by, date, order_number)
            VALUES (?, ?, ?, ?, ?)
            """
            position_params = (
                student_id,
                student_data["ld_vb_post_post"],  # Должность
                student_data["ld_vb_post_assigned"],  # Кем назначен
                student_data["ld_vb_post_date_assigned"],  # Дата назначения
                student_data["ld_vb_post_number_order"]  # Номер приказа
            )
            cursor.execute(position_query, position_params)

        if student_data.get("ld_vb_rank_rank"):
            rank_query = """
            INSERT INTO rank_history (student_id, rank, assigned_by, date, order_number)
            VALUES (?, ?, ?, ?, ?)
            """
            rank_params = (
                student_id,
                student_data["ld_vb_rank_rank"],  # Звание
                student_data["ld_vb_rank_assigned"],  # Кем назначен
                student_data["ld_vb_rank_date_assigned"],  # Дата назначения
                student_data["ld_vb_rank_number_order"]  # Номер приказа
            )
            cursor.execute(rank_query, rank_params)
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    finally:
        cursor.close()
        conn.close()

    return student_id


# Примечание: ранее здесь находилось дублирующее определение check_user(),
# которое переопределяло корректную версию выше (см. строку ~272) и ломало
# авторизацию. Дубликат удалён.

def get_students():
    query = "SELECT id, o_surname, o_name, o_lastname, o_course, o_group_name FROM students"
    return execute_query(query, fetch=True)


# --- Глобальный поиск: выборки всех записей с ФИО (для app/global_search.py).
# Фильтрация по подстроке выполняется на стороне Python, т.к. SQLite LOWER()
# не меняет регистр кириллицы.

def search_all_encouragements():
    query = """
    SELECT e.id, e.encouragement_type AS kind, e.reason, e.date AS date_obj,
           s.id AS student_id, s.o_surname, s.o_name
    FROM encouragements e JOIN students s ON s.id = e.student_id
    ORDER BY e.date DESC
    """
    return execute_query(query, fetch=True)


def search_all_penalties():
    query = """
    SELECT p.id, p.penalty_type AS kind, p.reason, p.date AS date_obj,
           s.id AS student_id, s.o_surname, s.o_name
    FROM penalties p JOIN students s ON s.id = p.student_id
    ORDER BY p.date DESC
    """
    return execute_query(query, fetch=True)


def search_all_session_results():
    query = """
    SELECT sr.id, sr.subject, sr.type_exam, sr.grade, sr.date,
           s.id AS student_id, s.o_surname, s.o_name
    FROM session_results sr JOIN students s ON s.id = sr.student_id
    ORDER BY sr.date DESC
    """
    return execute_query(query, fetch=True)


def search_all_achievements():
    query = ("SELECT id, block, name, points, version, calc_type "
             "FROM achievements_catalog ORDER BY block, name")
    return execute_query(query, fetch=True)


def search_all_reviews():
    query = ("SELECT r.id, r.student_id, s.o_surname, s.o_name, s.o_lastname, "
             "s.o_group_name, r.achievement_id, a.name AS achievement_name, "
             "r.status, r.semester, r.final_points "
             "FROM roadmap_reviews r "
             "JOIN students s ON s.id = r.student_id "
             "LEFT JOIN achievements_catalog a ON a.id = r.achievement_id "
             "ORDER BY r.id DESC")
    return execute_query(query, fetch=True)


# Добавление поощрения
def add_encouragement(student_id, encouragement_type, reason, issued_by, date_obj, order_number):
    query = """
    INSERT INTO encouragements (student_id, encouragement_type, reason, issued_by, date, order_number)
    VALUES (?, ?, ?, ?, ?, ?)
    """
    execute_query(query, (student_id, encouragement_type, reason, issued_by, date_obj, order_number))

# Получение всех поощерений для студента
def get_encouragements_by_student(student_id):
    query = """
    SELECT encouragement_type, reason, issued_by, date AS date_obj, order_number FROM encouragements
    WHERE student_id = ?
    """
    return execute_query(query, (student_id,), fetch=True)

# Добавление взыскания
def add_penalty(student_id, penalty_type, reason, date_reason, issued_by, date_obj, order_number):
    query = """
    INSERT INTO penalties (student_id, penalty_type, reason, date_reason, issued_by, date, order_number)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    execute_query(query, (student_id, penalty_type, reason, date_reason, issued_by, date_obj, order_number))

# Получение всех взысканий для студента
def get_penalties_by_student(student_id):
    query = """
    SELECT penalty_type, reason, date_reason, issued_by, date AS date_obj, order_number FROM penalties
    WHERE student_id = ?
    """
    return execute_query(query, (student_id,), fetch=True)

def search_students_by_name_part(name_part):
    query = """
    SELECT id, o_surname, o_name, o_lastname FROM students
    WHERE o_surname LIKE ? OR o_name LIKE ? OR o_lastname LIKE ?
    """
    name_part = f"%{name_part}%"  # Добавляем % для поиска по части строки
    return execute_query(query, (name_part, name_part, name_part), fetch=True)

def get_subjects_by_name_part(name_part):
    query = "SELECT id, subject_name FROM subjects WHERE subject_name LIKE ?"
    name_part = f"%{name_part}%"  # Добавляем % для поиска по части строки
    return execute_query(query, (name_part,), fetch=True)
# ---------------------------------------------------------------------------
# Модуль «Дорожная карта» (наследие MKR): справочник достижений, экспертные
# решения, индивидуальные планы, ручные баллы и сводная аналитика.
# Таблицы живут в той же базе kanzler_pro.db; студент дорожной карты — это
# курсант из личного дела Канцлера (таблица students).
# ---------------------------------------------------------------------------

MKR_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS achievements_catalog (
        id TEXT PRIMARY KEY,
        block INTEGER NOT NULL,
        name TEXT NOT NULL,
        points INTEGER NOT NULL,
        version TEXT,
        calc_type TEXT DEFAULT 'ms'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roadmap_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        achievement_id TEXT,
        status TEXT DEFAULT 'pending',
        expert_comment TEXT,
        reviewed_at DATETIME,
        confirmation_file TEXT,
        semester INTEGER,
        k_ur REAL DEFAULT 1.0,
        k_role REAL DEFAULT 1.0,
        k_vn REAL DEFAULT 1.0,
        k_st REAL DEFAULT 1.0,
        final_points INTEGER,
        duration_months INTEGER DEFAULT 0,
        grant_amount REAL DEFAULT 0,
        ip_bonus INTEGER DEFAULT 0,
        FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS individual_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        semester INTEGER,
        plan_text TEXT,
        approved_by TEXT,
        approved_date DATETIME,
        status TEXT DEFAULT 'draft',
        FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS student_semester_status (
        student_id INTEGER,
        semester INTEGER,
        is_candidate BOOLEAN DEFAULT 0,
        is_resident BOOLEAN DEFAULT 0,
        candidate_applied_date DATETIME,
        resident_approved_date DATETIME,
        PRIMARY KEY (student_id, semester),
        FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS manual_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        semester INTEGER,
        block INTEGER,
        score INTEGER,
        comment TEXT,
        FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS semester_averages (
        student_id INTEGER,
        semester INTEGER,
        average_score REAL,
        PRIMARY KEY (student_id, semester),
        FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rr_student ON roadmap_reviews(student_id)",
    "CREATE INDEX IF NOT EXISTS idx_rr_status ON roadmap_reviews(status)",
]


def init_mkr_tables():
    """Создаёт таблицы Дорожной карты (идемпотентно)."""
    for sql in MKR_TABLES_SQL:
        execute_query(sql)
    # Лёгкая миграция: в исторической CREATE TABLE roadmap_reviews не было
    # created_at, из-за чего запрос уведомлений (get_recent_pending_reviews)
    # всегда падал в except. Колонка добавляется один раз; значение по
    # умолчанию для новых записей проставляет add_review.
    ensure_column("roadmap_reviews", "created_at", "DATETIME")


# Названия блоков достижений (справочник Road Map)
BLOCK_NAMES = {
    1: "Учёба",
    2: "Наука",
    3: "Творчество",
    4: "Общественное движение",
    5: "Спорт",
    6: "Добровольчество (волонтёрство)",
    7: "Патриотическое воспитание",
    8: "Иные достижения",
}


def get_blocks():
    return sorted(BLOCK_NAMES.items())


def add_achievement(ach_id, block, name, points, version="", calc_type="ms"):
    execute_query(
        "INSERT OR REPLACE INTO achievements_catalog "
        "(id, block, name, points, version, calc_type) VALUES (?, ?, ?, ?, ?, ?)",
        (str(ach_id), int(block), name, int(points), version, calc_type))


def delete_achievement(ach_id):
    execute_query("DELETE FROM achievements_catalog WHERE id = ?", (str(ach_id),))


def get_achievements(block=None, search=None):
    query = ("SELECT id, block, name, points, version, calc_type "
             "FROM achievements_catalog WHERE 1=1")
    params = []
    if block:
        query += " AND block = ?"
        params.append(int(block))
    if search:
        query += " AND (name LIKE ? OR id LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    query += " ORDER BY block, CAST(id AS INTEGER), id"
    return execute_query(query, tuple(params), fetch=True)


def count_achievements():
    rows = execute_query("SELECT COUNT(*) c FROM achievements_catalog", fetch=True)
    return rows[0]["c"] if rows else 0


def import_achievements_from_csv(filepath):
    """Импорт справочника достижений из CSV (формат наследия MKR)."""
    import csv as _csv
    added = 0
    with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
        reader = _csv.reader(f)
        rows = list(reader)
    start = 0
    if rows and not str(rows[0][0]).strip().isdigit():
        start = 1  # первая строка — заголовки
    for row in rows[start:]:
        if len(row) < 4:
            continue
        try:
            add_achievement(row[0], row[1], row[2], row[3],
                            row[4] if len(row) > 4 else "",
                            row[5] if len(row) > 5 else "ms")
            added += 1
        except Exception as e:
            from utils_logger import log_except
            log_except(f"database: импорт достижения строка {row[:2]}", e)
            continue
    return added


def calculate_final_points(calc_type, base_points, k_ur=1.0, k_role=1.0,
                           k_vn=1.0, k_st=1.0, duration_months=0,
                           grant_amount=0, ip_bonus=0):
    """Расчёт итоговых баллов по формуле из MKR."""
    base = int(base_points or 0)
    if calc_type == "avg_score":
        return base
    if calc_type == "grant":
        return int(grant_amount or 0)
    total = base * float(k_ur or 1) * float(k_role or 1) * \
        float(k_vn or 1) * float(k_st or 1)
    if calc_type == "month":
        total = total * max(int(duration_months or 0), 1)
    return int(round(total + int(ip_bonus or 0)))


def count_pending_reviews():
    """Число заявок на экспертизу Road Map в статусе 'на рассмотрении'."""
    try:
        rows = execute_query(
            "SELECT COUNT(*) FROM roadmap_reviews WHERE status = 'pending'",
            fetch=True)
        return int(rows[0][0]) if rows else 0
    except Exception:
        return 0


def get_recent_pending_reviews(limit=10):
    """Последние новые заявки (для колокольчика уведомлений).

    Примечание: в CREATE TABLE roadmap_reviews колонки created_at нет —
    раньше запрос всегда падал в except и использовался медленный запасной
    вариант. Теперь created_at добавляется идемпотентной миграцией
    ensure_column (см. init_mkr_tables), а запасной запрос оставлен на
    случай, если старая БД ещё не мигрирована.
    """
    try:
        ensure_column("roadmap_reviews", "created_at", "DATETIME")
    except Exception:
        pass  # если ALTER недоступен (например, база только для чтения)
    try:
        return execute_query(
            "SELECT r.id, r.student_id, s.o_surname, s.o_name, s.o_lastname, "
            "       a.name, r.semester, r.created_at "
            "FROM roadmap_reviews r "
            "LEFT JOIN students s ON s.id = r.student_id "
            "LEFT JOIN achievements_catalog a ON a.id = r.achievement_id "
            "WHERE r.status = 'pending' "
            "ORDER BY r.id DESC LIMIT ?",
            (int(limit),), fetch=True) or []
    except Exception:
        # created_at может отсутствовать в старой схеме — упрощённый вариант
        try:
            return execute_query(
                "SELECT r.id, r.student_id, s.o_surname, s.o_name, s.o_lastname, "
                "       a.name, r.semester, NULL AS created_at "
                "FROM roadmap_reviews r "
                "LEFT JOIN students s ON s.id = r.student_id "
                "LEFT JOIN achievements_catalog a ON a.id = r.achievement_id "
                "WHERE r.status = 'pending' "
                "ORDER BY r.id DESC LIMIT ?",
                (int(limit),), fetch=True) or []
        except Exception:
            return []


def add_review(student_id, achievement_id, semester, status="pending",
               confirmation_file="", comment=None, k_ur=1.0, k_role=1.0,
               k_vn=1.0, k_st=1.0, duration_months=0, grant_amount=0, ip_bonus=0):
    ach = execute_query(
        "SELECT points, calc_type FROM achievements_catalog WHERE id = ?",
        (str(achievement_id),), fetch=True)
    points, calc_type = (ach[0]["points"], ach[0]["calc_type"]) if ach else (0, "ms")
    final = calculate_final_points(calc_type, points, k_ur, k_role, k_vn, k_st,
                                   duration_months, grant_amount, ip_bonus) \
        if status == "approved" else None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    execute_query(
        """INSERT INTO roadmap_reviews
           (student_id, achievement_id, status, expert_comment, reviewed_at,
            confirmation_file, semester, k_ur, k_role, k_vn, k_st, final_points,
            duration_months, grant_amount, ip_bonus, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (student_id, str(achievement_id), status, comment,
         now if status != "pending" else None,
         confirmation_file, int(semester), k_ur, k_role, k_vn, k_st, final,
         duration_months, grant_amount, ip_bonus, now))


def update_review(review_id, status, comment=None, final_points=None):
    execute_query(
        """UPDATE roadmap_reviews SET status = ?, expert_comment = ?,
           reviewed_at = ?, final_points = ? WHERE id = ?""",
        (status, comment, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         final_points, review_id))


def delete_review(review_id):
    execute_query("DELETE FROM roadmap_reviews WHERE id = ?", (review_id,))


def get_reviews(student_id=None, status=None, semester=None):
    query = ("SELECT r.id, r.student_id, s.o_surname, s.o_name, s.o_lastname, "
             "s.o_group_name, r.achievement_id, a.name AS ach_name, a.block, "
             "a.points, r.status, r.semester, r.final_points, r.expert_comment, "
             "r.reviewed_at, r.confirmation_file, r.k_ur, r.k_role, r.k_vn, "
             "r.k_st, r.duration_months, r.grant_amount, r.ip_bonus "
             "FROM roadmap_reviews r "
             "JOIN students s ON s.id = r.student_id "
             "LEFT JOIN achievements_catalog a ON a.id = r.achievement_id "
             "WHERE 1=1")
    params = []
    if student_id:
        query += " AND r.student_id = ?"
        params.append(int(student_id))
    if status:
        query += " AND r.status = ?"
        params.append(status)
    if semester:
        query += " AND r.semester = ?"
        params.append(int(semester))
    query += " ORDER BY r.id DESC"
    return execute_query(query, tuple(params), fetch=True)


def get_student_total_points(student_id, semester=None):
    query = ("SELECT COALESCE(SUM(final_points), 0) t FROM roadmap_reviews "
             "WHERE status = 'approved' AND student_id = ?")
    params = [student_id]
    if semester:
        query += " AND semester = ?"
        params.append(int(semester))
    rows = execute_query(query, tuple(params), fetch=True)
    return rows[0]["t"] if rows else 0


def save_individual_plan(student_id, semester, plan_text, status="draft",
                         approved_by=None):
    existing = execute_query(
        "SELECT id FROM individual_plans WHERE student_id = ? AND semester = ?",
        (student_id, int(semester)), fetch=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if existing:
        execute_query(
            "UPDATE individual_plans SET plan_text = ?, status = ?, "
            "approved_by = ?, approved_date = ? WHERE id = ?",
            (plan_text, status, approved_by, now, existing[0]["id"]))
    else:
        execute_query(
            "INSERT INTO individual_plans (student_id, semester, plan_text, "
            "status, approved_by, approved_date) VALUES (?,?,?,?,?,?)",
            (student_id, int(semester), plan_text, status, approved_by, now))


def get_individual_plan(student_id, semester):
    rows = execute_query(
        "SELECT * FROM individual_plans WHERE student_id = ? AND semester = ?",
        (student_id, int(semester)), fetch=True)
    return rows[0] if rows else None


def set_semester_status(student_id, semester, is_candidate=None, is_resident=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = get_semester_status(student_id, semester)
    cand = int(bool(is_candidate)) if is_candidate is not None else (cur["is_candidate"] if cur else 0)
    res = int(bool(is_resident)) if is_resident is not None else (cur["is_resident"] if cur else 0)
    applied = now if (is_candidate and not (cur and cur["candidate_applied_date"])) else (cur["candidate_applied_date"] if cur else None)
    approved = now if (is_resident and not (cur and cur["resident_approved_date"])) else (cur["resident_approved_date"] if cur else None)
    execute_query(
        """INSERT INTO student_semester_status
           (student_id, semester, is_candidate, is_resident,
            candidate_applied_date, resident_approved_date)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(student_id, semester) DO UPDATE SET
             is_candidate = excluded.is_candidate,
             is_resident = excluded.is_resident,
             candidate_applied_date = excluded.candidate_applied_date,
             resident_approved_date = excluded.resident_approved_date""",
        (student_id, int(semester), cand, res, applied, approved))


def get_semester_status(student_id, semester):
    rows = execute_query(
        "SELECT * FROM student_semester_status WHERE student_id = ? AND semester = ?",
        (student_id, int(semester)), fetch=True)
    return rows[0] if rows else None


def add_manual_score(student_id, semester, block, score, comment=""):
    execute_query(
        "INSERT INTO manual_scores (student_id, semester, block, score, comment) "
        "VALUES (?,?,?,?,?)",
        (student_id, int(semester), int(block), int(score), comment))


def get_manual_scores(student_id=None, semester=None):
    query = ("SELECT m.*, s.o_surname, s.o_name, s.o_group_name "
             "FROM manual_scores m JOIN students s ON s.id = m.student_id "
             "WHERE 1=1")
    params = []
    if student_id:
        query += " AND m.student_id = ?"
        params.append(int(student_id))
    if semester:
        query += " AND m.semester = ?"
        params.append(int(semester))
    query += " ORDER BY m.id DESC"
    return execute_query(query, tuple(params), fetch=True)


def delete_manual_score(score_id):
    execute_query("DELETE FROM manual_scores WHERE id = ?", (score_id,))


def set_semester_average(student_id, semester, average_score):
    execute_query(
        """INSERT INTO semester_averages (student_id, semester, average_score)
           VALUES (?,?,?)
           ON CONFLICT(student_id, semester)
           DO UPDATE SET average_score = excluded.average_score""",
        (student_id, int(semester), float(average_score)))


def get_semester_average(student_id, semester):
    rows = execute_query(
        "SELECT average_score FROM semester_averages "
        "WHERE student_id = ? AND semester = ?",
        (student_id, int(semester)), fetch=True)
    return rows[0]["average_score"] if rows else None


def get_roadmap_stats():
    """Сводка для дашборда: количество решений, топ студентов, разрез по блокам."""
    def scalar(query, params=()):
        rows = execute_query(query, params, fetch=True)
        return rows[0][0] if rows else 0

    stats = {
        "students": scalar("SELECT COUNT(*) FROM students"),
        "achievements": count_achievements(),
        "total": scalar("SELECT COUNT(*) FROM roadmap_reviews"),
        "pending": scalar("SELECT COUNT(*) FROM roadmap_reviews WHERE status='pending'"),
        "approved": scalar("SELECT COUNT(*) FROM roadmap_reviews WHERE status='approved'"),
        "rejected": scalar("SELECT COUNT(*) FROM roadmap_reviews WHERE status='rejected'"),
        "points": scalar("SELECT COALESCE(SUM(final_points),0) FROM roadmap_reviews WHERE status='approved'"),
    }
    stats["top"] = execute_query(
        """SELECT s.id, s.o_surname, s.o_name, s.o_group_name,
                  SUM(r.final_points) pts
           FROM roadmap_reviews r JOIN students s ON s.id = r.student_id
           WHERE r.status = 'approved'
           GROUP BY r.student_id ORDER BY pts DESC LIMIT 10""", fetch=True)
    stats["by_block"] = execute_query(
        """SELECT a.block, COUNT(*) c, COALESCE(SUM(r.final_points),0) pts
           FROM roadmap_reviews r
           LEFT JOIN achievements_catalog a ON a.id = r.achievement_id
           WHERE r.status = 'approved' GROUP BY a.block ORDER BY a.block""",
        fetch=True)
    return stats
