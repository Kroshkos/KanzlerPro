"""Централизованное логирование «Канцлер Про».

Раньше в UI-слое встречались конструкции ``except Exception: pass``, которые
скрывали реальные ошибки (например, падение запроса к БД выглядело как
«пустая страница»). Теперь все перехваченные исключения пишутся в
``data/logs/kanzler.log`` с указанием файла и строки, где они произошли, —
это позволяет диагностировать проблему, не роняя приложение.

Использование::

    from utils_logger import log_except
    try:
        ...
    except Exception as e:
        log_except("home_page: загрузка виджета", e)

или короче (для блока except)::

    try:
        ...
    except Exception:
        log_except("home_page: загрузка виджета")
"""

import logging
import os
import traceback

from config import DATA_DIR

LOG_DIR = os.path.join(DATA_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "kanzler.log")

_logger = None


def get_logger() -> logging.Logger:
    """Ленивая инициализация логгера (пишет в файл и в stderr)."""
    global _logger
    if _logger is not None:
        return _logger
    _logger = logging.getLogger("kanzler")
    _logger.setLevel(logging.INFO)
    if not _logger.handlers:
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s"))
            _logger.addHandler(fh)
        except OSError:
            # если каталог логов недоступен — пишем хотя бы в консоль
            pass
        sh = logging.StreamHandler()
        sh.setLevel(logging.ERROR)
        sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        _logger.addHandler(sh)
    return _logger


def log_error(context: str, exc: BaseException | None = None):
    """Логирует ошибку с трейсбеком. `context` — что делали (модуль/действие)."""
    if exc is not None:
        get_logger().error("%s: %s\n%s", context, exc,
                          "".join(traceback.format_exception(exc)).rstrip())
    else:
        get_logger().error("%s\n%s", context,
                          traceback.format_exc().rstrip())


def log_except(context: str):
    """Вызывается из блока except; сам достаёт текущее исключение."""
    import sys
    exc = sys.exc_info()[1]
    log_error(context, exc)
