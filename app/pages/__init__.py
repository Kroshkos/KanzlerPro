"""Пакет страниц приложения «Канцлер».

Каждая страница — отдельный модуль (ранее все 18 классов лежали в одном
файле ui.py на ~4000 строк). Межстраничные переходы выполняются через
``pages.registry.get_page`` — это разрывает циклические импорты.

Здесь собираются реальные классы: модули импортируются по одному, после
чего реестр ``registry._LOADED`` заполняется ссылками на классы.
"""

import importlib

from pages import registry
from pages.registry import PAGE_MODULES, get_page

_classes = {}
for _mod_name in sorted(set(PAGE_MODULES.values())):
    _module = importlib.import_module(_mod_name)
    for _name, _owner in PAGE_MODULES.items():
        if _owner == _mod_name and hasattr(_module, _name):
            _classes[_name] = getattr(_module, _name)

registry._LOADED.update(_classes)

__all__ = list(_classes) + ["get_page", "registry"]
globals().update(_classes)
