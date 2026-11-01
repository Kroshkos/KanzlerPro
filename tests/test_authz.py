"""Тесты authz — централизованной проверки прав (RBAC).

Flet-объекты не нужны: require_admin при отказе импортирует flet, но для
успешной ветки достаточно фейковой страницы с dict-сессией.
"""

import types

import pytest

import authz
from constants import ADMIN_ROLE, DEFAULT_ROLE


class _FakeStore:
    """Стаб page.session.store из Flet >= 0.70 (get/set/clear)."""

    def __init__(self, data):
        self._data = data

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value

    def clear(self):
        self._data.clear()


def _page_with_role(role):
    """Минимальный стаб — ft.Page: utils.session_get читает page.session.store."""
    data = {"role": role, "username": "tester"} if role is not None else {}
    return types.SimpleNamespace(session=_FakeStore(data))


class TestCurrentRoleAndIsAdmin:
    def test_admin(self):
        p = _page_with_role(ADMIN_ROLE)
        assert authz.current_role(p) == ADMIN_ROLE
        assert authz.is_admin(p) is True

    def test_plain_user_is_not_admin(self):
        assert authz.is_admin(_page_with_role(DEFAULT_ROLE)) is False

    def test_anonymous_is_not_admin(self):
        assert authz.is_admin(_page_with_role(None)) is False

    def test_old_buggy_literal_admin_is_not_admin(self):
        """Регрессия аудита: роль 'admin' (англ.) не должна давать прав —
        в БД константа 'Администратор'; рассинхрон литералов и был багом."""
        assert authz.is_admin(_page_with_role("admin")) is False


class TestRequireAdmin:
    def test_admin_gets_none(self):
        assert authz.require_admin(_page_with_role(ADMIN_ROLE)) is None

    def test_denied_for_user(self):
        denied = authz.require_admin(_page_with_role(DEFAULT_ROLE))
        assert denied is not None  # контрол-заглушка вместо страницы

    def test_admin_only_pages_registry(self):
        """Страницы мутаций баллов/пользователей/журнала обязаны быть закрыты."""
        for name in ("UsersPage", "LogsPage", "RoadmapExpertPage"):
            assert name in authz.ADMIN_ONLY_PAGES
