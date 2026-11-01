# Вклад в проект

## Локальный запуск
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python main.py            # запуск приложения (Flet)
python -m pytest -q       # тесты слоя БД/безопасности
```

## Правила
- Переменные окружения: `KANZLER_DB` (путь к БД), `KANZLER_DATA_DIR`,
  `KANZLER_ADMIN_PASSWORD` (пароль админа при первой инициализации).
- Секреты (пароли, токены) запрещены в коде и истории git.
- Перед коммитом прогоните `python -m pytest -q`.
- Хуки: `pip install pre-commit && pre-commit install` — ruff и compileall
  автоматически перед каждым коммитом (конфиг `.pre-commit-config.yaml`).
- Новые SQL-запросы — только параметризованные (`?`), без f-строк со значениями.
