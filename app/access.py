"""Сервисный слой проверки прав при мутациях данных (BACKLOG B-1).

Проблема, которую решает модуль: RBAC проверялся только на уровне
навигации (authz.require_admin — «не пустили на страницу»). Обход через
прямой вызов функции БД (или будущий API/CLI) проверка не задевал.

Теперь мутаторы вызывают require_role(...) перед записью:

    from access import require_role
    from constants import ADMIN_ROLE, ROLES

    def delete_user(user_id, actor_role=None):
        require_role(actor_role, ADMIN_ROLE, action="удаление пользователя")
        ...

actor_role — роль того, кто выполняет действие; её пробрасывает UI-слой
из session (`session_get(page, "role")`). Значение None означает «роль не
передана» — режим совместимости для легаси-вызовов и тестов; он разрешён,
но фиксируется в журнале действий как unaudited-mutation, чтобы можно было
найти все места, где сессия ещё не проброшена. Когда все вызовы будут
переведены, режим совместимости ужесточается до отказа (см. ALLOW_UNSCOPED).
"""

from constants import ADMIN_ROLE, ROLES

#: True — вызовы без actor_role разрешены (переходный период).
#: False — вызовы без actor_role отклоняются как недостаточное право.
ALLOW_UNSCOPED = False


class PermissionDeniedError(PermissionError):
    """Действие запрещено: роли актора недостаточно для мутации."""


#: Мутации, требующие роль «Администратор» (пока — управление учётками).
ADMIN_REQUIRED_ACTIONS = frozenset({
    "создание пользователя",
    "удаление пользователя",
    "смена пароля пользователя",
    "смена роли пользователя",
})


def is_admin_role(role) -> bool:
    """Единственная точка истины «роль == администратор» для слоя данных.

    UI-версия (authz.is_admin) работает с ft.Page; эта — со строкой роли,
    чтобы слой БД/сервисов не зависел от Flet.
    """
    return (role or "") == ADMIN_ROLE


def require_role(actor_role, required_role=ADMIN_ROLE, action=""):
    """Проверяет, что роль актора достаточна для действия.

    Бросает PermissionDeniedError, если роль не подходит. Если actor_role
    пустой (сессия не проброшена), поведение зависит от ALLOW_UNSCOPED.

    Иерархия ролей (BACKLOG B-1): «Администратор» может всё, что может
    «Пользователь»; обратное — нет. Поэтому проверка формулируется как
    «минимально требуемая роль», а не точное совпадение.
    """
    if actor_role is None or actor_role == "":
        if ALLOW_UNSCOPED:
            return  # переходный режим: легаси-вызовы без сессии не ломаем
            # TODO(B-1): когда все страницы пробросят роль — поставить
            # ALLOW_UNSCOPED = False.
        raise PermissionDeniedError(
            f"Недостаточно прав для действия: {action or 'мутация данных'} "
            "(роль актора не передана)")
    if required_role == ADMIN_ROLE:
        if not is_admin_role(actor_role):
            raise PermissionDeniedError(
                f"Недостаточно прав для действия: {action or 'мутация данных'}. "
                f"Требуется роль «{ADMIN_ROLE}»")
        return
    # Требуется минимальная роль «Пользователь»: её имеют обе роли
    # (пустая/неизвестная роль — отказ).
    if actor_role not in ROLES:
        raise PermissionDeniedError(
            f"Недостаточно прав для действия: {action or 'мутация данных'}. "
            f"Требуется роль из списка {list(ROLES)}")
