"""
Безопасность: пароли, CSRF, rate limit, разграничение доступа.

- hash_password / verify_password — PBKDF2-HMAC-SHA256, 200_000 итераций
- check_csrf — глобальная проверка CSRF-токена для всех POST
- check_login_rate / register_login_attempt / reset_login_attempts — защита от брутфорса
- log_login — журнал всех попыток входа
- admin_required — декоратор для роутов админки
"""
import hashlib
import hmac
import secrets
from functools import wraps
from flask import request, session, redirect, url_for, abort

PBKDF2_ITERATIONS = 200_000
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_MIN = 15


# ---------- Пароли ----------
def hash_password(pw: str) -> str:
    """Возвращает PBKDF2-хеш пароля с уникальной солью."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    """Проверяет пароль против хеша (сравнение константное по времени)."""
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", pw.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ---------- CSRF ----------
def check_csrf() -> None:
    """Проверяет CSRF-токен для всех POST-запросов."""
    if request.method == "POST":
        token = request.headers.get("X-CSRFToken") or request.form.get("csrf", "")
        expected = session.get("csrf")
        if not expected or not secrets.compare_digest(expected, token):
            abort(400)


# ---------- Rate limit на вход ----------
def check_login_rate(ip: str, email: str) -> bool:
    """True — можно пробовать, False — заблокирован."""
    from db import db as _db
    con = _db()
    con.execute(
        "delete from login_attempts where attempt_at < datetime('now', ?)",
        (f"-{RATE_LIMIT_WINDOW_MIN} minutes",))
    con.commit()
    row = con.execute(
        "select count(*) as cnt from login_attempts where ip=? and email=?",
        (ip, email)).fetchone()
    return row["cnt"] < RATE_LIMIT_MAX


def register_login_attempt(ip: str, email: str) -> None:
    """Записывает неудачную попытку входа."""
    from db import db as _db
    con = _db()
    con.execute("insert into login_attempts(ip, email) values(?, ?)", (ip, email))
    con.commit()


def reset_login_attempts(ip: str, email: str) -> None:
    """Очищает счётчик неудачных попыток после успешного входа."""
    from db import db as _db
    con = _db()
    con.execute("delete from login_attempts where ip=? and email=?", (ip, email))
    con.commit()


# ---------- Журнал входов ----------
def log_login(login: str, role: str, success: bool) -> None:
    """Пишет попытку входа в журнал (успех/отказ/блокировка/выход)."""
    from db import db as _db
    con = _db()
    con.execute(
        "insert into login_log(ip, login, role, success, user_agent) values(?,?,?,?,?)",
        (request.remote_addr or "unknown", login[:120], role,
         1 if success else 0, request.headers.get("User-Agent", "")[:200]))
    con.commit()


# ---------- Доступ ----------
def admin_required(f):
    """Декоратор: пускает только админа, иначе редирект на /login."""
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("auth.account_login"))
        return f(*a, **kw)
    return wrapper