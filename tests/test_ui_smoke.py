"""Смоук-тесты переработанных страниц: конструктор + ключевые обработчики.

Flet-контролы можно создавать без запущенного окна, поэтому проверяем:
  * страница собирается без исключений;
  * collect/search-логика возвращает корректные структуры на реальной БД.
"""

import flet as ft
import pytest


class _FakeSession(dict):
    """dict-хранилище — заглушка page.session (SessionStorage)."""


class _Page:
    """Минимальная заглушка ft.Page: update()/add() — no-op."""

    def __init__(self):
        self.controls = []
        self.session = _FakeSession()

    def update(self):
        pass

    def add(self, *c):
        self.controls.extend(c)


def _admin():
    """B-1 (ALLOW_UNSCOPED=False): администратор нужен для мутаторов."""
    from constants import ADMIN_ROLE

    return {"role": ADMIN_ROLE}


@pytest.fixture()
def fake_page():
    return _Page(_admin())


def _make_student(surname, name, middlename, group, course):
    import repositories as repo
    repo.add_student({
        "o_surname": surname, "o_name": name, "o_lastname": middlename,
        "o_group_name": group, "o_course": course,
    }, actor_role=_admin()["role"])


class TestSearchPage:
    def test_page_builds(self, db, fake_page):
        from pages.search_page import SearchPage
        sp = SearchPage(fake_page)
        assert sp.search_surname is not None
        assert len(sp.additional_fields) == 17

    def test_add_and_remove_field(self, db, fake_page):
        from pages.search_page import SearchPage
        sp = SearchPage(fake_page)
        sp.additional_fields_dropdown.value = "Имя"
        sp.add_additional_field(None)
        assert sp.additional_fields["Имя"] is not None
        assert len(sp.additional_fields_container.controls) == 2  # поле + крестик
        sp.remove_field("Имя")
        assert sp.additional_fields["Имя"] is None
        assert len(sp.additional_fields_container.controls) == 0

    def test_collect_kwargs_maps_labels(self, db, fake_page):
        from pages.search_page import SearchPage
        sp = SearchPage(fake_page)
        sp.search_surname.value = "Иванов"
        sp.additional_fields_dropdown.value = "Группа"
        sp.add_additional_field(None)
        sp.additional_fields["Группа"].value = "1А"
        kwargs = sp._collect_kwargs()
        assert kwargs == {"surname": "Иванов", "group_name": "1А"}

    def test_search_returns_cards(self, db, fake_page):
        _make_student("Иванов", "Иван", "Иваныч", "1А", 1)
        _make_student("Петров", "Пётр", "Петрович", "2Б", 2)
        from pages.search_page import SearchPage
        sp = SearchPage(fake_page)
        sp.search_surname.value = "Иванов"
        sp.perform_search(None)
        assert len(sp.results_container.controls) == 2  # заголовок + список карточек
        texts = []
        def walk(c):
            if isinstance(c, ft.Text) and c.value:
                texts.append(str(c.value))
            for sub in getattr(c, "controls", []) or []:
                walk(sub)
            content = getattr(c, "content", None)
            if content is not None:
                walk(content)
        for ctrl in sp.results_container.controls:
            walk(ctrl)
        assert any("Найдено курсантов: 1" in t for t in texts)
        assert any("Иванов" in t for t in texts)

    def test_empty_criteria_shows_hint(self, db, fake_page):
        from pages.search_page import SearchPage
        sp = SearchPage(fake_page)
        sp.perform_search(None)
        texts = []
        def walk(c):
            if isinstance(c, ft.Text) and c.value:
                texts.append(str(c.value))
            for sub in getattr(c, "controls", []) or []:
                walk(sub)
            content = getattr(c, "content", None)
            if content is not None:
                walk(content)
        for ctrl in sp.results_container.controls:
            walk(ctrl)
        assert any("критерий" in t.lower() for t in texts)


class TestLoginPage:
    def test_login_builds_with_notice(self, db, fake_page):
        from pages.login_page import LoginPage
        lp = LoginPage(fake_page)
        assert lp.notice.control.visible is False

    def test_login_empty_shows_warning(self, db, fake_page):
        from pages.login_page import LoginPage
        lp = LoginPage(fake_page)
        lp.username.value = ""
        lp.password.value = ""
        lp.login_click(None)
        assert lp.notice.control.visible is True

    def test_login_wrong_password_shows_error(self, db, fake_page):
        from database import add_user
        from pages.login_page import LoginPage
        add_user("boss", "secret123", "Администратор", actor_role="Администратор")
        lp = LoginPage(fake_page)
        lp.username.value = "boss"
        lp.password.value = "WRONG"
        lp.login_click(None)
        assert lp.notice.control.visible is True
