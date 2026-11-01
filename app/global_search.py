"""Глобальный поиск по всей базе «Канцлер Про».

Единый запрос находит:
  * курсантов (ФИО, группа, должность/звание) — наследие Kanzler;
  * заявки экспертизы Дорожной карты (номер, статус, достижение);
  * достижения каталога Road Map;
  * дисциплинарные записи (поощрения/взыскания) и результаты сессий.

Используется строкой поиска в шапке каркаса (KantslerApp) и страницей
результатов ``SearchResultsPage``.
"""

import re
import sqlite3

from database import (execute_query, get_students, search_all_achievements,
                      search_all_encouragements, search_all_penalties,
                      search_all_reviews, search_all_session_results)


def _like(term):
    # SQLite LOWER() не работает с кириллицей — регистр приводим в Python.
    # Экранирование спецсимволов LIKE нужно, чтобы «%»/«_» в запросе
    # пользователя искалились как обычные символы (см. ESCAPE '\' ниже).
    escaped = re.sub(r"([%_\\])", r"\\\1", term.strip())
    return f"%{escaped.lower()}%"


def _norm(term):
    """Нормализация для Python-фильтрации (регистронезависимо, ё->е)."""
    return term.strip().lower().replace("ё", "е")


def _py_contains(haystack, needle_norm):
    if haystack is None:
        return False
    return needle_norm in str(haystack).lower().replace("ё", "е")


def global_search(query, limit_per_group=25):
    """Возвращает dict групп результатов: students / reviews / achievements
    / discipline / sessions. Пустая строка -> пустой dict."""
    q = (query or "").strip()
    out = {"students": [], "reviews": [], "achievements": [],
           "discipline": [], "sessions": []}
    if len(q) < 2:
        return out
    needle = _norm(q)

    # --- Курсанты (ФИО / группа) ---
    # SQLite LOWER() не умеет менять регистр кириллицы, поэтому строки
    # фильтруем на стороне Python (get_students() выбирает все записи).
    try:
        rows = get_students() or []
        out["students"] = [
            r for r in rows
            if (_py_contains(f"{r['o_surname']} {r['o_name']} {r['o_lastname']}", needle)
                or _py_contains(r["o_group_name"], needle))
        ][:limit_per_group]
    except sqlite3.Error:
        out["students"] = []

    # --- Заявки экспертизы (Road Map) ---
    try:
        rows = []
        for r in (search_all_reviews() or []):
            if (_py_contains(r["achievement_name"], needle)
                    or _py_contains(r["o_surname"], needle)):
                rows.append(r)
            if len(rows) >= limit_per_group:
                break
        out["reviews"] = rows
    except sqlite3.Error:
        out["reviews"] = []

    # --- Достижения каталога ---
    try:
        rows = []
        for a in (search_all_achievements() or []):
            if (_py_contains(a["name"], needle)
                    or _py_contains(a["id"], needle)):
                rows.append(a)
            if len(rows) >= limit_per_group:
                break
        out["achievements"] = rows
    except sqlite3.Error:
        out["achievements"] = []

    # --- Дисциплинарная практика ---
    try:
        enc = [dict(r) for r in (search_all_encouragements() or [])
               if _py_contains(r["reason"], needle)
               or _py_contains(r["o_surname"], needle)]
        pen = [dict(r) for r in (search_all_penalties() or [])
               if _py_contains(r["reason"], needle)
               or _py_contains(r["o_surname"], needle)]
        for r in enc:
            r["kind"] = r.get("encouragement_type")
        for r in pen:
            r["kind"] = r.get("penalty_type")
        merged = sorted(enc + pen,
                        key=lambda r: str(r.get("date_obj") or ""), reverse=True)
        out["discipline"] = merged[:limit_per_group]
    except sqlite3.Error:
        out["discipline"] = []

    # --- Результаты сессий ---
    try:
        rows = []
        for sr in (search_all_session_results() or []):
            if (_py_contains(sr["subject"], needle)
                    or _py_contains(sr["o_surname"], needle)):
                rows.append(sr)
            if len(rows) >= limit_per_group:
                break
        out["sessions"] = rows
    except sqlite3.Error:
        out["sessions"] = []

    return out


def total_found(result):
    return sum(len(v) for v in result.values())
