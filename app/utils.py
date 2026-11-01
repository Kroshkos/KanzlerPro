import flet as ft


def validate_student_data(full_name, course, group_name):
    if not full_name or not course or not group_name:
        return False
    try:
        int(course)
        return True
    except ValueError:
        return False


# --- Совместимость API page.session между версиями Flet ---------------------
# * Flet 0.28.x: page.session — это SessionStorage с методами set()/get()/clear().
# * Flet >= 0.70/0.80/1.0: page.session — объект Session. Он НЕ поддерживает
#   item assignment (session[key] = value -> TypeError) и НЕ имеет set()/get().
#   Хранилище данных сессии переехало в page.session.store (SessionStore),
#   где есть методы set()/get()/contains_key()/remove()/clear().
# Функции ниже автоматически определяют доступный API.


def _session_store(page: ft.Page):
    """Возвращает объект-хранилище session независимо от версии Flet."""
    session = page.session
    # Flet >= 0.70: хранилище доступно через property .store
    store = getattr(session, "store", None)
    if store is not None and hasattr(store, "set"):
        return store
    # Flet 0.28.x: сам session и есть SessionStorage
    if hasattr(session, "set"):
        return session
    raise RuntimeError(
        f"Неизвестный API page.session ({type(session).__name__}). "
        "Обновите utils.py под текущую версию Flet."
    )


def session_set(page: ft.Page, key: str, value):
    """Сохраняет значение в session-хранилище страницы (любая версия Flet)."""
    _session_store(page).set(key, value)


def session_get(page: ft.Page, key: str, default=None):
    """Читает значение из session-хранилища страницы (любая версия Flet)."""
    value = _session_store(page).get(key)
    return default if value is None else value


def session_clear(page: ft.Page):
    """Полностью очищает session-хранилище страницы (любая версия Flet)."""
    _session_store(page).clear()


# --- Совместимость SnackBar между версиями Flet -----------------------------
# * Flet 0.28.x: использовался атрибут page.snack_bar (присваивание + .open = True).
# * Flet >= 0.70/1.0: page.snack_bar удалён; SnackBar добавляется в page.overlay,
#   управляется свойством .open и автоматически удаляется из overlay после закрытия
#   (on_close handler ниже).
# Функция show_snack работает с обеими версиями API.


def show_snack(page: ft.Page, message):
    """Показывает SnackBar с текстом `message` (любая версия Flet)."""
    text = message if isinstance(message, ft.Control) else ft.Text(str(message))
    snack = ft.SnackBar(content=text)

    if hasattr(page, "snack_bar"):  # старый API (Flet <= 0.28.x)
        page.snack_bar = snack
        page.snack_bar.open = True
        page.update()
        return

    # Новый API (Flet >= 0.70 / 1.0): overlay-хранилище на странице
    def _remove_from_overlay(e=None):
        try:
            page.overlay.remove(snack)
        except ValueError:
            pass
        page.update()

    snack.on_close = _remove_from_overlay
    page.overlay.append(snack)
    snack.open = True
    page.update()


# ---------------------------------------------------------------------------
# Безопасные преобразования значений.
# В Flet 1.x значения из протокола (размеры окна, e.control.data и т.п.)
# могут приходить как строки — прямое сравнение str с числом или int()/float()
# от «грязного» значения роняет приложение. Все эти хелперы устойчивы к
# строкам, запятому как десятичному разделителю и пустым значениям.
# ---------------------------------------------------------------------------
def to_num(value, default=None):
    """Любое значение -> float (или default). Принимает строки '1920.5', '3,14'."""
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def to_int(value, default=None):
    """Любое значение -> int (или default). Строки, float, None — безопасно."""
    n = to_num(value, None)
    if n is None:
        return default
    return int(n)


def row_get(row, key, default=None):
    """Безопасное чтение колонки из sqlite3.Row / dict по имени.

    sqlite3.Row не поддерживает .get(), а KeyError при отсутствующей
    колонке роняет on_click-хендлер — возвращаем default вместо падения.
    """
    if row is None:
        return default
    try:
        keys = row.keys()
    except AttributeError:
        return row.get(key, default)  # обычный dict
    if key not in keys:
        return default
    value = row[key]
    return default if value is None else value
