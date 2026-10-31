"""Модуль безопасности приложения «Канцлер».

Хранение паролей в открытом виде недопустимо, поэтому используется
стойкое ключепроизводное функции PBKDF2-HMAC-SHA256 (стандартная
библиотека hashlib, внешних зависимостей не требуется):

    формат записи в БД:  pbkdf2_sha256$<итерации>$<hex-соль>$<hex-хеш>

Старые записи с открытыми паролями распознаются по отсутствию префикса
и прозрачно мигрируются в хеши при первой успешной авторизации.
"""

import hashlib
import hmac
import os

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 200_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Возвращает строку вида 'pbkdf2_sha256$iter$salt_hex$hash_hex'."""
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def is_hashed(stored: str) -> bool:
    """True, если запись уже является хешем нового формата."""
    return bool(stored) and stored.startswith(f"{_ALGORITHM}$")


def verify_password(password: str, stored: str) -> bool:
    """Проверяет пароль против хеша.

    Возвращает True/False. Для устаревших (не хешированных) записей
    выполняет сравнение по константному времени, чтобы не раскрывать
    длину/содержимое через время ответа.
    """
    if not stored:
        return False
    if not is_hashed(stored):
        # Легаси-запись: открытый пароль в БД (до миграции).
        return hmac.compare_digest(password, stored)
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGORITHM:
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def needs_migration(stored: str) -> bool:
    """True, если запись надо перезаписать хешем (открытый пароль)."""
    return bool(stored) and not is_hashed(stored)
