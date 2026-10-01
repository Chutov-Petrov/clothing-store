"""
Хэлперы: работа с товарами, промокодами, корзиной, изображениями.

Функции-обогатители (enrich), расчёт скидок, сохранение файлов.
"""
import os
import secrets
from flask import session

from db import db
from constants import ALLOWED_EXT

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "static", "uploads")

# ---------- Пользователь ----------
def current_user():
    """Возвращает текущего покупателя или None."""
    uid = session.get("uid")
    if not uid:
        return None
    return db().execute("select * from users where id=?", (uid,)).fetchone()


# ---------- Изображения ----------
def is_image(data: bytes) -> bool:
    """Проверяет magic bytes: PNG/JPEG/WEBP."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return False


def save_image(file) -> str:
    """Сохраняет загруженный файл со случайным именем. Возвращает имя или ''."""
    if not file or not file.filename:
        return ""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return ""
    head = file.stream.read(32)
    file.stream.seek(0)
    if not is_image(head):
        return ""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = f"{secrets.token_hex(16)}{ext}"
    file.save(os.path.join(UPLOAD_DIR, name))
    return name


# ---------- Товары ----------
def gallery(pid: int):
    """Все фото товара (для галереи)."""
    return db().execute(
        "select * from product_images where product_id=? order by position, id",
        (pid,)).fetchall()


def main_image(p) -> str:
    """Имя главного фото товара."""
    if p["image"]:
        return p["image"]
    row = db().execute(
        "select filename from product_images where product_id=? "
        "order by position, id limit 1", (p["id"],)).fetchone()
    return row["filename"] if row else ""


def product_stats(pid: int) -> dict:
    """Средний рейтинг и число отзывов."""
    r = db().execute(
        "select coalesce(avg(rating),0) as avg, count(*) as cnt "
        "from reviews where product_id=?", (pid,)).fetchone()
    return {"avg": r["avg"], "cnt": r["cnt"]}


def in_wishlist(pid: int) -> bool:
    """Есть ли товар в избранном у текущего пользователя."""
    if not session.get("uid"):
        return False
    return db().execute(
        "select 1 from wishlist where user_id=? and product_id=?",
        (session["uid"], pid)).fetchone() is not None


def wishlist_count() -> int:
    """Число товаров в избранном."""
    if not session.get("uid"):
        return 0
    r = db().execute("select count(*) from wishlist where user_id=?",
                     (session["uid"],)).fetchone()
    return r[0] if r else 0


def enrich(rows) -> list:
    """Обогащает список товаров: главное фото, рейтинг, признак избранного."""
    result = []
    for p in rows:
        d = dict(p)
        d["main_image"] = main_image(p)
        st = product_stats(p["id"])
        d["avg_rating"], d["review_count"] = st["avg"], st["cnt"]
        d["in_wishlist"] = in_wishlist(p["id"])
        result.append(d)
    return result


# ---------- Промокоды ----------
def get_promo_by_code(code: str):
    """Активный промокод по коду или None."""
    if not code:
        return None
    code = code.strip().upper()
    return db().execute(
        "select * from promocodes where code=? and active=1", (code,)).fetchone()


def calc_discount(promo, total: int) -> int:
    """Размер скидки в рублях. 0 — если промокод не подходит."""
    if not promo:
        return 0
    if promo["min_sum"] and total < promo["min_sum"]:
        return 0
    if promo["max_uses"] and promo["used_count"] >= promo["max_uses"]:
        return 0
    discount = 0
    if promo["discount_percent"]:
        discount += total * promo["discount_percent"] // 100
    if promo["discount_fixed"]:
        discount += promo["discount_fixed"]
    return min(discount, total)


def current_promo():
    """Промокод, применённый в текущей сессии."""
    code = session.get("promo")
    if not code:
        return None
    return get_promo_by_code(code)


# ---------- Корзина ----------
def cart_totals():
    """
    Возвращает (items, subtotal, discount, total, promo).

    items   — список dict(key, p, size, qty, img)
    subtotal — сумма без скидки
    discount — размер скидки
    total   — итог к оплате
    promo   — применённый промокод или None
    """
    items, subtotal = [], 0
    for key, qty in session.get("cart", {}).items():
        pid, size = key.split(":", 1)
        p = db().execute("select * from products where id=?", (pid,)).fetchone()
        if p:
            items.append(dict(key=key, p=p, size=size, qty=qty,
                              img=main_image(p)))
            subtotal += p["price"] * qty
    promo = current_promo()
    discount = calc_discount(promo, subtotal)
    total = subtotal - discount
    return items, subtotal, discount, total, promo