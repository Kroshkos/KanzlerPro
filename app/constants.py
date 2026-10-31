"""Единый источник истины для констант приложения «Канцлер».

UI-модули и слой работы с БД импортируют значения отсюда, чтобы списки
полей и ролей не разъезжались при правках (раньше EDITABLE_STUDENT_FIELDS
дублировался в ui.py, а STUDENT_FIELDS — в database.py).
"""

# Допустимые роли пользователей (используются в UsersPage и проверках прав)
ROLES = ("Администратор", "Пользователь")

ADMIN_ROLE = ROLES[0]
DEFAULT_ROLE = ROLES[1]

# Поля личного дела, доступные для редактирования на странице EditStudentPage.
# Каждое поле ОБЯЗАТЕЛЬНО должно входить в database.STUDENT_FIELDS —
# там находится белый список для защиты SQL; соответствие проверяется
# тестом tests/test_schema.py::test_editable_fields_are_whitelisted.
EDITABLE_STUDENT_FIELDS = [
    "o_surname", "o_name", "o_lastname", "o_course", "o_group_name",
    "o_gender", "o_age", "o_date_of_birth", "o_place_of_birth",
    "o_citizenship", "o_nationality", "o_religion", "o_marital_status",
    "kontact_residential_address", "kontact_number", "kontact_email",
    "ld_passport_series", "ld_passport_number", "ld_vb_personal_number",
    "if_social_origin", "if_family_composition", "if_number_of_children",
]
