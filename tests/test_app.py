"""
Тесты проекта «Ткань» — проверка безопасности и бизнес-логики.

Запуск:  python -m pytest tests/ -v
"""


# ============================================================
# 1. Базовые маршруты
# ============================================================

def test_home_page_loads(client):
    """Главная страница открывается и содержит название магазина."""
    r = client.get("/")
    assert r.status_code == 200
    assert "ТКАНЬ" in r.get_data(as_text=True)


def test_catalog_page_loads(client):
    """Каталог открывается."""
    r = client.get("/catalog")
    assert r.status_code == 200


def test_product_page_loads(client):
    """Карточка товара с id=1 открывается."""
    r = client.get("/product/1")
    assert r.status_code == 200


def test_product_404_for_missing(client):
    """Несуществующий товар → 404."""
    r = client.get("/product/999999")
    assert r.status_code == 404


# ============================================================
# 2. Безопасность — SQL-инъекции, XSS, CSRF
# ============================================================

def test_sql_injection_in_search(client):
    """SQL-инъекция в поиске не должна ломать каталог."""
    r = client.get("/catalog?q=' OR 1=1--")
    assert r.status_code == 200


def test_sql_injection_in_cat_param(client):
    """Инъекция через параметр cat не должна работать."""
    r = client.get("/catalog?cat=' OR 1=1--")
    assert r.status_code == 200


def test_csrf_required_for_post(client):
    """POST без CSRF-токена → 400 (Bad Request)."""
    r = client.post("/cart/add", data={"id": "1", "size": "M"})
    assert r.status_code == 400


def test_admin_page_redirects_to_login(client):
    """Без авторизации /admin редиректит на /login."""
    r = client.get("/admin")
    assert r.status_code == 302
    assert "/login" in r.headers.get("Location", "")


def test_admin_login_wrong_password(client, csrf_token):
    """Неверный пароль админа → 401."""
    r = client.post("/login", data={
        "csrf": csrf_token,
        "email": "admin",
        "password": "wrong-password",
    })
    assert r.status_code == 401


# ============================================================
# 3. Пароли — хеширование и валидация
# ============================================================

def test_password_hashing_not_plain():
    """Пароль в БД хранится в виде PBKDF2-хеша, не в открытом виде."""
    from security import hash_password, verify_password
    hashed = hash_password("MySecret123")
    assert hashed != "MySecret123"
    assert hashed.startswith("pbkdf2_sha256$")
    assert verify_password("MySecret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_password_hashing_unique_salt():
    """Два вызова hash_password для одного пароля дают разный результат."""
    from security import hash_password
    h1 = hash_password("SamePassword1")
    h2 = hash_password("SamePassword1")
    assert h1 != h2  # разная соль


def test_register_weak_password_rejected(client, csrf_token):
    """Слабый пароль (qwerty12) → отказ."""
    r = client.post("/register", data={
        "csrf": csrf_token,
        "email": "weak@test.ru",
        "name": "Тест",
        "password": "qwerty12",
        "password2": "qwerty12",
    })
    text = r.get_data(as_text=True)
    assert "заглавную букву" in text


def test_register_missing_digit_rejected(client, csrf_token):
    """Пароль без цифры → отказ."""
    r = client.post("/register", data={
        "csrf": csrf_token,
        "email": "nodigit@test.ru",
        "name": "Тест",
        "password": "QwertyAb",
        "password2": "QwertyAb",
    })
    text = r.get_data(as_text=True)
    assert "цифру" in text


def test_register_strong_password_accepted(client, csrf_token):
    """Сложный пароль (Qwerty12) → успешная регистрация (302)."""
    r = client.post("/register", data={
        "csrf": csrf_token,
        "email": "strong@test.ru",
        "name": "Иван",
        "phone": "+79990000000",
        "password": "Qwerty12",
        "password2": "Qwerty12",
    })
    assert r.status_code == 302
    assert "/profile" in r.headers.get("Location", "")


# ============================================================
# 4. Rate limit на входе
# ============================================================

def test_login_rate_limit(client, csrf_token):
    """После 5 неудачных попыток — 429 (Too Many Requests)."""
    for i in range(5):
        client.post("/login", data={
            "csrf": csrf_token,
            "email": "test@rate.ru",
            "password": "wrong",
        })
    # 6-я попытка должна быть заблокирована
    r = client.post("/login", data={
        "csrf": csrf_token,
        "email": "test@rate.ru",
        "password": "wrong",
    })
    assert r.status_code == 429


# ============================================================
# 5. Промокоды и корзина
# ============================================================

def test_calc_discount_percent():
    """WELCOME10 даёт 10% скидку."""
    from helpers import calc_discount
    promo = {"discount_percent": 10, "discount_fixed": 0,
             "min_sum": 0, "max_uses": 0, "used_count": 0}
    assert calc_discount(promo, 10000) == 1000


def test_calc_discount_fixed():
    """SALE500 даёт 500 ₽ скидки."""
    from helpers import calc_discount
    promo = {"discount_percent": 0, "discount_fixed": 500,
             "min_sum": 0, "max_uses": 0, "used_count": 0}
    assert calc_discount(promo, 10000) == 500


def test_calc_discount_below_min_sum():
    """Скидка = 0, если сумма меньше min_sum."""
    from helpers import calc_discount
    promo = {"discount_percent": 10, "discount_fixed": 0,
             "min_sum": 50000, "max_uses": 0, "used_count": 0}
    assert calc_discount(promo, 10000) == 0


def test_calc_discount_limit_exceeded():
    """Скидка = 0, если лимит использований исчерпан."""
    from helpers import calc_discount
    promo = {"discount_percent": 10, "discount_fixed": 0,
             "min_sum": 0, "max_uses": 5, "used_count": 5}
    assert calc_discount(promo, 10000) == 0


def test_calc_discount_not_exceed_total():
    """Скидка не может превышать сумму заказа."""
    from helpers import calc_discount
    promo = {"discount_percent": 0, "discount_fixed": 500,
             "min_sum": 0, "max_uses": 0, "used_count": 0}
    assert calc_discount(promo, 300) == 300  # не 500


# ============================================================
# 6. Загрузка изображений
# ============================================================

def test_is_image_png():
    """PNG-сигнатура распознаётся."""
    from helpers import is_image
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    assert is_image(png_header) is True


def test_is_image_jpeg():
    """JPEG-сигнатура распознаётся."""
    from helpers import is_image
    jpeg_header = b"\xff\xd8\xff" + b"\x00" * 29
    assert is_image(jpeg_header) is True


def test_is_image_rejects_text():
    """Обычный текст не считается изображением."""
    from helpers import is_image
    assert is_image(b"This is not an image at all") is False


# ============================================================
# 7. Логика корзины
# ============================================================

def test_cart_add_valid(client, csrf_token):
    """Добавление существующего товара с правильным размером → 302."""
    r = client.post("/cart/add", data={
        "csrf": csrf_token,
        "id": "1",
        "size": "M",
    })
    assert r.status_code == 302


def test_cart_add_invalid_size(client, csrf_token):
    """Неверный размер → 400."""
    r = client.post("/cart/add", data={
        "csrf": csrf_token,
        "id": "1",
        "size": "XXXXXL",
    })
    assert r.status_code == 400