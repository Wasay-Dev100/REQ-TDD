import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db  # noqa: E402
from models.user import User  # noqa: E402
from models.product import Product  # noqa: E402
from models.place_order_order import PlaceOrderOrder  # noqa: E402
from models.place_order_order_item import PlaceOrderOrderItem  # noqa: E402
from controllers.place_order_controller import (  # noqa: E402
    assert_products_available_for_order,
    create_order_models,
    enqueue_order_for_chef,
    get_current_user,
    parse_and_validate_order_payload,
    utcnow,
)
from views.place_order_views import render_place_order_page  # noqa: E402

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()

@pytest.fixture
def app_context():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()

@pytest.fixture
def db_session(app_context):
    return db.session

def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_user_in_db(email=None, username=None, password="Passw0rd!"):
    if email is None:
        email = f"{_unique('user')}@example.com"
    if username is None:
        username = _unique("user")
    user = User(email=email, username=username, password_hash="", is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

def _create_product_in_db(
    name=None,
    price_cents=1234,
    image_url="https://example.com/img.jpg",
    is_available=True,
    is_active=True,
    description="Tasty",
):
    if name is None:
        name = _unique("dish")
    product = Product(
        name=name,
        description=description,
        price_cents=price_cents,
        image_url=image_url,
        is_available=is_available,
        is_active=is_active,
    )
    db.session.add(product)
    db.session.commit()
    return product

def _login_required_patch(user_id=1, username="u"):
    return patch("controllers.place_order_controller.current_user", MagicMock(is_authenticated=True, id=user_id, username=username))

def _assert_error_response_schema(payload):
    assert isinstance(payload, dict)
    assert "error" in payload
    assert "message" in payload
    assert "details" in payload

def _assert_dish_card_schema(card):
    assert set(card.keys()) == {"id", "name", "price_cents", "image_url", "is_available"}
    assert isinstance(card["id"], int)
    assert isinstance(card["name"], str)
    assert isinstance(card["price_cents"], int)
    assert (isinstance(card["image_url"], str) or card["image_url"] is None)
    assert isinstance(card["is_available"], bool)

def _assert_order_response_schema(payload):
    required = {
        "order_id",
        "status",
        "total_cents",
        "created_at",
        "cancelable_until",
        "seconds_remaining_to_cancel",
        "items",
    }
    assert required.issubset(payload.keys())
    assert isinstance(payload["order_id"], int)
    assert payload["status"] in {"PENDING", "CONFIRMED", "CANCELED"}
    assert isinstance(payload["total_cents"], int)
    assert isinstance(payload["created_at"], str)
    assert isinstance(payload["cancelable_until"], str)
    assert isinstance(payload["seconds_remaining_to_cancel"], int)
    assert payload["seconds_remaining_to_cancel"] >= 0
    assert isinstance(payload["items"], list)
    for item in payload["items"]:
        assert set(item.keys()) == {"product_id", "name", "quantity", "unit_price_cents", "line_total_cents"}
        assert isinstance(item["product_id"], int)
        assert isinstance(item["name"], str)
        assert isinstance(item["quantity"], int)
        assert isinstance(item["unit_price_cents"], int)
        assert isinstance(item["line_total_cents"], int)

def _assert_cancel_order_response_schema(payload):
    assert set(payload.keys()) >= {"order_id", "status", "canceled_at"}
    assert isinstance(payload["order_id"], int)
    assert payload["status"] == "CANCELED"
    assert isinstance(payload["canceled_at"], str)

def _route_exists(path: str, method: str) -> bool:
    method = method.upper()
    for rule in app.url_map.iter_rules():
        if rule.rule == path and method in rule.methods:
            return True
    return False

# MODEL: User (models/user.py)
def test_user_model_has_required_fields(app_context):
    for field in ["id", "email", "username", "password_hash", "is_active"]:
        assert hasattr(User, field), f"Missing User.{field} field"

def test_user_set_password(app_context):
    user = User(email=f"{_unique('e')}@example.com", username=_unique("u"), password_hash="", is_active=True)
    user.set_password("secret123")
    assert user.password_hash
    assert user.password_hash != "secret123"

def test_user_check_password(app_context):
    user = User(email=f"{_unique('e')}@example.com", username=_unique("u"), password_hash="", is_active=True)
    user.set_password("secret123")
    assert user.check_password("secret123") is True
    assert user.check_password("wrong") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")
    u1 = User(email=email, username=username, password_hash="", is_active=True)
    u1.set_password("pw1")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("other"), password_hash="", is_active=True)
    u2.set_password("pw2")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, password_hash="", is_active=True)
    u3.set_password("pw3")
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# MODEL: Product (models/product.py)
def test_product_model_has_required_fields(app_context):
    for field in ["id", "name", "description", "price_cents", "image_url", "is_available", "is_active"]:
        assert hasattr(Product, field), f"Missing Product.{field} field"

def test_product_to_card_dict(app_context):
    p = Product(
        name=_unique("dish"),
        description="desc",
        price_cents=2500,
        image_url="https://example.com/a.jpg",
        is_available=False,
        is_active=True,
    )
    card = p.to_card_dict()
    _assert_dish_card_schema(card)
    assert card["name"] == p.name
    assert card["price_cents"] == p.price_cents
    assert card["image_url"] == p.image_url
    assert card["is_available"] == p.is_available

def test_product_unique_constraints(app_context):
    p1 = Product(name=_unique("p"), description=None, price_cents=100, image_url=None, is_available=True, is_active=True)
    p2 = Product(name=_unique("p"), description=None, price_cents=100, image_url=None, is_available=True, is_active=True)
    db.session.add_all([p1, p2])
    db.session.commit()
    assert p1.id is not None and p2.id is not None

# MODEL: PlaceOrderOrder (models/place_order_order.py)
def test_placeorderorder_model_has_required_fields(app_context):
    for field in [
        "id",
        "customer_id",
        "status",
        "created_at",
        "updated_at",
        "confirmed_at",
        "canceled_at",
        "cancel_reason",
        "total_cents",
        "cancel_window_seconds",
    ]:
        assert hasattr(PlaceOrderOrder, field), f"Missing PlaceOrderOrder.{field} field"

def test_placeorderorder_recalculate_total(app_context):
    order = PlaceOrderOrder(customer_id=1, status="PENDING", total_cents=0, cancel_window_seconds=60)
    item1 = PlaceOrderOrderItem(product_id=1, quantity=2, unit_price_cents=500, line_total_cents=1000)
    item2 = PlaceOrderOrderItem(product_id=2, quantity=1, unit_price_cents=250, line_total_cents=250)
    total = order.recalculate_total([item1, item2])
    assert total == 1250

def test_placeorderorder_is_cancelable(app_context):
    now = datetime.now(timezone.utc)
    order = PlaceOrderOrder(
        customer_id=1,
        status="PENDING",
        total_cents=0,
        cancel_window_seconds=60,
        created_at=now - timedelta(seconds=30),
    )
    assert order.is_cancelable(now) is True

    order2 = PlaceOrderOrder(
        customer_id=1,
        status="PENDING",
        total_cents=0,
        cancel_window_seconds=60,
        created_at=now - timedelta(seconds=61),
    )
    assert order2.is_cancelable(now) is False

    order3 = PlaceOrderOrder(
        customer_id=1,
        status="CANCELED",
        total_cents=0,
        cancel_window_seconds=60,
        created_at=now - timedelta(seconds=10),
    )
    assert order3.is_cancelable(now) is False

def test_placeorderorder_to_dict(app_context):
    now = datetime.now(timezone.utc)
    order = PlaceOrderOrder(
        customer_id=1,
        status="PENDING",
        total_cents=123,
        cancel_window_seconds=60,
        created_at=now,
        updated_at=now,
    )
    d = order.to_dict()
    assert isinstance(d, dict)
    assert "order_id" in d
    assert "status" in d
    assert "total_cents" in d
    assert "created_at" in d
    assert "cancelable_until" in d
    assert "seconds_remaining_to_cancel" in d
    assert "items" in d

def test_placeorderorder_unique_constraints(app_context):
    o1 = PlaceOrderOrder(customer_id=1, status="PENDING", total_cents=0, cancel_window_seconds=60)
    o2 = PlaceOrderOrder(customer_id=1, status="PENDING", total_cents=0, cancel_window_seconds=60)
    db.session.add_all([o1, o2])
    db.session.commit()
    assert o1.id is not None and o2.id is not None

# MODEL: PlaceOrderOrderItem (models/place_order_order_item.py)
def test_placeorderorderitem_model_has_required_fields(app_context):
    for field in ["id", "order_id", "product_id", "quantity", "unit_price_cents", "line_total_cents"]:
        assert hasattr(PlaceOrderOrderItem, field), f"Missing PlaceOrderOrderItem.{field} field"

def test_placeorderorderitem_compute_line_total(app_context):
    item = PlaceOrderOrderItem(product_id=1, quantity=3, unit_price_cents=499, line_total_cents=0)
    total = item.compute_line_total()
    assert total == 1497

def test_placeorderorderitem_to_dict(app_context):
    item = PlaceOrderOrderItem(product_id=7, quantity=2, unit_price_cents=1000, line_total_cents=2000)
    d = item.to_dict()
    assert isinstance(d, dict)
    assert set(d.keys()) >= {"product_id", "quantity", "unit_price_cents", "line_total_cents"}

def test_placeorderorderitem_unique_constraints(app_context):
    i1 = PlaceOrderOrderItem(order_id=1, product_id=1, quantity=1, unit_price_cents=100, line_total_cents=100)
    i2 = PlaceOrderOrderItem(order_id=1, product_id=1, quantity=2, unit_price_cents=100, line_total_cents=200)
    db.session.add_all([i1, i2])
    db.session.commit()
    assert i1.id is not None and i2.id is not None

# ROUTE: /place-order (GET) - place_order_page
def test_place_order_get_exists(client):
    assert _route_exists("/place-order", "GET"), "Route /place-order with GET must exist"

def test_place_order_get_renders_template(client):
    user = None
    with app.app_context():
        user = _create_user_in_db()
    with _login_required_patch(user_id=user.id, username=user.username):
        resp = client.get("/place-order")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")
    assert b"<html" in resp.data.lower() or b"<!doctype html" in resp.data.lower()

# ROUTE: /api/place-order/dishes (GET) - list_dishes
def test_api_place_order_dishes_get_exists(client):
    assert _route_exists("/api/place-order/dishes", "GET"), "Route /api/place-order/dishes with GET must exist"

def test_api_place_order_dishes_get_renders_template(client):
    with app.app_context():
        user = _create_user_in_db()
        _create_product_in_db(is_available=True, is_active=True)
        _create_product_in_db(is_available=False, is_active=True)
    with _login_required_patch(user_id=user.id, username=user.username):
        resp = client.get("/api/place-order/dishes")
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    payload = resp.get_json()
    assert isinstance(payload, dict)
    assert "dishes" in payload
    assert isinstance(payload["dishes"], list)
    assert len(payload["dishes"]) >= 2
    for card in payload["dishes"]:
        _assert_dish_card_schema(card)

# ROUTE: /api/place-order/validate-quantity (POST) - validate_quantity
def test_api_place_order_validate_quantity_post_exists(client):
    assert _route_exists("/api/place-order/validate-quantity", "POST"), "Route /api/place-order/validate-quantity with POST must exist"

def test_api_place_order_validate_quantity_post_success(client):
    with app.app_context():
        user = _create_user_in_db()
    with _login_required_patch(user_id=user.id, username=user.username):
        resp = client.post("/api/place-order/validate-quantity", json={"quantity": "12"})
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    payload = resp.get_json()
    assert set(payload.keys()) == {"is_valid", "normalized_quantity"}
    assert payload["is_valid"] is True
    assert payload["normalized_quantity"] == 12

def test_api_place_order_validate_quantity_post_missing_required_fields(client):
    with app.app_context():
        user = _create_user_in_db()
    with _login_required_patch(user_id=user.id, username=user.username):
        resp = client.post("/api/place-order/validate-quantity", json={})
    assert resp.status_code == 400
    payload = resp.get_json()
    _assert_error_response_schema(payload)

def test_api_place_order_validate_quantity_post_invalid_data(client):
    with app.app_context():
        user = _create_user_in_db()
    with _login_required_patch(user_id=user.id, username=user.username):
        resp = client.post("/api/place-order/validate-quantity", json={"quantity": "12a"})
    assert resp.status_code == 400
    payload = resp.get_json()
    _assert_error_response_schema(payload)

def test_api_place_order_validate_quantity_post_duplicate_data(client):
    with app.app_context():
        user = _create_user_in_db()
    with _login_required_patch(user_id=user.id, username=user.username):
        resp1 = client.post("/api/place-order/validate-quantity", json={"quantity": "7"})
        resp2 = client.post("/api/place-order/validate-quantity", json={"quantity": "7"})
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.get_json() == resp2.get_json()

# ROUTE: /api/place-order/orders (POST) - create_order
def test_api_place_order_orders_post_exists(client):
    assert _route_exists("/api/place-order/orders", "POST"), "Route /api/place-order/orders with POST must exist"

def test_api_place_order_orders_post_success(client):
    with app.app_context():
        user = _create_user_in_db()
        p1 = _create_product_in_db(price_cents=500, is_available=True, is_active=True)
        p2 = _create_product_in_db(price_cents=250, is_available=True, is_active=True)
    with _login_required_patch(user_id=user.id, username=user.username), patch(
        "controllers.place_order_controller.enqueue_order_for_chef"
    ) as mock_enqueue:
        resp = client.post(
            "/api/place-order/orders",
            json={"items": [{"product_id": p1.id, "quantity": 2}, {"product_id": p2.id, "quantity": 1}]},
        )
    assert resp.status_code == 201
    assert resp.content_type.startswith("application/json")
    payload = resp.get_json()
    _assert_order_response_schema(payload)
    assert payload["status"] == "PENDING"
    assert payload["total_cents"] == 1250
    mock_enqueue.assert_called_once()

def test_api_place_order_orders_post_missing_required_fields(client):
    with app.app_context():
        user = _create_user_in_db()
    with _login_required_patch(user_id=user.id, username=user.username):
        resp = client.post("/api/place-order/orders", json={})
    assert resp.status_code == 400
    payload = resp.get_json()
    _assert_error_response_schema(payload)

def test_api_place_order_orders_post_invalid_data(client):
    with app.app_context():
        user = _create_user_in_db()
        p1 = _create_product_in_db(price_cents=500, is_available=True, is_active=True)
    with _login_required_patch(user_id=user.id, username=user.username):
        resp = client.post("/api/place-order/orders", json={"items": [{"product_id": p1.id, "quantity": 0}]})
    assert resp.status_code == 400
    payload = resp.get_json()
    _assert_error_response_schema(payload)

def test_api_place_order_orders_post_duplicate_data(client):
    with app.app_context():
        user = _create_user_in_db()
        p1 = _create_product_in_db(price_cents=500, is_available=True, is_active=True)
    with _login_required_patch(user_id=user.id, username=user.username), patch(
        "controllers.place_order_controller.enqueue_order_for_chef"
    ):
        resp = client.post("/api/place-order/orders", json={"items": [{"product_id": p1.id, "quantity": 1}, {"product_id": p1.id, "quantity": 2}]})
    assert resp.status_code == 400
    payload = resp.get_json()
    _assert_error_response_schema(payload)

# ROUTE: /api/place-order/orders/<int:order_id> (GET) - get_order
def test_api_place_order_orders_order_id_get_exists(client):
    assert _route_exists("/api/place-order/orders/<int:order_id>", "GET"), "Route /api/place-order/orders/<int:order_id> with GET must exist"

def test_api_place_order_orders_order_id_get_renders_template(client):
    with app.app_context():
        user = _create_user_in_db()
        p1 = _create_product_in_db(price_cents=500, is_available=True, is_active=True)
        order = PlaceOrderOrder(customer_id=user.id, status="PENDING", total_cents=0, cancel_window_seconds=60, created_at=datetime.now(timezone.utc))
        db.session.add(order)
        db.session.flush()
        item = PlaceOrderOrderItem(order_id=order.id, product_id=p1.id, quantity=2, unit_price_cents=p1.price_cents, line_total_cents=2 * p1.price_cents)
        db.session.add(item)
        order.total_cents = order.recalculate_total([item])
        db.session.commit()
        order_id = order.id
    with _login_required_patch(user_id=user.id, username=user.username):
        resp = client.get(f"/api/place-order/orders/{order_id}")
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    payload = resp.get_json()
    _assert_order_response_schema(payload)
    assert payload["order_id"] == order_id

# ROUTE: /api/place-order/orders/<int:order_id>/cancel (POST) - cancel_order
def test_api_place_order_orders_order_id_cancel_post_exists(client):
    assert _route_exists("/api/place-order/orders/<int:order_id>/cancel", "POST"), "Route /api/place-order/orders/<int:order_id>/cancel with POST must exist"

def test_api_place_order_orders_order_id_cancel_post_success(client):
    with app.app_context():
        user = _create_user_in_db()
        order = PlaceOrderOrder(
            customer_id=user.id,
            status="PENDING",
            total_cents=0,
            cancel_window_seconds=60,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(order)
        db.session.commit()
        order_id = order.id
    with _login_required_patch(user_id=user.id, username=user.username):
        resp = client.post(f"/api/place-order/orders/{order_id}/cancel", json={"reason": "Changed mind"})
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    payload = resp.get_json()
    _assert_cancel_order_response_schema(payload)
    assert payload["order_id"] == order_id

def test_api_place_order_orders_order_id_cancel_post_missing_required_fields(client):
    with app.app_context():
        user = _create_user_in_db()
        order = PlaceOrderOrder(
            customer_id=user.id,
            status="PENDING",
            total_cents=0,
            cancel_window_seconds=60,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(order)
        db.session.commit()
        order_id = order.id
    with _login_required_patch(user_id=user.id, username=user.username):
        resp = client.post(f"/api/place-order/orders/{order_id}/cancel", json={})
    assert resp.status_code in (200, 400)
    payload = resp.get_json()
    if resp.status_code == 400:
        _assert_error_response_schema(payload)
    else:
        _assert_cancel_order_response_schema(payload)

def test_api_place_order_orders_order_id_cancel_post_invalid_data(client):
    with app.app_context():
        user = _create_user_in_db()
        order = PlaceOrderOrder(
            customer_id=user.id,
            status="PENDING",
            total_cents=0,
            cancel_window_seconds=60,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(order)
        db.session.commit()
        order_id = order.id
    long_reason = "x" * 256
    with _login_required_patch(user_id=user.id, username=user.username):
        resp = client.post(f"/api/place-order/orders/{order_id}/cancel", json={"reason": long_reason})
    assert resp.status_code == 400
    payload = resp.get_json()
    _assert_error_response_schema(payload)

def test_api_place_order_orders_order_id_cancel_post_duplicate_data(client):
    with app.app_context():
        user = _create_user_in_db()
        order = PlaceOrderOrder(
            customer_id=user.id,
            status="PENDING",
            total_cents=0,
            cancel_window_seconds=60,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(order)
        db.session.commit()
        order_id = order.id
    with _login_required_patch(user_id=user.id, username=user.username):
        resp1 = client.post(f"/api/place-order/orders/{order_id}/cancel", json={"reason": "First"})
        resp2 = client.post(f"/api/place-order/orders/{order_id}/cancel", json={"reason": "Second"})
    assert resp1.status_code == 200
    assert resp2.status_code in (403, 400)
    payload2 = resp2.get_json()
    _assert_error_response_schema(payload2)

# HELPER: get_current_user(N/A)
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(app_context):
    user = _create_user_in_db()
    with _login_required_patch(user_id=user.id, username=user.username):
        u = get_current_user()
    assert u is not None
    assert getattr(u, "id", None) == user.id

def test_get_current_user_with_invalid_input(app_context):
    with patch("controllers.place_order_controller.current_user", MagicMock(is_authenticated=False)):
        with pytest.raises(Exception):
            get_current_user()

# HELPER: parse_and_validate_order_payload(payload)
def test_parse_and_validate_order_payload_function_exists():
    assert callable(parse_and_validate_order_payload)

def test_parse_and_validate_order_payload_with_valid_input():
    payload = {"items": [{"product_id": 1, "quantity": 2}, {"product_id": 2, "quantity": 1}]}
    result = parse_and_validate_order_payload(payload)
    assert isinstance(result, dict)
    assert "items" in result
    assert isinstance(result["items"], list)
    assert result["items"] == payload["items"]

def test_parse_and_validate_order_payload_with_invalid_input():
    with pytest.raises(Exception):
        parse_and_validate_order_payload({"items": [{"product_id": 0, "quantity": 1}]})
    with pytest.raises(Exception):
        parse_and_validate_order_payload({"items": []})
    with pytest.raises(Exception):
        parse_and_validate_order_payload({"items": [{"product_id": 1, "quantity": 1000}]})
    with pytest.raises(Exception):
        parse_and_validate_order_payload({"items": [{"product_id": 1, "quantity": 1, "extra": "x"}]})

# HELPER: assert_products_available_for_order(items)
def test_assert_products_available_for_order_function_exists():
    assert callable(assert_products_available_for_order)

def test_assert_products_available_for_order_with_valid_input(app_context):
    p1 = _create_product_in_db(is_available=True, is_active=True)
    p2 = _create_product_in_db(is_available=True, is_active=True)
    items = [{"product_id": p1.id, "quantity": 1}, {"product_id": p2.id, "quantity": 2}]
    assert_products_available_for_order(items)

def test_assert_products_available_for_order_with_invalid_input(app_context):
    p1 = _create_product_in_db(is_available=False, is_active=True)
    items = [{"product_id": p1.id, "quantity": 1}]
    with pytest.raises(Exception):
        assert_products_available_for_order(items)

# HELPER: create_order_models(customer_id, items, now_utc)
def test_create_order_models_function_exists():
    assert callable(create_order_models)

def test_create_order_models_with_valid_input(app_context):
    user = _create_user_in_db()
    p1 = _create_product_in_db(price_cents=500, is_available=True, is_active=True)
    p2 = _create_product_in_db(price_cents=250, is_available=True, is_active=True)
    now = datetime.now(timezone.utc)
    items = [{"product_id": p1.id, "quantity": 2}, {"product_id": p2.id, "quantity": 1}]
    order = create_order_models(customer_id=user.id, items=items, now_utc=now)
    assert isinstance(order, PlaceOrderOrder)
    assert order.customer_id == user.id
    assert order.status == "PENDING"
    assert order.total_cents == 1250

def test_create_order_models_with_invalid_input(app_context):
    user = _create_user_in_db()
    now = datetime.now(timezone.utc)
    with pytest.raises(Exception):
        create_order_models(customer_id=user.id, items=[], now_utc=now)
    with pytest.raises(Exception):
        create_order_models(customer_id=0, items=[{"product_id": 1, "quantity": 1}], now_utc=now)

# HELPER: enqueue_order_for_chef(order)
def test_enqueue_order_for_chef_function_exists():
    assert callable(enqueue_order_for_chef)

def test_enqueue_order_for_chef_with_valid_input(app_context):
    order = PlaceOrderOrder(customer_id=1, status="PENDING", total_cents=0, cancel_window_seconds=60, created_at=datetime.now(timezone.utc))
    enqueue_order_for_chef(order)

def test_enqueue_order_for_chef_with_invalid_input(app_context):
    with pytest.raises(Exception):
        enqueue_order_for_chef(None)

# HELPER: utcnow(N/A)
def test_utcnow_function_exists():
    assert callable(utcnow)

def test_utcnow_with_valid_input():
    now = utcnow()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None

def test_utcnow_with_invalid_input():
    with pytest.raises(TypeError):
        utcnow(1)  # type: ignore[arg-type]