"""Кэш редко меняющихся справочников (BACKLOG C-4).

Списки групп, курсов набора и блоков достижений используются фильтрами UI
на каждой перерисовке страницы, но меняются единицы раз в день. Каждый
такой запрос — лишнее открытие SQLite-соединения; модуль держит значение
в памяти процесса и сбрасывает его при любой записи, затрагивающей
соответствующую таблицу.

Инвалидация — «широкая» (по имени таблицы): пропущенный инвалидатор
приведёт лишь к устаревшему списку фильтров до ближайшей записи, но не к
портче данных — сами данные всегда читаются из БД напрямую.

Пример:
    from cache import cached

    def list_group_names():
        return [r[0] for r in database.list_groups()]

    groups = cached("groups", list_group_names)   # считаем
    invalidate("students")                        # после добавления курсанта
"""

import threading

_lock = threading.RLock()
_store = {}          # key -> value
_deps = {}           # table -> set(keys), зависящие от таблицы


def cached(key, loader, table=None):
    """Возвращает значение из кэша; при промахе вычисляет через loader().

    table — имя таблицы-источника для точечной инвалидации (см.
    invalidate). Если table не указан, значение живёт до invalidate_all().
    """
    with _lock:
        if key in _store:
            return _store[key]
        value = loader()
        _store[key] = value
        if table:
            _deps.setdefault(table, set()).add(key)
        return value


def invalidate(table=None):
    """Сбрасывает кэш записей по таблице; table=None — сбрасывает всё."""
    with _lock:
        if table is None:
            _store.clear()
            _deps.clear()
            return
        for key in _deps.pop(table, set()):
            _store.pop(key, None)


def invalidate_all():
    """Полный сброс кэша (используется тестами и тяжёлыми миграциями)."""
    invalidate(None)


def stats():
    """Отладочная сводка: какие ключи закэшированы (для doctor/тестов)."""
    with _lock:
        return sorted(_store.keys())
