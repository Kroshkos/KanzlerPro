"""Консольная диагностика приложения «Канцлер Про» (BACKLOG D-5).

Запуск из корня проекта:

    python -m app.doctor

Проверяет без запуска GUI:
  * конфигурацию путей (DATA_DIR, DB_PATH, PHOTOS_DIR, REPORTS_DIR);
  * читаемость SQLite-файла и результат PRAGMA integrity_check;
  * наличие обязательных таблиц схемы;
  * целостность хеш-цепочки журнала действий (B-5);
  * каталог резервных копий и их количество/давность (A-4);
  * версии зависимостей (flet / pandas / openpyxl / reportlab).

Коды выхода: 0 — всё в порядке, 1 — найдены проблемы.
"""

import os
import sqlite3
import sys

# Плоские импорты слоя app работают и при запуске «python -m app.doctor»:
# пакет добавляет свой каталог в sys.path (как main.py для app/).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _check_line(name, ok, detail=""):
    mark = "OK " if ok else "FAIL"
    print(f"[{mark}] {name}" + (f": {detail}" if detail else ""))
    return bool(ok)


def check_paths():
    """Пути конфигурации существуют (каталоги создаются ensure_dirs())."""
    from config import DATA_DIR, DB_PATH, PHOTOS_DIR, REPORTS_DIR, ensure_dirs

    ensure_dirs()
    problems = []
    for name, path in (("DATA_DIR", DATA_DIR), ("PHOTOS_DIR", PHOTOS_DIR),
                       ("REPORTS_DIR", REPORTS_DIR)):
        if not _check_line(name, os.path.isdir(path), path):
            problems.append(name)
    db_ok = os.path.isfile(DB_PATH)
    _check_line("DB_PATH", db_ok, DB_PATH if db_ok else "файл БД ещё не создан")
    return problems


def check_database_integrity():
    """PRAGMA integrity_check + наличие ключевых таблиц."""
    from config import DB_PATH

    if not os.path.isfile(DB_PATH):
        _check_line("База данных", False, f"нет файла {DB_PATH}")
        return ["db-missing"]
    problems = []
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            ok = bool(result) and result[0] == "ok"
            if not _check_line("integrity_check", ok, str(result[0] if result else "?")):
                problems.append("integrity_check")

            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"users", "students", "logs", "encouragements",
                        "penalties", "roadmap_reviews"}
            missing = sorted(required - tables)
            if not _check_line("таблицы схемы", not missing,
                               "не хватает: " + ", ".join(missing) if missing
                               else f"{len(tables)} таблиц"):
                problems.append("tables")
        finally:
            conn.close()
    except sqlite3.Error as e:
        _check_line("База данных", False, f"ошибка открытия: {e}")
        problems.append("sqlite-error")
    return problems


def check_logs_chain():
    """Целостность хеш-цепочки журнала (B-5). Пустой журнал — норма."""
    from database import verify_logs_chain

    try:
        broken = verify_logs_chain()
    except sqlite3.Error as e:
        _check_line("Журнал (hash-цепочка)", False, f"ошибка проверки: {e}")
        return ["logs-chain"]
    ok = not broken
    _check_line("Журнал (hash-цепочка)", ok,
                f"нарушены строки: {broken[:10]}" if not ok else "цепочка цела")
    return [] if ok else ["logs-chain"]


def check_backups():
    """Каталог backups существует, копии есть, последняя — не старше суток."""
    from datetime import datetime

    from config import DATA_DIR

    backups_dir = os.path.join(DATA_DIR, "backups")
    if not os.path.isdir(backups_dir):
        _check_line("Резервные копии", False, f"нет каталога {backups_dir}")
        return ["backups-dir"]
    files = [f for f in os.listdir(backups_dir) if f.endswith(".db")]
    newest_age_h = None
    if files:
        newest = max(os.path.getmtime(os.path.join(backups_dir, f)) for f in files)
        newest_age_h = (datetime.now() - datetime.fromtimestamp(newest)).total_seconds() / 3600
    fresh = newest_age_h is not None and newest_age_h <= 24
    _check_line("Резервные копии", fresh,
                f"{len(files)} копий, последней {newest_age_h:.1f} ч"
                if files else "копий пока нет (создаются при старте приложения)")
    return [] if fresh else ["backups-stale"]


def check_photos():
    """Целостность файлового хранилища фото (BACKLOG C-3/D-3).

    * каталог PHOTOS_DIR существует и доступен для записи;
    * в БД не осталось незамигрированных base64-значений o_photo —
      иначе файл базы раздут, а карточки показывают медленный data-URI;
    * на каждое имя файла из o_photo есть соответствующий файл на диске
      (потерянные файлы — предупреждение, не ошибка: запись курсанта
      при этом остаётся валидной).
    """
    try:
        import photo_storage
        from photo_storage import legacy_base64_count, photo_path
    except ImportError as e:  # pragma: no cover
        _check_line("Хранилище фото", False, f"модуль недоступен: {e}")
        return ["photos-module"]

    problems = []
    from config import DB_PATH

    # Каталог фото резолвим через photo_storage._photos_dir(): он учитывает
    # подмену пути (тесты/перезагрузка config), тогда как статический импорт
    # config.PHOTOS_DIR давал рассинхрон doctor ↔ photo_storage.
    PHOTOS_DIR = photo_storage._photos_dir()

    writable = os.access(PHOTOS_DIR, os.W_OK) if os.path.isdir(PHOTOS_DIR) else False
    if not _check_line("PHOTOS_DIR (запись)", writable or not os.path.isfile(DB_PATH),
                       PHOTOS_DIR):
        problems.append("photos-dir")

    if not os.path.isfile(DB_PATH):
        _check_line("Фото в БД", True, "база ещё не создана — проверять нечего")
        return problems

    try:
        legacy = legacy_base64_count()
    except sqlite3.Error as e:
        _check_line("Фото в БД", False, f"ошибка запроса: {e}")
        return ["photos-query"]
    if not _check_line("Фото в БД (base64-легаси)", legacy == 0,
                       f"незамигрированных записей: {legacy} "
                       "(выполните photo_storage.migrate_legacy_base64())"
                       if legacy else "все фото в файлах"):
        problems.append("photos-legacy-base64")

    from database import get_photo_references

    missing = 0
    refs = get_photo_references()
    for _sid, value in refs:
        path = photo_path(value or "")
        if path is None:
            continue  # base64-легаси учтено проверкой выше
        if not os.path.exists(path):
            missing += 1
    _check_line("Файлы фото на диске", True,
                f"{len(refs)} ссылок, отсутствующих файлов: {missing}"
                + (" — ПРЕДУПРЕЖДЕНИЕ" if missing else ""))
    return problems


def check_versions():
    """Версии ключевых зависимостей (справочно, не влияет на код выхода)."""
    packages = ("flet", "pandas", "openpyxl", "reportlab",
                "python-docx", "python-dotenv")
    from importlib.metadata import PackageNotFoundError, version

    parts = []
    for p in packages:
        try:
            parts.append(f"{p}=={version(p)}")
        except PackageNotFoundError:
            parts.append(f"{p}=ОТСУТСТВУЕТ")
    all_present = "=ОТСУТСТВУЕТ" not in " ".join(parts)
    _check_line("Зависимости", all_present, ", ".join(parts))
    return [] if all_present else ["deps"]


def run_checks():
    """Выполняет все проверки, возвращает список проблем (пусто = OK)."""
    print(f"Канцлер Про — диагностика (Python {sys.version.split()[0]})")
    print("-" * 60)
    problems = []
    problems += check_paths()
    problems += check_database_integrity()
    problems += check_logs_chain()
    problems += check_photos()
    problems += check_backups()
    problems += check_versions()
    print("-" * 60)
    if problems:
        print(f"Найдено проблем: {len(problems)} -> {', '.join(problems)}")
    else:
        print("Проблем не обнаружено.")
    return problems


def main(argv=None):
    """Точка входа: коды выхода 0 — OK, 1 — найдены проблемы.

    Флаг ``--no-backups`` (используется в CI, пункт T-4) понижает
    «нет свежих резервных копий» из ошибки в предупреждение: в CI база
    создаётся с нуля и бэкапы там не генерируются намеренно.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    ignore_backups = "--no-backups" in argv
    problems = run_checks()
    if ignore_backups and "backups-dir" in problems:
        problems.remove("backups-dir")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
