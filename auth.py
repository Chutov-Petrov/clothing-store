"""
Аутентификация: регистрация, вход, выход, личный кабинет.

Blueprint auth_bp — все роуты, связанные с пользователями.
"""
import re
import secrets
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash)

from config import ADMIN_PASSWORD
from db import db
from helpers import current_user
from security import (hash_password, verify_password,
                      check_login_rate, register_login_attempt,
                      reset_login_attempts, log_login)

auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ============================================================
# Регистрация
# ============================================================
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("auth.profile"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()

        if not EMAIL_RE.match(email):
            flash("Некорректный email")
        elif len(password) < 8:
            flash("Пароль должен быть не короче 8 символов")
        elif not re.search(r"[A-Z]", password):
            flash("Пароль должен содержать заглавную букву")
        elif not re.search(r"[a-z]", password):
            flash("Пароль должен содержать строчную букву")
        elif not re.search(r"\d", password):
            flash("Пароль должен содержать цифру")
        elif password != password2:
            flash("Пароли не совпадают")
        elif not name:
            flash("Укажите имя")
        elif db().execute("select 1 from users where email=?", (email,)).fetchone():
            flash("Email занят")
        else:
            con = db()
            uid = con.execute(
                "insert into users(email,password_hash,name,phone) values(?,?,?,?)",
                (email, hash_password(password), name, phone)).lastrowid
            con.commit()
            session["uid"] = uid
            flash("Добро пожаловать!")
            return redirect(url_for("auth.profile"))

    return render_template("register.html")


# ============================================================
# Вход (админ + покупатель)
# ============================================================
@auth_bp.route("/login", methods=["GET", "POST"])
def account_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        ip = request.remote_addr or "unknown"

        if not check_login_rate(ip, email):
            log_login(email, "blocked", False)
            flash(f"Слишком много попыток. Попробуйте через 15 минут.")
            return render_template("account_login.html"), 429

        # Вход админа
        if email in ("админ", "admin"):
            if secrets.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
                reset_login_attempts(ip, email)
                log_login(email, "admin", True)
                session["admin"] = True
                flash("Добро пожаловать, администратор!")
                return redirect(url_for("admin.admin"))
            register_login_attempt(ip, email)
            log_login(email, "admin", False)
            flash("Неверный пароль администратора")
            return render_template("account_login.html"), 401

        # Вход покупателя
        row = db().execute("select * from users where email=?", (email,)).fetchone()
        if row and verify_password(password, row["password_hash"]):
            reset_login_attempts(ip, email)
            log_login(email, "customer", True)
            session["uid"] = row["id"]
            flash("С возвращением!")
            return redirect(url_for("auth.profile"))
        register_login_attempt(ip, email)
        log_login(email, "customer", False)
        flash("Неверный email или пароль")
        return render_template("account_login.html"), 401

    return render_template("account_login.html")


# ============================================================
# Выход
# ============================================================
@auth_bp.post("/logout")
def account_logout():
    u = current_user()
    if u:
        log_login(u["email"], "customer_logout", True)
    session.pop("uid", None)
    flash("Вы вышли")
    return redirect(url_for("catalog.shop"))


# ============================================================
# Личный кабинет
# ============================================================
@auth_bp.route("/profile", methods=["GET", "POST"])
def profile():
    u = current_user()
    if not u:
        return redirect(url_for("auth.account_login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        if not name:
            flash("Имя не может быть пустым")
        else:
            con = db()
            con.execute("update users set name=?, phone=? where id=?",
                        (name, phone, u["id"]))
            con.commit()
            flash("Данные сохранены")
            return redirect(url_for("auth.profile"))

    orders = db().execute(
        "select * from orders where user_id=? order by id desc",
        (u["id"],)).fetchall()
    items_by_order = {}
    if orders:
        ids = [o["id"] for o in orders]
        qs = ",".join("?" * len(ids))
        for r in db().execute(
                f"select * from order_items where order_id in ({qs})", ids):
            items_by_order.setdefault(r["order_id"], []).append(r)

    return render_template("profile.html", orders=orders,
                           items=items_by_order)


# ============================================================
# Смена пароля
# ============================================================
@auth_bp.route("/profile/password", methods=["GET", "POST"])
def change_password():
    u = current_user()
    if not u:
        return redirect(url_for("auth.account_login"))

    if request.method == "POST":
        old = request.form.get("old", "")
        new = request.form.get("new", "")
        new2 = request.form.get("new2", "")

        if not verify_password(old, u["password_hash"]):
            flash("Текущий пароль неверный")
        elif len(new) < 8:
            flash("Новый пароль должен быть не короче 8 символов")
        elif not re.search(r"[A-Z]", new):
            flash("Пароль должен содержать заглавную букву")
        elif not re.search(r"[a-z]", new):
            flash("Пароль должен содержать строчную букву")
        elif not re.search(r"\d", new):
            flash("Пароль должен содержать цифру")
        elif new != new2:
            flash("Новые пароли не совпадают")
        elif new == old:
            flash("Новый должен отличаться от текущего")
        else:
            con = db()
            con.execute("update users set password_hash=? where id=?",
                        (hash_password(new), u["id"]))
            con.commit()
            flash("Пароль изменён")
            return redirect(url_for("auth.profile"))

    return render_template("change_password.html")
    

# ============================================================
# Детали заказа
# ============================================================
@auth_bp.route("/profile/order/<int:oid>")
def order_detail(oid):
    """Страница одного заказа — доступна только владельцу."""
    u = current_user()
    if not u:
        return redirect(url_for("auth.account_login"))

    # Важно: фильтр по user_id — чужой заказ получить нельзя
    order = db().execute(
        "select * from orders where id=? and user_id=?",
        (oid, u["id"])).fetchone()

    if not order:
        from flask import abort
        abort(404)

    items = db().execute(
        "select * from order_items where order_id=?", (oid,)).fetchall()

    return render_template("order.html", order=order, items=items)


@auth_bp.post("/profile/order/<int:oid>/repeat")
def order_repeat(oid):
    """Копирует товары из прошлого заказа обратно в корзину."""
    u = current_user()
    if not u:
        return redirect(url_for("auth.account_login"))

    order = db().execute(
        "select * from orders where id=? and user_id=?",
        (oid, u["id"])).fetchone()
    if not order:
        from flask import abort
        abort(404)

    # Забираем позиции заказа
    rows = db().execute(
        "select name, size, qty from order_items where order_id=?",
        (oid,)).fetchall()

    cart = session.get("cart", {})
    added = 0
    for row in rows:
        # Ищем товар по имени (простой матч — имена уникальны в SEED)
        p = db().execute(
            "select * from products where name=? and stock > 0",
            (row["name"],)).fetchone()
        if not p:
            continue
        size = row["size"]
        # Проверяем, что размер актуален для товара
        if size not in p["sizes"].split(","):
            continue
        key = f"{p['id']}:{size}"
        # Не превышаем остаток
        new_qty = min(cart.get(key, 0) + row["qty"], p["stock"])
        cart[key] = new_qty
        added += 1

    session["cart"] = cart

    if added:
        flash(f"Добавлено товаров в корзину: {added}")
    else:
        flash("Товары из этого заказа больше недоступны")
    return redirect(url_for("cart.cart"))