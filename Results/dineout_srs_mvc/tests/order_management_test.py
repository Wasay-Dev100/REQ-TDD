import os
import sys
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db  # noqa: E402
from models.user import User  # noqa: E402
from models.category import Category  # noqa: E402
from models.product import Product  # noqa: E402
from models.customer_order_management_order import Order  # noqa: E402
from models.customer_order_management_order_item import OrderItem  # noqa: E402
from models.customer_order_management_bill_request import BillRequest  # noqa: E402
from models.customer_order_management_feedback import Feedback  # noqa: E402
from controllers.customer_order_management_controller import (  # noqa: E402
    validate_order_editable,
    apply_order_items_patch,
    compute_totals,
    firebase_upsert_order,
    firebase_upsert_bill_request,
    firebase_upsert_feedback,
)
from views.customer_order_management_views import (  # noqa: E402
    serialize_category,
    serialize_product,
    serialize_order_item,
    serialize_order,
    serialize_bill,
    serialize_feedback,
)

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

def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_user_in_db(email=None, username=None, password="Passw0rd!"):
    if email is None:
        email = f"{_uid('user')}@example.com"
    if username is None:
        username = _uid("username")
    u = User(email=email, username=username, password_hash="")
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u

def _create_category_in_db(name=None, description="desc", is_active=True, sort_order=1):
    if name is None:
        name = _uid("cat")
    c = Category(name=name, description=description, is_active=is_active, sort_order=sort_order)
    db.session.add(c)
    db.session.commit()
    return c

def _create_product_in_db(category_id, name=None, price_cents=1000, is_available=True):
    if name is None:
        name = _uid("prod")
    p = Product(
        category_id=category_id,
        name=name,
        description="tasty",
        price_cents=price_cents,
        image_url=None,
        is_available=is_available,
        prep_time_minutes=10,
    )
    db.session.add(p)
    db.session.commit()
    return p

def _create_order_in_db(customer_id, table_identifier=None, status="NEW", notes=None):
    if table_identifier is None:
        table_identifier = _uid("T")
    o = Order(
        customer_id=customer_id,
        table_identifier=table_identifier,
        status=status,
        subtotal_cents=0,
        tax_cents=0,
        service_charge_cents=0,
        total_cents=0,
        notes=notes,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        prepared_at=None,
        cancelled_at=None,
    )
    db.session.add(o)
    db.session.commit()
    return o

def _create_order_item_in_db(order_id, product_id, product_name_snapshot="Snap", unit_price_cents_snapshot=500, quantity=2):
    it = OrderItem(
        order_id=order_id,
        product_id=product_id,
        product_name_snapshot=product_name_snapshot,
        unit_price_cents_snapshot=unit_price_cents_snapshot,
        quantity=quantity,
        special_instructions=None,
        line_total_cents=unit_price_cents_snapshot * quantity,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(it)
    db.session.commit()
    return it

def _create_bill_request_in_db(order_id, requested_by_customer_id, status="REQUESTED", notes=None):
    br = BillRequest(
        order_id=order_id,
        requested_by_customer_id=requested_by_customer_id,
        status=status,
        requested_at=datetime.utcnow(),
        processed_at=None,
        notes=notes,
    )
    db.session.add(br)
    db.session.commit()
    return br

def _create_feedback_in_db(order_id, customer_id, rating=5, comment=None):
    fb = Feedback(
        order_id=order_id,
        customer_id=customer_id,
        rating=rating,
        comment=comment,
        created_at=datetime.utcnow(),
    )
    db.session.add(fb)
    db.session.commit()
    return fb

def _assert_route_exists(path: str, method: str):
    rules = list(app.url_map.iter_rules())
    matches = [r for r in rules if r.rule == path and method in r.methods]
    assert matches, f"Expected route {method} {path} to exist"

# -----------------------
# MODEL: User
# -----------------------
def test_user_model_has_required_fields(app_context):
    for field in ["id", "email", "username", "password_hash", "created_at"]:
        assert hasattr(User, field), f"User missing field: {field}"

def test_user_set_password(app_context):
    u = User(email=f"{_uid('u')}@example.com", username=_uid("u"), password_hash="")
    u.set_password("Secret123!")
    assert u.password_hash
    assert u.password_hash != "Secret123!"

def test_user_check_password(app_context):
    u = User(email=f"{_uid('u')}@example.com", username=_uid("u"), password_hash="")
    u.set_password("Secret123!")
    assert u.check_password("Secret123!") is True
    assert u.check_password("WrongPass!") is False

def test_user_unique_constraints(app_context):
    email = f"{_uid('dup')}@example.com"
    username = _uid("dupuser")

    u1 = User(email=email, username=username, password_hash="")
    u1.set_password("Secret123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_uid("otheruser"), password_hash="")
    u2.set_password("Secret123!")
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_uid('other')}@example.com", username=username, password_hash="")
    u3.set_password("Secret123!")
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# -----------------------
# MODEL: Category
# -----------------------
def test_category_model_has_required_fields(app_context):
    for field in ["id", "name", "description", "is_active", "sort_order"]:
        assert hasattr(Category, field), f"Category missing field: {field}"

def test_category_unique_constraints(app_context):
    name = _uid("catdup")
    c1 = Category(name=name, description=None, is_active=True, sort_order=1)
    db.session.add(c1)
    db.session.commit()

    c2 = Category(name=name, description=None, is_active=True, sort_order=2)
    db.session.add(c2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# -----------------------
# MODEL: Product
# -----------------------
def test_product_model_has_required_fields(app_context):
    for field in [
        "id",
        "category_id",
        "name",
        "description",
        "price_cents",
        "image_url",
        "is_available",
        "prep_time_minutes",
    ]:
        assert hasattr(Product, field), f"Product missing field: {field}"

def test_product_unique_constraints(app_context):
    cat = _create_category_in_db()
    p1 = Product(
        category_id=cat.id,
        name="SameNameOK",
        description=None,
        price_cents=100,
        image_url=None,
        is_available=True,
        prep_time_minutes=None,
    )
    p2 = Product(
        category_id=cat.id,
        name="SameNameOK",
        description=None,
        price_cents=200,
        image_url=None,
        is_available=True,
        prep_time_minutes=None,
    )
    db.session.add_all([p1, p2])
    db.session.commit()
    assert p1.id is not None and p2.id is not None

# -----------------------
# MODEL: Order
# -----------------------
def test_order_model_has_required_fields(app_context):
    for field in [
        "id",
        "customer_id",
        "table_identifier",
        "status",
        "subtotal_cents",
        "tax_cents",
        "service_charge_cents",
        "total_cents",
        "notes",
        "created_at",
        "updated_at",
        "prepared_at",
        "cancelled_at",
    ]:
        assert hasattr(Order, field), f"Order missing field: {field}"

def test_order_is_editable(app_context):
    user = _create_user_in_db()
    order = _create_order_in_db(customer_id=user.id, status="NEW")
    assert hasattr(order, "is_editable")
    assert callable(order.is_editable)
    result = order.is_editable()
    assert isinstance(result, bool)

def test_order_recalculate_totals(app_context):
    user = _create_user_in_db()
    cat = _create_category_in_db()
    prod = _create_product_in_db(category_id=cat.id, price_cents=1000)

    order = _create_order_in_db(customer_id=user.id, status="NEW")
    _create_order_item_in_db(order_id=order.id, product_id=prod.id, unit_price_cents_snapshot=1000, quantity=2)

    assert hasattr(order, "recalculate_totals")
    order.recalculate_totals(tax_rate=0.1, service_charge_rate=0.05)
    db.session.refresh(order)

    assert order.subtotal_cents == 2000
    assert order.tax_cents == 200
    assert order.service_charge_cents == 100
    assert order.total_cents == 2300

def test_order_unique_constraints(app_context):
    user = _create_user_in_db()
    o1 = _create_order_in_db(customer_id=user.id, table_identifier="A1", status="NEW")
    o2 = _create_order_in_db(customer_id=user.id, table_identifier="A1", status="NEW")
    assert o1.id != o2.id

# -----------------------
# MODEL: OrderItem
# -----------------------
def test_orderitem_model_has_required_fields(app_context):
    for field in [
        "id",
        "order_id",
        "product_id",
        "product_name_snapshot",
        "unit_price_cents_snapshot",
        "quantity",
        "special_instructions",
        "line_total_cents",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(OrderItem, field), f"OrderItem missing field: {field}"

def test_orderitem_recalculate_line_total(app_context):
    user = _create_user_in_db()
    cat = _create_category_in_db()
    prod = _create_product_in_db(category_id=cat.id, price_cents=750)
    order = _create_order_in_db(customer_id=user.id)

    item = OrderItem(
        order_id=order.id,
        product_id=prod.id,
        product_name_snapshot="Snap",
        unit_price_cents_snapshot=750,
        quantity=3,
        special_instructions=None,
        line_total_cents=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(item)
    db.session.commit()

    assert hasattr(item, "recalculate_line_total")
    item.recalculate_line_total()
    db.session.commit()
    db.session.refresh(item)
    assert item.line_total_cents == 2250

def test_orderitem_unique_constraints(app_context):
    user = _create_user_in_db()
    cat = _create_category_in_db()
    prod = _create_product_in_db(category_id=cat.id)
    order = _create_order_in_db(customer_id=user.id)

    i1 = _create_order_item_in_db(order_id=order.id, product_id=prod.id, product_name_snapshot="X", unit_price_cents_snapshot=100, quantity=1)
    i2 = _create_order_item_in_db(order_id=order.id, product_id=prod.id, product_name_snapshot="X", unit_price_cents_snapshot=100, quantity=1)
    assert i1.id != i2.id

# -----------------------
# MODEL: BillRequest
# -----------------------
def test_billrequest_model_has_required_fields(app_context):
    for field in ["id", "order_id", "requested_by_customer_id", "status", "requested_at", "processed_at", "notes"]:
        assert hasattr(BillRequest, field), f"BillRequest missing field: {field}"

def test_billrequest_unique_constraints(app_context):
    user = _create_user_in_db()
    order = _create_order_in_db(customer_id=user.id)
    br1 = _create_bill_request_in_db(order_id=order.id, requested_by_customer_id=user.id)
    br2 = _create_bill_request_in_db(order_id=order.id, requested_by_customer_id=user.id)
    assert br1.id != br2.id

# -----------------------
# MODEL: Feedback
# -----------------------
def test_feedback_model_has_required_fields(app_context):
    for field in ["id", "order_id", "customer_id", "rating", "comment", "created_at"]:
        assert hasattr(Feedback, field), f"Feedback missing field: {field}"

def test_feedback_unique_constraints(app_context):
    user = _create_user_in_db()
    order = _create_order_in_db(customer_id=user.id)
    f1 = _create_feedback_in_db(order_id=order.id, customer_id=user.id, rating=5, comment="a")
    f2 = _create_feedback_in_db(order_id=order.id, customer_id=user.id, rating=4, comment="b")
    assert f1.id != f2.id

# -----------------------
# ROUTE: /menu (GET)
# -----------------------
def test_menu_get_exists(client):
    _assert_route_exists("/menu", "GET")

def test_menu_get_renders_template(client):
    resp = client.get("/menu")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# -----------------------
# ROUTE: /orders (POST)
# -----------------------
def test_orders_post_exists(client):
    _assert_route_exists("/orders", "POST")

def test_orders_post_success(client):
    with app.app_context():
        user = _create_user_in_db()
        cat = _create_category_in_db()
        prod = _create_product_in_db(category_id=cat.id, price_cents=1200)

    payload = {
        "customer_id": user.id,
        "table_identifier": _uid("TABLE"),
        "items": [{"product_id": prod.id, "quantity": 2, "special_instructions": "no onions"}],
        "notes": "please hurry",
    }
    with patch("controllers.customer_order_management_controller.firebase_upsert_order") as mock_fb:
        resp = client.post("/orders", json=payload)
        assert resp.status_code in (200, 201)
        data = resp.get_json(silent=True)
        assert data is not None
        assert "id" in data or "order" in data
        assert mock_fb.called is True

def test_orders_post_missing_required_fields(client):
    with patch("controllers.customer_order_management_controller.firebase_upsert_order") as mock_fb:
        resp = client.post("/orders", json={"table_identifier": _uid("T")})
        assert resp.status_code in (400, 422)
        assert mock_fb.called is False

def test_orders_post_invalid_data(client):
    with app.app_context():
        user = _create_user_in_db()

    with patch("controllers.customer_order_management_controller.firebase_upsert_order") as mock_fb:
        resp = client.post(
            "/orders",
            json={
                "customer_id": user.id,
                "table_identifier": _uid("T"),
                "items": "not-a-list",
            },
        )
        assert resp.status_code in (400, 422)
        assert mock_fb.called is False

def test_orders_post_duplicate_data(client):
    with app.app_context():
        user = _create_user_in_db()
        cat = _create_category_in_db()
        prod = _create_product_in_db(category_id=cat.id, price_cents=500)

    payload = {
        "customer_id": user.id,
        "table_identifier": _uid("T"),
        "items": [{"product_id": prod.id, "quantity": 1}],
        "notes": None,
    }
    with patch("controllers.customer_order_management_controller.firebase_upsert_order"):
        r1 = client.post("/orders", json=payload)
        r2 = client.post("/orders", json=payload)
    assert r1.status_code in (200, 201)
    assert r2.status_code in (200, 201, 409)

# -----------------------
# ROUTE: /orders/<int:order_id> (GET)
# -----------------------
def test_orders_order_id_get_exists(client):
    _assert_route_exists("/orders/<int:order_id>", "GET")

def test_orders_order_id_get_renders_template(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id)

    resp = client.get(f"/orders/{order.id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# -----------------------
# ROUTE: /orders/<int:order_id> (PATCH)
# -----------------------
def test_orders_order_id_patch_exists(client):
    _assert_route_exists("/orders/<int:order_id>", "PATCH")

# -----------------------
# ROUTE: /orders/<int:order_id>/cancel (POST)
# -----------------------
def test_orders_order_id_cancel_post_exists(client):
    _assert_route_exists("/orders/<int:order_id>/cancel", "POST")

def test_orders_order_id_cancel_post_success(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_order") as mock_fb:
        resp = client.post(f"/orders/{order.id}/cancel", json={"reason": "changed mind"})
        assert resp.status_code in (200, 201)
        assert mock_fb.called is True

def test_orders_order_id_cancel_post_missing_required_fields(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_order") as mock_fb:
        resp = client.post(f"/orders/{order.id}/cancel", json={})
        assert resp.status_code in (200, 201, 400, 422)
        if resp.status_code in (400, 422):
            assert mock_fb.called is False

def test_orders_order_id_cancel_post_invalid_data(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_order") as mock_fb:
        resp = client.post(f"/orders/{order.id}/cancel", json={"reason": 12345})
        assert resp.status_code in (200, 201, 400, 422)
        if resp.status_code in (400, 422):
            assert mock_fb.called is False

def test_orders_order_id_cancel_post_duplicate_data(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_order"):
        r1 = client.post(f"/orders/{order.id}/cancel", json={"reason": "x"})
        r2 = client.post(f"/orders/{order.id}/cancel", json={"reason": "x"})
    assert r1.status_code in (200, 201)
    assert r2.status_code in (200, 201, 409)

# -----------------------
# ROUTE: /orders/<int:order_id>/bill (POST)
# -----------------------
def test_orders_order_id_bill_post_exists(client):
    _assert_route_exists("/orders/<int:order_id>/bill", "POST")

def test_orders_order_id_bill_post_success(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_bill_request") as mock_fb:
        resp = client.post(
            f"/orders/{order.id}/bill",
            json={"customer_id": user.id, "notes": "cash please"},
        )
        assert resp.status_code in (200, 201)
        assert mock_fb.called is True

def test_orders_order_id_bill_post_missing_required_fields(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_bill_request") as mock_fb:
        resp = client.post(f"/orders/{order.id}/bill", json={"notes": "x"})
        assert resp.status_code in (400, 422)
        assert mock_fb.called is False

def test_orders_order_id_bill_post_invalid_data(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_bill_request") as mock_fb:
        resp = client.post(
            f"/orders/{order.id}/bill",
            json={"customer_id": "not-an-int", "notes": "x"},
        )
        assert resp.status_code in (400, 422)
        assert mock_fb.called is False

def test_orders_order_id_bill_post_duplicate_data(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_bill_request"):
        r1 = client.post(f"/orders/{order.id}/bill", json={"customer_id": user.id, "notes": None})
        r2 = client.post(f"/orders/{order.id}/bill", json={"customer_id": user.id, "notes": None})
    assert r1.status_code in (200, 201)
    assert r2.status_code in (200, 201, 409)

# -----------------------
# ROUTE: /orders/<int:order_id>/bill (GET)
# -----------------------
def test_orders_order_id_bill_get_exists(client):
    _assert_route_exists("/orders/<int:order_id>/bill", "GET")

def test_orders_order_id_bill_get_renders_template(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    resp = client.get(f"/orders/{order.id}/bill")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# -----------------------
# ROUTE: /orders/<int:order_id>/feedback (POST)
# -----------------------
def test_orders_order_id_feedback_post_exists(client):
    _assert_route_exists("/orders/<int:order_id>/feedback", "POST")

def test_orders_order_id_feedback_post_success(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_feedback") as mock_fb:
        resp = client.post(
            f"/orders/{order.id}/feedback",
            json={"customer_id": user.id, "rating": 5, "comment": "great"},
        )
        assert resp.status_code in (200, 201)
        assert mock_fb.called is True

def test_orders_order_id_feedback_post_missing_required_fields(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_feedback") as mock_fb:
        resp = client.post(f"/orders/{order.id}/feedback", json={"customer_id": user.id})
        assert resp.status_code in (400, 422)
        assert mock_fb.called is False

def test_orders_order_id_feedback_post_invalid_data(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_feedback") as mock_fb:
        resp = client.post(
            f"/orders/{order.id}/feedback",
            json={"customer_id": user.id, "rating": "five", "comment": "x"},
        )
        assert resp.status_code in (400, 422)
        assert mock_fb.called is False

def test_orders_order_id_feedback_post_duplicate_data(client):
    with app.app_context():
        user = _create_user_in_db()
        order = _create_order_in_db(customer_id=user.id, status="NEW")

    with patch("controllers.customer_order_management_controller.firebase_upsert_feedback"):
        r1 = client.post(f"/orders/{order.id}/feedback", json={"customer_id": user.id, "rating": 5, "comment": None})
        r2 = client.post(f"/orders/{order.id}/feedback", json={"customer_id": user.id, "rating": 5, "comment": None})
    assert r1.status_code in (200, 201)
    assert r2.status_code in (200, 201, 409)

# -----------------------
# HELPER: validate_order_editable(order: Order)
# -----------------------
def test_validate_order_editable_function_exists():
    assert callable(validate_order_editable)

def test_validate_order_editable_with_valid_input(app_context):
    user = _create_user_in_db()
    order = _create_order_in_db(customer_id=user.id, status="NEW")
    result = validate_order_editable(order)
    assert result is None or (isinstance(result, tuple) and len(result) == 2)

def test_validate_order_editable_with_invalid_input(app_context):
    result = validate_order_editable(None)
    assert result is not None
    assert isinstance(result, tuple)
    assert len(result) == 2

# -----------------------
# HELPER: apply_order_items_patch(order: Order, items_payload: list[dict])
# -----------------------
def test_apply_order_items_patch_function_exists():
    assert callable(apply_order_items_patch)

def test_apply_order_items_patch_with_valid_input(app_context):
    user = _create_user_in_db()
    cat = _create_category_in_db()
    prod = _create_product_in_db(category_id=cat.id, price_cents=333)
    order = _create_order_in_db(customer_id=user.id, status="NEW")

    items_payload = [{"product_id": prod.id, "quantity": 3, "special_instructions": "extra spicy"}]
    apply_order_items_patch(order, items_payload)
    db.session.commit()

    items = OrderItem.query.filter_by(order_id=order.id).all()
    assert len(items) >= 1
    assert any(i.product_id == prod.id and i.quantity == 3 for i in items)

def test_apply_order_items_patch_with_invalid_input(app_context):
    user = _create_user_in_db()
    order = _create_order_in_db(customer_id=user.id, status="NEW")
    with pytest.raises(Exception):
        apply_order_items_patch(order, None)

# -----------------------
# HELPER: compute_totals(order: Order) -> dict
# -----------------------
def test_compute_totals_function_exists():
    assert callable(compute_totals)

def test_compute_totals_with_valid_input(app_context):
    user = _create_user_in_db()
    cat = _create_category_in_db()
    prod = _create_product_in_db(category_id=cat.id, price_cents=1000)
    order = _create_order_in_db(customer_id=user.id, status="NEW")
    _create_order_item_in_db(order_id=order.id, product_id=prod.id, unit_price_cents_snapshot=1000, quantity=2)

    totals = compute_totals(order)
    assert isinstance(totals, dict)
    for k in ["subtotal_cents", "tax_cents", "service_charge_cents", "total_cents"]:
        assert k in totals

def test_compute_totals_with_invalid_input(app_context):
    with pytest.raises(Exception):
        compute_totals(None)

# -----------------------
# HELPER: firebase_upsert_order(order: Order)
# -----------------------
def test_firebase_upsert_order_function_exists():
    assert callable(firebase_upsert_order)

def test_firebase_upsert_order_with_valid_input(app_context):
    user = _create_user_in_db()
    order = _create_order_in_db(customer_id=user.id, status="NEW")
    with patch("controllers.customer_order_management_controller.firebase_upsert_order", wraps=firebase_upsert_order) as wrapped:
        wrapped(order)
        assert wrapped.called is True

def test_firebase_upsert_order_with_invalid_input(app_context):
    with pytest.raises(Exception):
        firebase_upsert_order(None)

# -----------------------
# HELPER: firebase_upsert_bill_request(bill_request: BillRequest)
# -----------------------
def test_firebase_upsert_bill_request_function_exists():
    assert callable(firebase_upsert_bill_request)

def test_firebase_upsert_bill_request_with_valid_input(app_context):
    user = _create_user_in_db()
    order = _create_order_in_db(customer_id=user.id, status="NEW")
    br = _create_bill_request_in_db(order_id=order.id, requested_by_customer_id=user.id)
    with patch(
        "controllers.customer_order_management_controller.firebase_upsert_bill_request",
        wraps=firebase_upsert_bill_request,
    ) as wrapped:
        wrapped(br)
        assert wrapped.called is True

def test_firebase_upsert_bill_request_with_invalid_input(app_context):
    with pytest.raises(Exception):
        firebase_upsert_bill_request(None)

# -----------------------
# HELPER: firebase_upsert_feedback(feedback: Feedback)
# -----------------------
def test_firebase_upsert_feedback_function_exists():
    assert callable(firebase_upsert_feedback)

def test_firebase_upsert_feedback_with_valid_input(app_context):
    user = _create_user_in_db()
    order = _create_order_in_db(customer_id=user.id, status="NEW")
    fb = _create_feedback_in_db(order_id=order.id, customer_id=user.id, rating=5, comment="ok")
    with patch(
        "controllers.customer_order_management_controller.firebase_upsert_feedback",
        wraps=firebase_upsert_feedback,
    ) as wrapped:
        wrapped(fb)
        assert wrapped.called is True

def test_firebase_upsert_feedback_with_invalid_input(app_context):
    with pytest.raises(Exception):
        firebase_upsert_feedback(None)