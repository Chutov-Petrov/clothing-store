"""
Общие фикстуры для тестов.

Каждый тест получает:
- изолированную временную БД (файл во временной папке)
- тестовый клиент Flask
- предустановленный CSRF-токен в сессии
"""
import os
import sys
import tempfile
import pytest

# Добавляем корень проекта в sys.path — чтобы import app сработал
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import db as db_module  # noqa: E402
from app import app as flask_app  # noqa: E402


@pytest.fixture
def client():
    """Тестовый клиент с временной БД и CSRF-токеном."""
    fd, temp_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Переключаем БД на временный файл
    old_db = db_module.DB
    db_module.DB = temp_db

    # Создаём таблицы + SEED
    db_module.init_db()

    flask_app.config["TESTING"] = True

    with flask_app.test_client() as c:
        with c.session_transaction() as sess:
            sess["csrf"] = "test-csrf-token"
        yield c

    # Восстанавливаем оригинальную БД
    db_module.DB = old_db
    try:
        os.unlink(temp_db)
    except OSError:
        pass


@pytest.fixture
def csrf_token():
    return "test-csrf-token"