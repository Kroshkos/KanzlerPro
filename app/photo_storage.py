"""Файловое хранилище фотографий курсантов (см. аудит, раздел «Производительность»).

Раньше фото курсантов хранились в колонке students.o_photo как base64-строки:
база раздувалась, SELECT * тянул мегабайты на каждую строку, а PDF-генератор
и карточка ЛД декодировали base64 на каждый показ. Теперь:

* в БД лежит только относительное имя файла (например "12.jpg") или пустая
  строка — колонка o_photo не меняет тип и миграции не требуются;
* сами файлы — в DATA_DIR/photos (config.PHOTOS_DIR);
* обратная совместимость со СТАРЫМИ базами: если в o_photo лежит base64
  (а не имя файла), photo_src() распознаёт это и отдаёт data-URI, как раньше.

Безопасность: save_photo() пишет только канонические имена "<id>.<ext>",
photo_path() резолвит путь строго внутри PHOTOS_DIR (защита от path
traversal при повреждённых/ручных значениях o_photo).
"""

import base64
import binascii
import os
import re

# Разрешённые расширения загружаемых фото (совпадает с allowed_extensions
# FilePicker в форме добавления курсанта).
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}


def _photos_dir() -> str:
    """Каталог фото берётся ДИНАМИЧЕСКИ (срез C-3).

    Порядок поиска актуального значения PHOTOS_DIR:
    1. атрибут модуля `photo_storage` — так подменяют путь тесты
       (monkeypatch.setattr(photo_storage, "PHOTOS_DIR", ...));
    2. атрибут модуля `config` — основной источник (перезагрузка
       конфигурации, KANZLER_DATA_DIR);
    3. собственный снимок PHOTOS_DIR, сделанный при импорте, — fallback
       для окружений, где модуль `config` недоступен по имени.

    Раньше использовался только статический импорт `from config import
    PHOTOS_DIR` — снимок пути, который не обновлялся при подмене
    конфигурации, из-за чего doctor и тесты видели рассинхрон путей.
    """
    own = globals().get("PHOTOS_DIR")
    if isinstance(own, str) and own:
        return own
    try:
        import config

        return config.PHOTOS_DIR
    except Exception:
        return own or ""


# Снимок по умолчанию (fallback): совместимость со старым кодом, который
# читал photo_storage.PHOTOS_DIR напрямую. Не является каноническим
# источником — канонический путь резолвится в _photos_dir() динамически.
try:
    from config import PHOTOS_DIR as _DEFAULT_PHOTOS_DIR
except Exception:  # pragma: no cover - окружения без config в sys.path
    _DEFAULT_PHOTOS_DIR = ""
PHOTOS_DIR = _DEFAULT_PHOTOS_DIR

# Признак «это base64, а не имя файла»: длинная строка без слэшей, состоящая
# только из символов base64. Имена файлов у нас короткие ("<int>.<ext>").
_B64_RE = re.compile(r"^[A-Za-z0-9+/=\s]{64,}$")


def _valid_ext(ext: str) -> str:
    ext = (ext or "").lower().lstrip(".")
    return ext if ext in ALLOWED_EXTENSIONS else "jpg"


def save_photo(raw_bytes: bytes, student_id: int, ext: str = "jpg") -> str:
    """Сохранить байты фото как <PHOTOS_DIR>/<student_id>.<ext>.

    Возвращает относительное имя файла — его надо положить в o_photo.
    Вызывается ПОСЛЕ создания записи о курсанте (нужен его id).
    """
    if not raw_bytes:
        return ""
    photos_dir = _photos_dir()
    os.makedirs(photos_dir, exist_ok=True)
    filename = f"{int(student_id)}.{_valid_ext(ext)}"
    path = os.path.join(photos_dir, filename)
    with open(path, "wb") as f:
        f.write(raw_bytes)
    return filename


def migrate_legacy_base64() -> int:
    """Однократная миграция: переносит старые base64-фото из БД в файлы.

    После миграции в колонке o_photo остаются только имена файлов — SELECT
    больше не тянет мегабайты base64 на каждую строку, а photo_src() не
    декодирует base64 на каждый показ. Повторный вызов безопасен (no-op).
    Возвращает количество перенесённых записей.
    """
    from database import execute_query  # ленивый импорт: без цикличной зависимости
    migrated = 0
    rows = execute_query("SELECT id, o_photo FROM students", fetch=True) or []
    for r in rows:
        value = (r["o_photo"] if isinstance(r, dict) else r[1]) or ""
        if not looks_like_base64(value):
            continue
        try:
            raw = base64.b64decode(value.strip())
            sid = int(r["id"] if isinstance(r, dict) else r[0])
            filename = save_photo(raw, sid, ext="png")
            if filename:
                execute_query("UPDATE students SET o_photo = ? WHERE id = ?",
                              params=(filename, sid))
                migrated += 1
        except (binascii.Error, ValueError) as e:
            from utils_logger import log_except
            log_except(f"photo_storage: миграция base64 id={r[0] if isinstance(r, dict) else r['id']}", e)
    return migrated


def legacy_base64_count() -> int:
    """Сколько записей o_photo всё ещё хранят base64 (для doctor/тестов)."""
    from database import execute_query

    rows = execute_query("SELECT id, o_photo FROM students", fetch=True) or []
    return sum(1 for r in rows
               if looks_like_base64((r["o_photo"] if isinstance(r, dict) else r[1]) or ""))


def vacuum_database() -> bool:
    """Освобождает место файла БД после миграции base64-фото (BACKLOG C-3).

    SQLite не возвращает освобождённые страницы файлу при UPDATE — файл
    остаётся «раздутым» до VACUUM. Вызывать после подтверждённой миграции
    migrate_legacy_base64(). Возвращает True, если VACUUM выполнен.
    Перед вакуумом убеждаемся, что base64 не осталось: иначе удаление
    строк было бы преждевременным (данные фото ещё не в файлах).
    """
    if legacy_base64_count() > 0:
        return False  # миграция не завершена — рано освобождать место
    from database import connect_to_db

    conn = connect_to_db()
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()
    return True


def delete_photo(filename: str) -> None:
    """Удалить файл фото из хранилища (при удалении курсанта).

    Толерантна к base64-значениям из старых БД и к отсутствующим файлам.
    """
    path = photo_path(filename)
    if path is None:
        return
    try:
        os.remove(path)
    except OSError:
        pass  # файла нет / права — не критично для удаления записи


def photo_path(value: str):
    """Полный путь к файлу фото, если value — корректное имя в PHOTOS_DIR.

    Возвращает None, если value пусто, это base64 из старой БД или значение
    пытается выйти за пределы хранилища (path traversal).
    """
    if not value:
        return None
    value = value.strip()
    # Старые записи: вместо имени файла там base64 — это не путь.
    if _B64_RE.match(value) and "." not in value[:20]:
        return None
    if os.sep in value or "/" in value or ".." in value:
        return None
    photos_dir = _photos_dir()
    path = os.path.realpath(os.path.join(photos_dir, value))
    if not path.startswith(os.path.realpath(photos_dir) + os.sep):
        return None
    return path


def looks_like_base64(value: str) -> bool:
    """Признак того, что в o_photo лежит base64 (миграция старых данных)."""
    if not value:
        return False
    value = value.strip()
    if len(value) < 64:
        return False
    if not _B64_RE.match(value):
        return False
    try:
        base64.b64decode(value[:128] + "==", validate=False)
        return True
    except (binascii.Error, ValueError):
        return False


def photo_src(value: str) -> str:
    """Строка src для ft.Image по значению колонки o_photo.

    * новое хранение (имя файла) → абсолютный local-путь к файлу;
    * старое хранение (base64)   → data-URI (как было до рефакторинга);
    * пусто/битое значение        → "" (вызывающая сторона рисует заглушку).
    """
    if not value:
        return ""
    value = value.strip()
    if looks_like_base64(value):
        return f"data:image/jpeg;base64,{value}"
    path = photo_path(value)
    if path and os.path.exists(path):
        return path
    return ""


def main() -> int:
    """Точка входа CLI миграции фото (BACKLOG C-3).

    Использование::

        python -m app.photo_storage             # только миграция base64→файлы
        python -m app.photo_storage --vacuum    # + освобождение места в БД

    VACUUM выполняется только если после миграции в базе не осталось
    base64-значений (см. vacuum_database) — преждевременное сжатие опасно.
    """
    import sys

    from database import init_db

    init_db()
    n = migrate_legacy_base64()
    print(f"photo_storage: мигрировано записей base64→файл: {n}")
    if "--vacuum" in sys.argv[1:]:
        if vacuum_database():
            print("photo_storage: VACUUM выполнен, файл БД сжат")
        else:
            print("photo_storage: VACUUM пропущен — остались base64-значения "
                  "(повторите миграцию или проверьте битые данные)")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
