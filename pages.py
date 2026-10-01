"""
Статические страницы: О нас, Доставка, Оплата, Контакты.

Blueprint pages_bp.
"""
from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/about")
def about():
    return render_template("about.html")


@pages_bp.route("/delivery")
def delivery():
    return render_template("delivery.html")


@pages_bp.route("/payment")
def payment():
    return render_template("payment.html")


@pages_bp.route("/contacts")
def contacts():
    return render_template("contacts.html")