"""
Работа с базой данных SQLite.

Все обращения к БД идут через функцию db() — она возвращает
соединение с включёнными внешними ключами и Row-фабрикой.
"""
import os
import sqlite3
from flask import g

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shop.db")


def db():
    """Возвращает соединение с БД для текущего запроса."""
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    """Закрывает соединение при завершении запроса."""
    con = g.pop("db", None)
    if con:
        con.close()


def init_db():
    """Создаёт таблицы и добавляет начальные данные."""
    from constants import SEED

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript("""
    create table if not exists products(
        id integer primary key autoincrement, name text not null,
        cat text not null, price integer not null,
        color text not null default '#DCE4FF', sizes text not null);
    create table if not exists orders(
        id integer primary key autoincrement, created text default current_timestamp,
        name text, phone text, total integer, status text default 'Новый');
    create table if not exists order_items(
        order_id integer, name text, size text, qty integer, price integer);
    create table if not exists users(
        id integer primary key autoincrement,
        email text unique not null,
        password_hash text not null,
        name text not null default '',
        phone text not null default '',
        created text default current_timestamp);
    create table if not exists product_images(
        id integer primary key autoincrement,
        product_id integer not null,
        filename text not null,
        position integer default 0);
    create table if not exists reviews(
        id integer primary key autoincrement,
        product_id integer not null,
        user_id integer not null,
        rating integer not null,
        text text not null default '',
        created text default current_timestamp,
        unique(product_id, user_id));
    create table if not exists wishlist(
        id integer primary key autoincrement,
        user_id integer not null,
        product_id integer not null,
        created text default current_timestamp,
        unique(user_id, product_id));
    create table if not exists login_attempts(
        id integer primary key autoincrement,
        ip text not null,
        email text not null,
        attempt_at text default current_timestamp);
    create table if not exists login_log(
        id integer primary key autoincrement,
        ip text not null,
        login text not null,
        role text not null default 'customer',
        success integer not null default 0,
        user_agent text not null default '',
        created text default current_timestamp);
    create table if not exists promocodes(
        id integer primary key autoincrement,
        code text unique not null,
        discount_percent integer not null default 0,
        discount_fixed integer not null default 0,
        min_sum integer not null default 0,
        max_uses integer not null default 0,
        used_count integer not null default 0,
        active integer not null default 1,
        created text default current_timestamp);
    """)
    cols = {r[1] for r in con.execute("pragma table_info(orders)")}
    if "user_id" not in cols:
        con.execute("alter table orders add column user_id integer")
    if "promo_code" not in cols:
        con.execute("alter table orders add column promo_code text not null default ''")
    if "discount" not in cols:
        con.execute("alter table orders add column discount integer not null default 0")
    pcols = {r[1] for r in con.execute("pragma table_info(products)")}
    if "image" not in pcols:
        con.execute("alter table products add column image text not null default ''")
    if "stock" not in pcols:
        con.execute("alter table products add column stock integer not null default 0")
    if "tag" not in pcols:
        con.execute("alter table products add column tag text not null default ''")
    if "material" not in pcols:
        con.execute("alter table products add column material text not null default ''")
    if "care" not in pcols:
        con.execute("alter table products add column care text not null default ''")

    existing_names = {r[0] for r in con.execute("select name from products")}
    new_rows = [row for row in SEED if row[0] not in existing_names]
    if new_rows:
        con.executemany(
            "insert into products(name,cat,price,color,sizes,image,stock,tag,material,care) "
            "values(?,?,?,?,?,?,?,?,?,?)", new_rows)
        print(f"➕ Добавлено товаров: {len(new_rows)}")

    if not con.execute("select count(*) from promocodes").fetchone()[0]:
        con.executemany(
            "insert into promocodes(code, discount_percent, discount_fixed, min_sum, max_uses) "
            "values(?,?,?,?,?)", [
            ("WELCOME10", 10, 0, 0, 0),
            ("SALE500",   0, 500, 3000, 100),
            ("VIP20",     20, 0, 10000, 20),
        ])
    con.commit()
    con.close()