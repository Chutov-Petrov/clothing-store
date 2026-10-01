"""
Админка: товары, заказы, отзывы, промокоды, журнал входов.

Blueprint admin_bp — все роуты с префиксом /admin.
"""
import os
import sqlite3
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash)

from constants import CATS, TAGS, STATUSES, MAX_GALLERY
from db import db
from helpers import gallery, main_image, save_image
from security import admin_required, log_login

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "static", "uploads")


# ============================================================
# Вход / выход (редиректы)
# ============================================================
@admin_bp.route("/login")
def login():
    return redirect(url_for("auth.account_login"))


@admin_bp.post("/logout")
def logout():
    log_login("admin", "admin_logout", True)
    session.pop("admin", None)
    flash("Вы вышли из админки")
    return redirect(url_for("catalog.shop"))


# ============================================================
# Товары
# ============================================================
@admin_bp.route("")
@admin_required
def admin():
    con = db()
    stats = dict(
        products=con.execute("select count(*) from products").fetchone()[0],
        orders=con.execute("select count(*) from orders").fetchone()[0],
        revenue=con.execute("select coalesce(sum(total),0) from orders").fetchone()[0],
        new=con.execute("select count(*) from orders where status='Новый'").fetchone()[0])

    edit = None
    edit_gallery = []
    if request.args.get("edit"):
        edit = con.execute("select * from products where id=?",
                           (request.args["edit"],)).fetchone()
        if edit:
            edit_gallery = gallery(edit["id"])
    elif "new" in request.args:
        edit = dict(id="", name="", cat=CATS[0], price="", color="#DCE4FF",
                    sizes="S,M,L", stock=0, tag="", material="", care="", image="")

    products = []
    for p in con.execute("select * from products order by id desc").fetchall():
        d = dict(p); d["main_image"] = main_image(p); products.append(d)

    return render_template("admin.html", tab="products", stats=stats, edit=edit,
                           edit_gallery=edit_gallery, products=products)


@admin_bp.post("/product")
@admin_required
def product_save():
    f = request.form
    try:
        price = int(f["price"])
    except (ValueError, KeyError):
        price = 0
    try:
        stock = int(f.get("stock") or 0)
    except ValueError:
        stock = 0

    name = f.get("name", "").strip()
    cat = f.get("cat")
    color = f.get("color", "#DCE4FF")
    sizes = f.get("sizes", "").strip()
    tag = f.get("tag", "")
    if tag not in TAGS:
        tag = ""
    material = f.get("material", "").strip()
    care = f.get("care", "").strip()

    if not name or cat not in CATS or price <= 0 or not sizes:
        flash("Заполните название, категорию, цену и размеры")
        return redirect(url_for("admin.admin", new=1))

    con = db()
    pid = f.get("id")
    if pid:
        con.execute("""update products set name=?,cat=?,price=?,color=?,sizes=?,
                       stock=?,tag=?,material=?,care=? where id=?""",
                    (name, cat, price, color, sizes, stock, tag, material, care, pid))
    else:
        pid = con.execute("""insert into products(name,cat,price,color,sizes,
                             stock,tag,material,care) values(?,?,?,?,?,?,?,?,?)""",
                          (name, cat, price, color, sizes, stock, tag, material, care)).lastrowid

    files = request.files.getlist("images")
    pos = con.execute(
        "select coalesce(max(position),-1)+1 from product_images where product_id=?",
        (pid,)).fetchone()[0]
    saved = 0
    for file in files:
        if not file or not file.filename:
            continue
        if len(gallery(pid)) >= MAX_GALLERY or saved >= MAX_GALLERY:
            break
        img = save_image(file)
        if img:
            con.execute("insert into product_images(product_id, filename, position) "
                        "values(?,?,?)", (pid, img, pos))
            pos += 1
            saved += 1
    con.commit()
    flash("Товар сохранён")
    return redirect(url_for("admin.admin", edit=pid))


@admin_bp.post("/product/<int:pid>/delete")
@admin_required
def product_delete(pid):
    con = db()
    row = con.execute("select image from products where id=?", (pid,)).fetchone()
    if row and row["image"]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, row["image"]))
        except OSError:
            pass
    for r in con.execute("select filename from product_images where product_id=?", (pid,)):
        try:
            os.remove(os.path.join(UPLOAD_DIR, r["filename"]))
        except OSError:
            pass
    con.execute("delete from product_images where product_id=?", (pid,))
    con.execute("delete from reviews where product_id=?", (pid,))
    con.execute("delete from wishlist where product_id=?", (pid,))
    con.execute("delete from products where id=?", (pid,))
    con.commit()
    flash("Товар удалён")
    return redirect(url_for("admin.admin"))


@admin_bp.post("/product/<int:pid>/image/<int:img_id>/delete")
@admin_required
def product_image_delete(pid, img_id):
    con = db()
    row = con.execute(
        "select filename from product_images where id=? and product_id=?",
        (img_id, pid)).fetchone()
    if row:
        try:
            os.remove(os.path.join(UPLOAD_DIR, row["filename"]))
        except OSError:
            pass
        con.execute("delete from product_images where id=?", (img_id,))
        con.commit()
        flash("Фото удалено")
    return redirect(url_for("admin.admin", edit=pid))


# ============================================================
# Заказы
# ============================================================
@admin_bp.route("/orders")
@admin_required
def admin_orders():
    con = db()
    orders = con.execute("""
        select o.*, u.email as user_email
        from orders o left join users u on u.id = o.user_id
        order by o.id desc
    """).fetchall()
    items = {}
    for r in con.execute("select * from order_items"):
        items.setdefault(r["order_id"], []).append(r)
    return render_template("admin.html", tab="orders", orders=orders,
                           items=items, stats=None)


@admin_bp.post("/orders/<int:oid>/status")
@admin_required
def order_status(oid):
    s = request.form.get("status")
    if s in STATUSES:
        db().execute("update orders set status=? where id=?", (s, oid))
        db().commit()
        flash("Статус обновлён")
    return redirect(url_for("admin.admin_orders"))


# ============================================================
# Отзывы
# ============================================================
@admin_bp.route("/reviews")
@admin_required
def admin_reviews():
    con = db()
    reviews = con.execute("""
        select r.*, u.name as user_name, u.email as user_email,
               p.name as product_name, p.id as product_id
        from reviews r
        left join users u on u.id = r.user_id
        left join products p on p.id = r.product_id
        order by r.id desc
    """).fetchall()
    return render_template("admin.html", tab="reviews", reviews=reviews, stats=None)


@admin_bp.post("/review/<int:rid>/delete")
@admin_required
def review_delete(rid):
    db().execute("delete from reviews where id=?", (rid,))
    db().commit()
    flash("Отзыв удалён")
    return redirect(url_for("admin.admin_reviews"))


# ============================================================
# Промокоды
# ============================================================
@admin_bp.route("/promos")
@admin_required
def admin_promos():
    con = db()
    promos = con.execute("select * from promocodes order by id desc").fetchall()
    return render_template("admin.html", tab="promos", promos=promos, stats=None)


@admin_bp.post("/promo")
@admin_required
def promo_save():
    f = request.form
    code = f.get("code", "").strip().upper()
    try:
        percent = int(f.get("percent") or 0)
    except ValueError:
        percent = 0
    try:
        fixed = int(f.get("fixed") or 0)
    except ValueError:
        fixed = 0
    try:
        min_sum = int(f.get("min_sum") or 0)
    except ValueError:
        min_sum = 0
    try:
        max_uses = int(f.get("max_uses") or 0)
    except ValueError:
        max_uses = 0

    if not code:
        flash("Введите код промокода")
        return redirect(url_for("admin.admin_promos"))
    if percent == 0 and fixed == 0:
        flash("Укажите скидку — процент или фикс. сумму")
        return redirect(url_for("admin.admin_promos"))

    con = db()
    try:
        con.execute("""insert into promocodes(code, discount_percent, discount_fixed,
                       min_sum, max_uses) values(?,?,?,?,?)""",
                    (code, percent, fixed, min_sum, max_uses))
        con.commit()
        flash(f"Промокод {code} создан")
    except sqlite3.IntegrityError:
        flash("Такой код уже существует")
    return redirect(url_for("admin.admin_promos"))


@admin_bp.post("/promo/<int:pid>/toggle")
@admin_required
def promo_toggle(pid):
    con = db()
    row = con.execute("select active from promocodes where id=?", (pid,)).fetchone()
    if row:
        con.execute("update promocodes set active=? where id=?",
                    (0 if row["active"] else 1, pid))
        con.commit()
        flash("Статус промокода изменён")
    return redirect(url_for("admin.admin_promos"))


@admin_bp.post("/promo/<int:pid>/delete")
@admin_required
def promo_delete(pid):
    db().execute("delete from promocodes where id=?", (pid,))
    db().commit()
    flash("Промокод удалён")
    return redirect(url_for("admin.admin_promos"))


# ============================================================
# Журнал входов
# ============================================================
@admin_bp.route("/logins")
@admin_required
def admin_logins():
    con = db()
    logs = con.execute("select * from login_log order by id desc limit 300").fetchall()
    return render_template("admin.html", tab="logins", logs=logs, stats=None)