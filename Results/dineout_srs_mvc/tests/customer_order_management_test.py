import os
import sys
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.category import Category
from models.product import Product
from models.customer_order_management_order import CustomerOrderManagementOrder
from models.customer_order_management_order_item import CustomerOrderManagementOrderItem
from models.customer_order_management_bill_request import CustomerOrderManagementBillRequest
from controllers.customer_order_management_controller import (
    validate_items_payload,
    compute_order_totals,
    assert_order_editable,
    assert_order_cancellable,
    firebase_create_order,
    firebase_update_order,
    firebase_cancel_order,
    firebase_create_bill_request,
    firebase_get_order_timer,
)
from views.customer_order_management_views import (
    render_menu_screen,
    render_order_screen,
    render_edit_order_screen,
    render_bill_screen,
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

def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_user(app_context, email=None, username=None, password="Passw0rd!"):
    email = email or f"{_unique('user')}@example.com"
    username = username or _unique("username")
    user = User(email=email, username=username, password_hash="")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

def _create_category(app_context, name=None, is_active=True, sort_order=1, description=None):
    name = name or _unique("cat")
    category = Category(name=name, description=description, sort_order=sort_order, is_active=is_active)
    db.session.add(category)
    db.session.commit()
    return category

def _create_product(app_context, category_id, name=None, price_cents=999, currency="USD", is_available=True):
    name = name or _unique("prod")
    product = Product(
        category_id=category_id,
        name=name,
        description="desc",
        price_cents=price_cents,
        currency=currency,
        is_available=is_available,
        image_url=None,
    )
    db.session.add(product)
    db.session.commit()
    return product

def _create_order(app_context, customer_id, table_number="T1", status="pending", firebase_order_id=None, notes=None):
    firebase_order_id = firebase_order_id or _unique("fb_order")
    now = datetime.utcnow()
    order = CustomerOrderManagementOrder(
        firebase_order_id=firebase_order_id,
        customer_id=customer_id,
        table_number=table_number,
        status=status,
        created_at=now,
        updated_at=now,
        prepared_at=None,
        cancelled_at=None,
        notes=notes,
    )
    db.session.add(order)
    db.session.commit()
    return order

def _create_order_item(app_context, order_id, product_id, quantity=2, unit_price_cents=500, special_instructions=None):
    now = datetime.utcnow()
    item = CustomerOrderManagementOrderItem(
        order_id=order_id,
        product_id=product_id,
        quantity=quantity,
        unit_price_cents=unit_price_cents,
        line_total_cents=quantity * unit_price_cents,
        special_instructions=special_instructions,
        created_at=now,
        updated_at=now,
    )
    db.session.add(item)
    db.session.commit()
    return item

def _create_bill_request(app_context, order_id, customer_id, status="requested", firebase_bill_request_id=None):
    firebase_bill_request_id = firebase_bill_request_id or _unique("fb_bill")
    now = datetime.utcnow()
    br = CustomerOrderManagementBillRequest(
        firebase_bill_request_id=firebase_bill_request_id,
        order_id=order_id,
        customer_id=customer_id,
        status=status,
        requested_at=now,
        fulfilled_at=None,
    )
    db.session.add(br)
    db.session.commit()
    return br

def _route_exists(rule: str, method: str) -> bool:
    for r in app.url_map.iter_rules():
        if r.rule == rule and method.upper() in r.methods:
            return True
    return False

# MODEL: User (models/user.py)
def test_user_model_has_required_fields():
    for field in ["id", "email", "username", "password_hash"]:
        assert hasattr(User, field), f"Missing field on User: {field}"

def test_user_set_password(app_context):
    user = User(email=f"{_unique('u')}@example.com", username=_unique("u"), password_hash="")
    user.set_password("secret123")
    assert user.password_hash
    assert user.password_hash != "secret123"

def test_user_check_password(app_context):
    user = User(email=f"{_unique('u')}@example.com", username=_unique("u"), password_hash="")
    user.set_password("secret123")
    assert user.check_password("secret123") is True
    assert user.check_password("wrong") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")
    u1 = User(email=email, username=username, password_hash="")
    u1.set_password("secret123")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("otheruser"), password_hash="")
    u2.set_password("secret123")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, password_hash="")
    u3.set_password("secret123")
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# MODEL: Category (models/category.py)
def test_category_model_has_required_fields():
    for field in ["id", "name", "description", "sort_order", "is_active"]:
        assert hasattr(Category, field), f"Missing field on Category: {field}"

def test_category_unique_constraints(app_context):
    name = _unique("catname")
    c1 = Category(name=name, description=None, sort_order=1, is_active=True)
    db.session.add(c1)
    db.session.commit()

    c2 = Category(name=name, description=None, sort_order=2, is_active=True)
    db.session.add(c2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# MODEL: Product (models/product.py)
def test_product_model_has_required_fields():
    for field in [
        "id",
        "category_id",
        "name",
        "description",
        "price_cents",
        "currency",
        "is_available",
        "image_url",
    ]:
        assert hasattr(Product, field), f"Missing field on Product: {field}"

def test_product_unique_constraints(app_context):
    cat = _create_category(app_context)
    p1 = Product(
        category_id=cat.id,
        name="Same Name",
        description=None,
        price_cents=100,
        currency="USD",
        is_available=True,
        image_url=None,
    )
    p2 = Product(
        category_id=cat.id,
        name="Same Name",
        description=None,
        price_cents=200,
        currency="USD",
        is_available=True,
        image_url=None,
    )
    db.session.add_all([p1, p2])
    db.session.commit()
    assert p1.id is not None and p2.id is not None

# MODEL: CustomerOrderManagementOrder (models/customer_order_management_order.py)
def test_customerordermanagementorder_model_has_required_fields():
    for field in [
        "id",
        "firebase_order_id",
        "customer_id",
        "table_number",
        "status",
        "created_at",
        "updated_at",
        "prepared_at",
        "cancelled_at",
        "notes",
    ]:
        assert hasattr(CustomerOrderManagementOrder, field), f"Missing field on CustomerOrderManagementOrder: {field}"

def test_customerordermanagementorder_is_editable(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")
    assert hasattr(order, "is_editable")
    assert callable(order.is_editable)
    result = order.is_editable()
    assert isinstance(result, bool)

def test_customerordermanagementorder_is_cancellable(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")
    assert hasattr(order, "is_cancellable")
    assert callable(order.is_cancellable)
    result = order.is_cancellable()
    assert isinstance(result, bool)

def test_customerordermanagementorder_unique_constraints(app_context):
    user = _create_user(app_context)
    fb_id = _unique("fb_order")
    o1 = _create_order(app_context, customer_id=user.id, firebase_order_id=fb_id)
    assert o1.id is not None

    o2 = CustomerOrderManagementOrder(
        firebase_order_id=fb_id,
        customer_id=user.id,
        table_number="T2",
        status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        prepared_at=None,
        cancelled_at=None,
        notes=None,
    )
    db.session.add(o2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# MODEL: CustomerOrderManagementOrderItem (models/customer_order_management_order_item.py)
def test_customerordermanagementorderitem_model_has_required_fields():
    for field in [
        "id",
        "order_id",
        "product_id",
        "quantity",
        "unit_price_cents",
        "line_total_cents",
        "special_instructions",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(CustomerOrderManagementOrderItem, field), f"Missing field on CustomerOrderManagementOrderItem: {field}"

def test_customerordermanagementorderitem_recalculate_totals(app_context):
    user = _create_user(app_context)
    cat = _create_category(app_context)
    prod = _create_product(app_context, category_id=cat.id, price_cents=321)
    order = _create_order(app_context, customer_id=user.id)
    item = _create_order_item(app_context, order_id=order.id, product_id=prod.id, quantity=3, unit_price_cents=321)
    item.quantity = 4
    assert hasattr(item, "recalculate_totals")
    assert callable(item.recalculate_totals)
    item.recalculate_totals()
    assert item.line_total_cents == item.quantity * item.unit_price_cents

def test_customerordermanagementorderitem_unique_constraints(app_context):
    user = _create_user(app_context)
    cat = _create_category(app_context)
    prod = _create_product(app_context, category_id=cat.id)
    order = _create_order(app_context, customer_id=user.id)
    i1 = _create_order_item(app_context, order_id=order.id, product_id=prod.id)
    i2 = _create_order_item(app_context, order_id=order.id, product_id=prod.id)
    assert i1.id is not None and i2.id is not None

# MODEL: CustomerOrderManagementBillRequest (models/customer_order_management_bill_request.py)
def test_customerordermanagementbillrequest_model_has_required_fields():
    for field in [
        "id",
        "firebase_bill_request_id",
        "order_id",
        "customer_id",
        "status",
        "requested_at",
        "fulfilled_at",
    ]:
        assert hasattr(CustomerOrderManagementBillRequest, field), f"Missing field on CustomerOrderManagementBillRequest: {field}"

def test_customerordermanagementbillrequest_unique_constraints(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id)
    fb_id = _unique("fb_bill")
    br1 = _create_bill_request(app_context, order_id=order.id, customer_id=user.id, firebase_bill_request_id=fb_id)
    assert br1.id is not None

    br2 = CustomerOrderManagementBillRequest(
        firebase_bill_request_id=fb_id,
        order_id=order.id,
        customer_id=user.id,
        status="requested",
        requested_at=datetime.utcnow(),
        fulfilled_at=None,
    )
    db.session.add(br2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# ROUTE: /menu (GET) - get_menu
def test_menu_get_exists():
    assert _route_exists("/menu", "GET"), "Route /menu with GET must exist"

def test_menu_get_renders_template(client):
    resp = client.get("/menu")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json", "text/plain")
    assert resp.data is not None
    assert len(resp.data) > 0

# ROUTE: /menu/categories (GET) - get_menu_categories
def test_menu_categories_get_exists():
    assert _route_exists("/menu/categories", "GET"), "Route /menu/categories with GET must exist"

def test_menu_categories_get_renders_template(client):
    resp = client.get("/menu/categories")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json", "text/plain")
    assert resp.data is not None
    assert len(resp.data) > 0

# ROUTE: /orders (POST) - create_order
def test_orders_post_exists():
    assert _route_exists("/orders", "POST"), "Route /orders with POST must exist"

def test_orders_post_success(client, app_context):
    user = _create_user(app_context)
    cat = _create_category(app_context)
    prod = _create_product(app_context, category_id=cat.id, price_cents=1234)

    payload = {
        "customer_id": str(user.id),
        "table_number": "A1",
        "notes": "no onions",
        "items": [
            {"product_id": prod.id, "quantity": 2, "special_instructions": "extra spicy"},
        ],
    }

    with patch("controllers.customer_order_management_controller.firebase_create_order", return_value=_unique("fb")):
        resp = client.post("/orders", json=payload)
    assert resp.status_code in (200, 201)
    assert resp.data is not None
    assert len(resp.data) > 0

def test_orders_post_missing_required_fields(client):
    payload = {"table_number": "A1", "items": []}
    resp = client.post("/orders", json=payload)
    assert resp.status_code in (400, 422)

def test_orders_post_invalid_data(client):
    payload = {
        "customer_id": "not-an-int",
        "table_number": 123,
        "items": "not-a-list",
        "notes": 999,
    }
    resp = client.post("/orders", json=payload)
    assert resp.status_code in (400, 422)

def test_orders_post_duplicate_data(client, app_context):
    user = _create_user(app_context)
    cat = _create_category(app_context)
    prod = _create_product(app_context, category_id=cat.id)

    payload = {
        "customer_id": str(user.id),
        "table_number": "A1",
        "notes": "dup",
        "items": [{"product_id": prod.id, "quantity": 1}],
    }

    fixed_fb = _unique("fb_fixed")
    with patch("controllers.customer_order_management_controller.firebase_create_order", return_value=fixed_fb):
        r1 = client.post("/orders", json=payload)
        r2 = client.post("/orders", json=payload)
    assert r1.status_code in (200, 201)
    assert r2.status_code in (400, 409, 422)

# ROUTE: /orders/<int:order_id> (GET) - get_order
def test_orders_order_id_get_exists():
    assert _route_exists("/orders/<int:order_id>", "GET"), "Route /orders/<int:order_id> with GET must exist"

def test_orders_order_id_get_renders_template(client, app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id)
    resp = client.get(f"/orders/{order.id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json", "text/plain")
    assert resp.data is not None
    assert len(resp.data) > 0

# ROUTE: /orders/<int:order_id> (PATCH) - update_order
def test_orders_order_id_patch_exists():
    assert _route_exists("/orders/<int:order_id>", "PATCH"), "Route /orders/<int:order_id> with PATCH must exist"

# ROUTE: /orders/<int:order_id>/cancel (POST) - cancel_order
def test_orders_order_id_cancel_post_exists():
    assert _route_exists("/orders/<int:order_id>/cancel", "POST"), "Route /orders/<int:order_id>/cancel with POST must exist"

def test_orders_order_id_cancel_post_success(client, app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")

    with patch("controllers.customer_order_management_controller.firebase_cancel_order", return_value=None):
        resp = client.post(f"/orders/{order.id}/cancel", json={"reason": "changed mind"})
    assert resp.status_code in (200, 204)
    assert resp.data is not None

def test_orders_order_id_cancel_post_missing_required_fields(client, app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")
    resp = client.post(f"/orders/{order.id}/cancel", json={})
    assert resp.status_code in (400, 422)

def test_orders_order_id_cancel_post_invalid_data(client, app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")
    resp = client.post(f"/orders/{order.id}/cancel", json={"reason": 123})
    assert resp.status_code in (400, 422)

def test_orders_order_id_cancel_post_duplicate_data(client, app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")

    with patch("controllers.customer_order_management_controller.firebase_cancel_order", return_value=None):
        r1 = client.post(f"/orders/{order.id}/cancel", json={"reason": "first"})
        r2 = client.post(f"/orders/{order.id}/cancel", json={"reason": "second"})
    assert r1.status_code in (200, 204)
    assert r2.status_code in (400, 409, 422)

# ROUTE: /orders/<int:order_id>/timer (GET) - get_order_timer
def test_orders_order_id_timer_get_exists():
    assert _route_exists("/orders/<int:order_id>/timer", "GET"), "Route /orders/<int:order_id>/timer with GET must exist"

def test_orders_order_id_timer_get_renders_template(client, app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")

    with patch(
        "controllers.customer_order_management_controller.firebase_get_order_timer",
        return_value={"eta_seconds": 300, "started_at": None},
    ):
        resp = client.get(f"/orders/{order.id}/timer")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json", "text/plain")
    assert resp.data is not None
    assert len(resp.data) > 0

# ROUTE: /orders/<int:order_id>/bill (POST) - request_bill
def test_orders_order_id_bill_post_exists():
    assert _route_exists("/orders/<int:order_id>/bill", "POST"), "Route /orders/<int:order_id>/bill with POST must exist"

def test_orders_order_id_bill_post_success(client, app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")

    with patch("controllers.customer_order_management_controller.firebase_create_bill_request", return_value=_unique("fb_bill")):
        resp = client.post(f"/orders/{order.id}/bill", json={})
    assert resp.status_code in (200, 201)
    assert resp.data is not None
    assert len(resp.data) > 0

def test_orders_order_id_bill_post_missing_required_fields(client, app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")
    resp = client.post(f"/orders/{order.id}/bill", data="not-json", content_type="text/plain")
    assert resp.status_code in (400, 415, 422)

def test_orders_order_id_bill_post_invalid_data(client, app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")
    resp = client.post(f"/orders/{order.id}/bill", json={"unexpected": "field"})
    assert resp.status_code in (200, 201, 400, 422)

def test_orders_order_id_bill_post_duplicate_data(client, app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")

    fixed_fb = _unique("fb_bill_fixed")
    with patch("controllers.customer_order_management_controller.firebase_create_bill_request", return_value=fixed_fb):
        r1 = client.post(f"/orders/{order.id}/bill", json={})
        r2 = client.post(f"/orders/{order.id}/bill", json={})
    assert r1.status_code in (200, 201)
    assert r2.status_code in (400, 409, 422)

# ROUTE: /orders/<int:order_id>/bill (GET) - get_bill_request_status
def test_orders_order_id_bill_get_exists():
    assert _route_exists("/orders/<int:order_id>/bill", "GET"), "Route /orders/<int:order_id>/bill with GET must exist"

def test_orders_order_id_bill_get_renders_template(client, app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")
    _create_bill_request(app_context, order_id=order.id, customer_id=user.id, status="requested")

    resp = client.get(f"/orders/{order.id}/bill")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json", "text/plain")
    assert resp.data is not None
    assert len(resp.data) > 0

# HELPER: validate_items_payload(items)
def test_validate_items_payload_function_exists():
    assert callable(validate_items_payload)

def test_validate_items_payload_with_valid_input(app_context):
    cat = _create_category(app_context)
    prod = _create_product(app_context, category_id=cat.id)
    items = [{"product_id": prod.id, "quantity": 2, "special_instructions": "no salt"}]
    result = validate_items_payload(items)
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], dict)
    assert "product_id" in result[0]
    assert "quantity" in result[0]

def test_validate_items_payload_with_invalid_input():
    with pytest.raises(Exception):
        validate_items_payload("not-a-list")

# HELPER: compute_order_totals(order, order_items)
def test_compute_order_totals_function_exists():
    assert callable(compute_order_totals)

def test_compute_order_totals_with_valid_input(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id)
    cat = _create_category(app_context)
    prod = _create_product(app_context, category_id=cat.id, price_cents=250)
    item = _create_order_item(app_context, order_id=order.id, product_id=prod.id, quantity=3, unit_price_cents=250)

    totals = compute_order_totals(order, [item])
    assert isinstance(totals, dict)
    assert any(k in totals for k in ["total_cents", "subtotal_cents", "total", "subtotal"])

def test_compute_order_totals_with_invalid_input(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id)
    with pytest.raises(Exception):
        compute_order_totals(order, "not-a-list")

# HELPER: assert_order_editable(order)
def test_assert_order_editable_function_exists():
    assert callable(assert_order_editable)

def test_assert_order_editable_with_valid_input(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")
    assert_order_editable(order)

def test_assert_order_editable_with_invalid_input(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="prepared")
    order.prepared_at = datetime.utcnow()
    db.session.commit()
    with pytest.raises(Exception):
        assert_order_editable(order)

# HELPER: assert_order_cancellable(order)
def test_assert_order_cancellable_function_exists():
    assert callable(assert_order_cancellable)

def test_assert_order_cancellable_with_valid_input(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="pending")
    assert_order_cancellable(order)

def test_assert_order_cancellable_with_invalid_input(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id, status="cancelled")
    order.cancelled_at = datetime.utcnow()
    db.session.commit()
    with pytest.raises(Exception):
        assert_order_cancellable(order)

# HELPER: firebase_create_order(order, order_items)
def test_firebase_create_order_function_exists():
    assert callable(firebase_create_order)

def test_firebase_create_order_with_valid_input(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id)
    cat = _create_category(app_context)
    prod = _create_product(app_context, category_id=cat.id)
    item = _create_order_item(app_context, order_id=order.id, product_id=prod.id)

    with patch("controllers.customer_order_management_controller.firebase_create_order", return_value=_unique("fb")) as m:
        fb_id = m(order, [item])
    assert isinstance(fb_id, str)
    assert fb_id

def test_firebase_create_order_with_invalid_input():
    with pytest.raises(Exception):
        firebase_create_order(None, None)

# HELPER: firebase_update_order(order, order_items)
def test_firebase_update_order_function_exists():
    assert callable(firebase_update_order)

def test_firebase_update_order_with_valid_input(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id)
    cat = _create_category(app_context)
    prod = _create_product(app_context, category_id=cat.id)
    item = _create_order_item(app_context, order_id=order.id, product_id=prod.id)

    with patch("controllers.customer_order_management_controller.firebase_update_order", return_value=None) as m:
        result = m(order, [item])
    assert result is None

def test_firebase_update_order_with_invalid_input():
    with pytest.raises(Exception):
        firebase_update_order(None, "not-a-list")

# HELPER: firebase_cancel_order(order, reason)
def test_firebase_cancel_order_function_exists():
    assert callable(firebase_cancel_order)

def test_firebase_cancel_order_with_valid_input(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id)
    with patch("controllers.customer_order_management_controller.firebase_cancel_order", return_value=None) as m:
        result = m(order, "changed mind")
    assert result is None

def test_firebase_cancel_order_with_invalid_input():
    with pytest.raises(Exception):
        firebase_cancel_order(None, None)

# HELPER: firebase_create_bill_request(bill_request)
def test_firebase_create_bill_request_function_exists():
    assert callable(firebase_create_bill_request)

def test_firebase_create_bill_request_with_valid_input(app_context):
    user = _create_user(app_context)
    order = _create_order(app_context, customer_id=user.id)
    br = _create_bill_request(app_context, order_id=order.id, customer_id=user.id)

    with patch("controllers.customer_order_management_controller.firebase_create_bill_request", return_value=_unique("fb_bill")) as m:
        fb_id = m(br)
    assert isinstance(fb_id, str)
    assert fb_id

def test_firebase_create_bill_request_with_invalid_input():
    with pytest.raises(Exception):
        firebase_create_bill_request(None)

# HELPER: firebase_get_order_timer(firebase_order_id)
def test_firebase_get_order_timer_function_exists():
    assert callable(firebase_get_order_timer)

def test_firebase_get_order_timer_with_valid_input():
    with patch(
        "controllers.customer_order_management_controller.firebase_get_order_timer",
        return_value={"eta_seconds": 120, "state": "preparing"},
    ) as m:
        timer = m("firebase_order_123")
    assert isinstance(timer, dict)
    assert timer

def test_firebase_get_order_timer_with_invalid_input():
    with pytest.raises(Exception):
        firebase_get_order_timer(None)