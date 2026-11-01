"""Реестр страниц: единая точка доступа к классам UI.

Разрыв циклических импортов между модулями пакета ``pages``: страницы
обращаются друг к другу только через ``registry.get_page`` (ленивый поиск
класса по имени), а не прямыми ``from pages.x import Y``. Реальная связка
классов выполняется один раз в ``pages/__init__.py`` после определения всех
классов.

Структура:
    PAGE_MODULES   — имя класса -> импорт-путь модуля (строки, всегда доступны);
    _LOADED        — имя класса -> класс (заполняется в __init__.py или лениво);
    get_page(name) — возвращает класс, при необходимости импортируя модуль.
"""

PAGE_MODULES = {
    "LoginPage": "pages.login_page",
    "KantslerApp": "pages.home_page",
    "UsersPage": "pages.users_page",
    "LogsPage": "pages.logs_page",
    "SearchPage": "pages.search_page",
    "KadriWorkPage": "pages.kadri_page",
    "AddStudentPage": "pages.kadri_page",
    "ShowStudentsPage": "pages.kadri_page",
    "EditStudentPage": "pages.kadri_page",
    "PositionChangePage": "pages.position_rank_page",
    "RankChangePage": "pages.position_rank_page",
    "StudiWorkPage": "pages.study_page",
    "VprWorkPage": "pages.study_page",
    "SessionResultsPage": "pages.study_page",
    "EncouragementWorkPage": "pages.vpr_page",
    "PenaltyWorkPage": "pages.vpr_page",
    "PremiaWorkPage": "pages.premia_page",
    "PersonalFilePage": "pages.personal_file_page",
    # --- Модуль «Дорожная карта» (наследие MKR) ---
    "DashboardPage": "pages.dashboard_page",
    "RoadmapCatalogPage": "pages.roadmap_catalog_page",
    "RoadmapExpertPage": "pages.roadmap_expert_page",
    "RoadmapIprPage": "pages.roadmap_ipr_page",
    "RoadmapRatingPage": "pages.roadmap_rating_page",
    "RoadmapReportsPage": "pages.roadmap_reports_page",
    # --- Глобальный поиск из шапки ---
    "SearchResultsPage": "pages.search_results_page",
}

# Имена классов, заполняется пакетом pages.__init__ (или лениво в get_page).
_LOADED: dict = {}


def get_page(name):
    """Возвращает класс страницы по имени (лениво, без циклических импортов)."""
    cls = _LOADED.get(name)
    if cls is not None:
        return cls
    module_path = PAGE_MODULES.get(name)
    if module_path is None:
        raise KeyError(f"Неизвестная страница: {name}")
    # Ленивый путь: пакет ещё не связан (например, прямой импорт модуля
    # страницы вне pages/__init__) — импортируем модуль и берём класс.
    from importlib import import_module
    module = import_module(module_path)
    cls = getattr(module, name, None)
    if cls is None:
        raise KeyError(f"Класс {name} не найден в модуле {module_path}")
    _LOADED[name] = cls
    return cls
