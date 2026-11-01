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

import os
import re
import base64
import binascii

from config import PHOTOS_DIR

# Разрешённые расширения загружаемых фото (совпадает с allowed_extensions
# FilePicker в форме добавления курсанта).
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}

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
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    filename = f"{int(student_id)}.{_valid_ext(ext)}"
    path = os.path.join(PHOTOS_DIR, filename)
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
    path = os.path.realpath(os.path.join(PHOTOS_DIR, value))
    if not path.startswith(os.path.realpath(PHOTOS_DIR) + os.sep):
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
