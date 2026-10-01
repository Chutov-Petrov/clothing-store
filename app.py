"""
Точка входа приложения «Ткань» — интернет-магазин одежды.

Реализован паттерн Application Factory: create_app() создаёт Flask-приложение,
подключает расширения, регистрирует Blueprints и обработчики ошибок.

Модули проекта:
- constants.py  — категории, теги, SEED
- config.py     — секреты (SECRET_KEY, ADMIN_PASSWORD)
- db.py         — работа с SQLite
- security.py   — пароли, CSRF, rate limit
- helpers.py    — хэлперы для товаров, промокодов, корзины
- auth.py       — регистрация, вход, профиль
- catalog.py    — главная, каталог, товар, отзывы
- cart.py       — корзина, промокоды, checkout
- wishlist.py   — избранное
- admin.py      — админка
"""
import secrets
from flask import Flask, render_template, session

from config import SECRET_KEY
from constants import EM, CATS, TAGS, STATUSES
from db import init_db, close_db
from security import check_csrf
from helpers import current_user, wishlist_count

from auth import auth_bp
from pages import pages_bp
from catalog import catalog_bp
from cart import cart_bp
from wishlist import wishlist_bp
from admin import admin_bp


def create_app() -> Flask:
    """Создаёт и настраивает Flask-приложение."""
    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

    # Закрываем соединение с БД при завершении запроса
    app.teardown_appcontext(close_db)

    # Глобальная проверка CSRF для всех POST-запросов
    app.before_request(check_csrf)

    # Регистрация Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(wishlist_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(pages_bp)

    # Общий контекст для всех шаблонов
    @app.context_processor
    def common():
        session.setdefault("csrf", secrets.token_hex(16))
        return dict(
            csrf=session["csrf"],
            EM=EM, CATS=CATS, TAGS=TAGS, STATUSES=STATUSES,
            cart_count=sum(session.get("cart", {}).values()),
            wishlist_count=wishlist_count(),
            is_admin=session.get("admin", False),
            user=current_user(),
        )

    # Обработчики ошибок
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def too_many(e):
        return render_template("errors/429.html"), 429

    return app


# Создаём приложение на уровне модуля — для запуска и для тестов
app = create_app()

# Инициализируем БД
init_db()


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=5000)