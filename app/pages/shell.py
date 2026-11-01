"""Единая навигационная оболочка «Канцлер Про».

Ранее страницы унаследованы от Kanzler и при переходах выполняли
`page.controls.clear(); page.add(SomePage(page))` — в новом каркасе это
означало сброс бокового меню (страницы открывались «голыми», без панели
навигации, а из-за неограниченной высоты пустовали).

Модуль `shell` предоставляет функции-переходы, которые понимают оба режима:
  * если страница открыта внутри каркаса KantslerApp — контент меняется
    ВНУТРИ области содержимого (боковое меню сохраняется на всех экранах);
  * если страница открыта автономно (отладка/прямой запуск) — работает по
    старой схеме с пересозданием страницы.

Все переходы оборачивают целевой контрол в контейнер с фиксированными
размерами (ширина = доступная область минус панель), что устраняет ошибку
Flet 1.x "height is unbounded" и пустые экраны.
"""


#: Активный каркас приложения (ставится KantslerApp при входе и после выхода)
_current_shell = None


def set_shell(shell):
    """Регистрирует активный каркас (или None при выходе из приложения)."""
    global _current_shell
    _current_shell = shell


def get_shell():
    return _current_shell


def navigate(page_obj, cls_name, *args, dashboard=False, **kwargs):
    """Переход к странице по имени класса.

    Args:
        page_obj: ft.Page.
        cls_name: имя класса страницы в реестре (например "AddStudentPage").
        dashboard: открыть дашборд (главный экран) вместо cls_name.
    """
    from pages.registry import get_page  # лениво — во избежание циклов импортов

    if dashboard and _current_shell is not None:
        _current_shell.show_dashboard()
        return

    try:
        view = get_page(cls_name)(page_obj, *args, **kwargs)
    except TypeError:
        view = get_page(cls_name)(page_obj)

    if _current_shell is not None:
        # Страница открывается внутри каркаса: меню остаётся видимым.
        _current_shell.open_standalone(cls_name, view)
    else:
        page_obj.controls.clear()
        page_obj.add(view)
        page_obj.update()


def back_to_app(page_obj):
    """Кнопка «Назад»: вернуться в каркас (дашборд) или восстановить его."""
    if _current_shell is not None:
        _current_shell.show_dashboard()
    else:
        navigate(page_obj, "KantslerApp")
