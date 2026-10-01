"""
Избранное: список, добавление/удаление (AJAX).

Blueprint wishlist_bp.
"""
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, jsonify)

from db import db
from helpers import enrich, wishlist_count

wishlist_bp = Blueprint("wishlist", __name__)


# ============================================================
# Страница избранного
# ============================================================
@wishlist_bp.route("/wishlist")
def wishlist():
    if not session.get("uid"):
        flash("Войдите, чтобы посмотреть избранное")
        return redirect(url_for("auth.account_login"))

    rows = db().execute("""
        select p.* from wishlist w
        join products p on p.id = w.product_id
        where w.user_id=? order by w.id desc
    """, (session["uid"],)).fetchall()

    products = enrich(rows)
    for p in products:
        p["in_wishlist"] = True

    return render_template("wishlist.html", products=products)


# ============================================================
# Переключить избранное (AJAX)
# ============================================================
@wishlist_bp.post("/wishlist/toggle/<int:pid>")
def toggle(pid):
    if not session.get("uid"):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "login": True}), 401
        flash("Войдите, чтобы добавить в избранное")
        return redirect(url_for("auth.account_login"))

    p = db().execute("select id from products where id=?", (pid,)).fetchone()
    if not p:
        abort_404()

    con = db()
    exists = con.execute(
        "select 1 from wishlist where user_id=? and product_id=?",
        (session["uid"], pid)).fetchone()

    if exists:
        con.execute("delete from wishlist where user_id=? and product_id=?",
                    (session["uid"], pid))
        added = False
    else:
        con.execute("insert into wishlist(user_id, product_id) values(?,?)",
                    (session["uid"], pid))
        added = True
    con.commit()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "added": added,
                        "count": wishlist_count()})

    flash("Добавлено в избранное" if added else "Удалено из избранного")
    return redirect(request.referrer or url_for("catalog.shop"))


def abort_404():
    from flask import abort
    abort(404)