"""
Корзина, промокоды, оформление заказа.

Blueprint cart_bp.
"""
import sqlite3
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, abort)

from db import db
from helpers import (cart_totals, get_promo_by_code, main_image)

cart_bp = Blueprint("cart", __name__)


# ============================================================
# Добавить товар в корзину
# ============================================================
@cart_bp.post("/cart/add")
def add_to_cart():
    pid, size = request.form.get("id", ""), request.form.get("size", "")
    p = db().execute("select * from products where id=?", (pid,)).fetchone()
    if not p or size not in p["sizes"].split(","):
        abort(400)
    if p["stock"] is not None and p["stock"] <= 0:
        flash("Товара нет в наличии")
        return redirect(request.referrer or url_for("catalog.shop"))

    cart = session.get("cart", {})
    key = f"{pid}:{size}"
    new_qty = cart.get(key, 0) + 1
    if p["stock"] and new_qty > p["stock"]:
        flash(f"На складе только {p['stock']} шт.")
        return redirect(request.referrer or url_for("catalog.shop"))

    cart[key] = new_qty
    session["cart"] = cart
    flash("Добавлено в корзину")
    return redirect(request.referrer or url_for("catalog.shop"))


# ============================================================
# Показать корзину
# ============================================================
@cart_bp.route("/cart")
def cart():
    items, subtotal, discount, total, promo = cart_totals()
    return render_template("cart.html", items=items, subtotal=subtotal,
                           discount=discount, total=total, promo=promo)


# ============================================================
# Применить промокод
# ============================================================
@cart_bp.post("/cart/promo")
def apply_promo():
    code = request.form.get("code", "").strip().upper()
    if not code:
        session.pop("promo", None)
        flash("Промокод удалён")
        return redirect(url_for("cart.cart"))

    promo = get_promo_by_code(code)
    if not promo:
        flash("Промокод не найден")
        return redirect(url_for("cart.cart"))

    items, subtotal = [], 0
    for key, qty in session.get("cart", {}).items():
        pid = key.split(":", 1)[0]
        p = db().execute("select price from products where id=?",
                         (pid,)).fetchone()
        if p:
            subtotal += p["price"] * qty

    if promo["min_sum"] and subtotal < promo["min_sum"]:
        flash(f"Минимальная сумма для этого промокода — {promo['min_sum']} ₽")
        return redirect(url_for("cart.cart"))
    if promo["max_uses"] and promo["used_count"] >= promo["max_uses"]:
        flash("Промокод больше не действует")
        return redirect(url_for("cart.cart"))

    session["promo"] = promo["code"]
    flash(f"Промокод {promo['code']} применён")
    return redirect(url_for("cart.cart"))


# ============================================================
# Убрать промокод
# ============================================================
@cart_bp.post("/cart/promo/clear")
def clear_promo():
    session.pop("promo", None)
    flash("Промокод удалён")
    return redirect(url_for("cart.cart"))


# ============================================================
# Изменить количество (+ / -)
# ============================================================
@cart_bp.post("/cart/change")
def change_qty():
    cart = session.get("cart", {})
    key = request.form.get("key", "")
    if key not in cart:
        return redirect(url_for("cart.cart"))

    pid = key.split(":", 1)[0]
    p = db().execute("select stock from products where id=?",
                     (pid,)).fetchone()
    limit = p["stock"] if p else None

    if request.form.get("d") == "+":
        if limit and cart[key] + 1 > limit:
            flash(f"Больше {limit} шт. нет в наличии")
        else:
            cart[key] += 1
    else:
        cart[key] -= 1
        if cart[key] < 1:
            del cart[key]

    session["cart"] = cart
    return redirect(url_for("cart.cart"))


# ============================================================
# Удалить товар из корзины
# ============================================================
@cart_bp.post("/cart/remove")
def remove_item():
    key = request.form.get("key", "")
    cart = session.get("cart", {})
    cart.pop(key, None)
    session["cart"] = cart
    flash("Товар удалён")
    return redirect(url_for("cart.cart"))


# ============================================================
# Очистить корзину
# ============================================================
@cart_bp.post("/cart/clear")
def clear_cart():
    session.pop("cart", None)
    session.pop("promo", None)
    flash("Корзина очищена")
    return redirect(url_for("cart.cart"))


# ============================================================
# Оформить заказ (транзакция)
# ============================================================
@cart_bp.post("/cart/checkout")
def checkout():
    items, subtotal, discount, total, promo = cart_totals()
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    if not items or not name or sum(c.isdigit() for c in phone) < 6:
        flash("Укажите имя и телефон")
        return redirect(url_for("cart.cart"))

    con = db()
    try:
        con.execute("BEGIN IMMEDIATE")

        # Перепроверяем остатки внутри транзакции
        for i in items:
            p = con.execute(
                "select stock, name from products where id=?",
                (i["p"]["id"],)).fetchone()
            if p and p["stock"] is not None and p["stock"] < i["qty"]:
                con.execute("ROLLBACK")
                flash(f"«{p['name']}» — на складе только {p['stock']} шт.")
                return redirect(url_for("cart.cart"))

        uid = session.get("uid")
        promo_code = promo["code"] if promo else ""
        oid = con.execute(
            "insert into orders(name,phone,total,user_id,promo_code,discount) "
            "values(?,?,?,?,?,?)",
            (name, phone, total, uid, promo_code, discount)).lastrowid

        for i in items:
            con.execute("insert into order_items values(?,?,?,?,?)",
                        (oid, i["p"]["name"], i["size"], i["qty"], i["p"]["price"]))
            con.execute("update products set stock = stock - ? where id=?",
                        (i["qty"], i["p"]["id"]))

        if promo:
            con.execute("update promocodes set used_count = used_count + 1 "
                        "where id=?", (promo["id"],))

        con.execute("COMMIT")
    except sqlite3.OperationalError:
        con.execute("ROLLBACK")
        flash("Не удалось оформить заказ. Попробуйте ещё раз.")
        return redirect(url_for("cart.cart"))

    session.pop("cart", None)
    session.pop("promo", None)
    flash(f"Заказ №{oid} оформлен. Мы позвоним вам")
    return redirect(url_for("catalog.shop"))