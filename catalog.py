"""
Каталог: главная, каталог с пагинацией, карточка товара, отзывы.

Blueprint catalog_bp.
"""
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, abort)

from db import db
from helpers import (enrich, gallery, main_image, product_stats,
                     in_wishlist, cart_totals)

catalog_bp = Blueprint("catalog", __name__)

CATS = ["Футболки", "Верхняя одежда", "Брюки", "Платья"]
PER_PAGE = 12


# ============================================================
# Главная
# ============================================================
@catalog_bp.route("/")
def home():
    con = db()
    cat_counts = {}
    for c in CATS:
        cnt = con.execute(
            "select count(*) from products where cat=? and stock > 0",
            (c,)).fetchone()[0]
        cat_counts[c] = cnt

    hits = enrich(con.execute(
        "select * from products where tag='hit' and stock > 0 "
        "order by id desc limit 4").fetchall())
    new_items = enrich(con.execute(
        "select * from products where tag='new' and stock > 0 "
        "order by id desc limit 4").fetchall())

    return render_template("home.html", cat_counts=cat_counts,
                           hits=hits, new_items=new_items)


# ============================================================
# Каталог
# ============================================================
@catalog_bp.route("/catalog")
def shop():
    cat = request.args.get("cat", "")
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    where, args = " where 1=1", []
    if cat in CATS:
        where += " and cat=?"; args.append(cat)
    if q:
        where += " and name like ?"; args.append(f"%{q}%")

    con = db()
    total_count = con.execute(
        f"select count(*) from products{where}", args).fetchone()[0]
    total_pages = max(1, (total_count + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    offset = (page - 1) * PER_PAGE

    order = {"asc": " order by price", "desc": " order by price desc"}.get(
        sort, " order by id desc")
    rows = con.execute(
        f"select * from products{where}{order} limit ? offset ?",
        args + [PER_PAGE, offset]).fetchall()

    products = enrich(rows)

    if total_pages <= 7:
        page_numbers = list(range(1, total_pages + 1))
    elif page <= 4:
        page_numbers = [1, 2, 3, 4, 5, "…", total_pages]
    elif page >= total_pages - 3:
        page_numbers = [1, "…"] + list(range(total_pages - 4, total_pages + 1))
    else:
        page_numbers = [1, "…", page - 1, page, page + 1, "…", total_pages]

    return render_template("shop.html", products=products, cat=cat, q=q,
                           sort=sort, page=page, total_pages=total_pages,
                           total_count=total_count, page_numbers=page_numbers)


# ============================================================
# Карточка товара
# ============================================================
@catalog_bp.route("/product/<int:pid>")
def product(pid):
    p = db().execute("select * from products where id=?", (pid,)).fetchone()
    if not p:
        abort(404)

    imgs = gallery(pid)
    main_img = main_image(p)
    st = product_stats(pid)
    reviews = db().execute("""
        select r.*, u.name as user_name from reviews r
        left join users u on u.id = r.user_id
        where r.product_id=? order by r.id desc
    """, (pid,)).fetchall()

    user_reviewed = False
    if session.get("uid"):
        user_reviewed = db().execute(
            "select 1 from reviews where product_id=? and user_id=?",
            (pid, session["uid"])).fetchone() is not None

    related = enrich(db().execute(
        "select * from products where cat=? and id<>? "
        "order by id desc limit 4", (p["cat"], pid)).fetchall())

    return render_template("product.html", p=p, gallery=imgs,
                           main_img=main_img, stats=st, reviews=reviews,
                           user_reviewed=user_reviewed, related=related,
                           in_wish=in_wishlist(pid))


# ============================================================
# Добавление отзыва
# ============================================================
@catalog_bp.post("/product/<int:pid>/review")
def add_review(pid):
    if not session.get("uid"):
        flash("Войдите, чтобы оставить отзыв")
        return redirect(url_for("auth.account_login"))

    p = db().execute("select id from products where id=?", (pid,)).fetchone()
    if not p:
        abort(404)

    try:
        rating = int(request.form.get("rating", ""))
    except ValueError:
        rating = 0
    if rating < 1 or rating > 5:
        flash("Оценка должна быть от 1 до 5")
        return redirect(url_for("catalog.product", pid=pid))

    text = request.form.get("text", "").strip()[:1000]
    con = db()
    if con.execute("select 1 from reviews where product_id=? and user_id=?",
                   (pid, session["uid"])).fetchone():
        flash("Вы уже оставили отзыв на этот товар")
    else:
        con.execute("insert into reviews(product_id,user_id,rating,text) "
                    "values(?,?,?,?)", (pid, session["uid"], rating, text))
        con.commit()
        flash("Спасибо за отзыв!")
    return redirect(url_for("catalog.product", pid=pid))