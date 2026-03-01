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
from models.customer_order_management_order import Order
from models.customer_order_management_order_item import OrderItem
from models.customer_order_management_bill_request import BillRequest
from models.customer_order_management_feedback import Feedback
from controllers.customer_order_management_controller import (
    generate_id,
    assert_order_editable,
    serialize_menu,
    serialize_order,
    firebase_upsert_order,
    firebase_write_bill_request,
    firebase_write_feedback,
)
from views.customer_order_management_views import menu_screen, order_timer_screen, feedback_screen

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

def _create_category(name=None, description=None):
    c = Category(name=name or _unique("cat"), description=description)
    db.session.add(c)
    db.session.commit()
    return c

def _create_product(
    category_id: int,
    name=None,
    description=None,
    price_cents: int = 1000,
    is_available: bool = True,
    image_url=None,
):
    p = Product(
        category_id=category_id,
        name=name or _unique("prod"),
        description=description,
        price_cents=price_cents,
        is_available=is_available,
        image_url=image_url,
        created_at=datetime.utcnow(),
    )
    db.session.add(p)
    db.session.commit()
    return p

def _create_user(email=None, username=None, password="Password123!"):
    u = User(
        email=email or f"{_unique('u')}@example.com",
        username=username or _unique("user"),
        password_hash="",
        created_at=datetime.utcnow(),
    )
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u

def _create_order(
    table_id=None,
    customer_id=None,
    status="DRAFT",
    currency="USD",
    special_instructions=None,
):
    oid = generate_id("ord")
    o = Order(
        id=oid,
        table_id=table_id or _unique("table"),
        customer_id=customer_id,
        status=status,
        currency=currency,
        subtotal_cents=0,
        tax_cents=0,
        service_charge_cents=0,
        total_cents=0,
        special_instructions=special_instructions,
        placed_at=None,
        preparing_at=None,
        cancelled_at=None,
        billed_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(o)
    db.session.commit()
    return o

def _create_order_item(
    order_id: str,
    product_id: int,
    product_name_snapshot=None,
    unit_price_cents_snapshot: int = 500,
    quantity: int = 1,
    notes=None,
):
    iid = generate_id("item")
    it = OrderItem(
        id=iid,
        order_id=order_id,
        product_id=product_id,
        product_name_snapshot=product_name_snapshot or _unique("snap"),
        unit_price_cents_snapshot=unit_price_cents_snapshot,
        quantity=quantity,
        notes=notes,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(it)
    db.session.commit()
    return it

def _create_bill_request(order_id: str, table_id: str, status="REQUESTED"):
    bid = generate_id("bill")
    br = BillRequest(
        id=bid,
        order_id=order_id,
        table_id=table_id,
        status=status,
        requested_at=datetime.utcnow(),
        fulfilled_at=None,
    )
    db.session.add(br)
    db.session.commit()
    return br

def _create_feedback(order_id: str, table_id: str, food_rating=None, service_rating=None, comments=None):
    fid = generate_id("fb")
    fb = Feedback(
        id=fid,
        order_id=order_id,
        table_id=table_id,
        food_rating=food_rating,
        service_rating=service_rating,
        comments=comments,
        created_at=datetime.utcnow(),
    )
    db.session.add(fb)
    db.session.commit()
    return fb

# MODEL: User (models/user.py)
def test_user_model_has_required_fields():
    for field in ["id", "email", "username", "password_hash", "created_at"]:
        assert hasattr(User, field), f"Missing field on User: {field}"

def test_user_set_password():
    u = User(email=f"{_unique('u')}@example.com", username=_unique("user"), password_hash="", created_at=datetime.utcnow())
    u.set_password("Password123!")
    assert u.password_hash
    assert u.password_hash != "Password123!"

def test_user_check_password():
    u = User(email=f"{_unique('u')}@example.com", username=_unique("user"), password_hash="", created_at=datetime.utcnow())
    u.set_password("Password123!")
    assert u.check_password("Password123!") is True
    assert u.check_password("wrong") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('u')}@example.com"
    username = _unique("user")
    u1 = User(email=email, username=username, password_hash="", created_at=datetime.utcnow())
    u1.set_password("Password123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("user2"), password_hash="", created_at=datetime.utcnow())
    u2.set_password("Password123!")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('u3')}@example.com", username=username, password_hash="", created_at=datetime.utcnow())
    u3.set_password("Password123!")
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()

# MODEL: Category (models/category.py)
def test_category_model_has_required_fields():
    for field in ["id", "name", "description"]:
        assert hasattr(Category, field), f"Missing field on Category: {field}"

def test_category_unique_constraints(app_context):
    name = _unique("cat")
    c1 = Category(name=name, description="d1")
    db.session.add(c1)
    db.session.commit()

    c2 = Category(name=name, description="d2")
    db.session.add(c2)
    with pytest.raises(Exception):
        db.session.commit()

# MODEL: Product (models/product.py)
def test_product_model_has_required_fields():
    for field in ["id", "category_id", "name", "description", "price_cents", "is_available", "image_url", "created_at"]:
        assert hasattr(Product, field), f"Missing field on Product: {field}"

def test_product_unique_constraints(app_context):
    cat = _create_category()
    name = _unique("prod")
    p1 = Product(
        category_id=cat.id,
        name=name,
        description="d1",
        price_cents=100,
        is_available=True,
        image_url=None,
        created_at=datetime.utcnow(),
    )
    p2 = Product(
        category_id=cat.id,
        name=name,
        description="d2",
        price_cents=200,
        is_available=True,
        image_url=None,
        created_at=datetime.utcnow(),
    )
    db.session.add_all([p1, p2])
    db.session.commit()
    assert Product.query.filter_by(name=name).count() == 2

# MODEL: Order (models/customer_order_management_order.py)
def test_order_model_has_required_fields():
    fields = [
        "id",
        "table_id",
        "customer_id",
        "status",
        "currency",
        "subtotal_cents",
        "tax_cents",
        "service_charge_cents",
        "total_cents",
        "special_instructions",
        "placed_at",
        "preparing_at",
        "cancelled_at",
        "billed_at",
        "created_at",
        "updated_at",
    ]
    for field in fields:
        assert hasattr(Order, field), f"Missing field on Order: {field}"

def test_order_is_editable(app_context):
    o = _create_order(status="DRAFT")
    assert hasattr(o, "is_editable")
    assert callable(o.is_editable)
    assert o.is_editable() is True

    o2 = _create_order(status="PLACED")
    assert o2.is_editable() is True

    o3 = _create_order(status="PREPARING")
    assert o3.is_editable() is False

    o4 = _create_order(status="CANCELLED")
    assert o4.is_editable() is False

def test_order_recalculate_totals(app_context):
    o = _create_order(status="DRAFT")
    cat = _create_category()
    p1 = _create_product(category_id=cat.id, price_cents=1000, is_available=True)
    p2 = _create_product(category_id=cat.id, price_cents=2500, is_available=True)
    _create_order_item(order_id=o.id, product_id=p1.id, unit_price_cents_snapshot=1000, quantity=2)
    _create_order_item(order_id=o.id, product_id=p2.id, unit_price_cents_snapshot=2500, quantity=1)

    assert hasattr(o, "recalculate_totals")
    o.recalculate_totals(tax_rate=0.1, service_charge_rate=0.05)
    db.session.refresh(o)

    assert o.subtotal_cents == 4500
    assert o.tax_cents == 450
    assert o.service_charge_cents == 225
    assert o.total_cents == 5175

def test_order_unique_constraints(app_context):
    oid = generate_id("ord")
    o1 = Order(
        id=oid,
        table_id=_unique("table"),
        customer_id=None,
        status="DRAFT",
        currency="USD",
        subtotal_cents=0,
        tax_cents=0,
        service_charge_cents=0,
        total_cents=0,
        special_instructions=None,
        placed_at=None,
        preparing_at=None,
        cancelled_at=None,
        billed_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(o1)
    db.session.commit()

    o2 = Order(
        id=oid,
        table_id=_unique("table2"),
        customer_id=None,
        status="DRAFT",
        currency="USD",
        subtotal_cents=0,
        tax_cents=0,
        service_charge_cents=0,
        total_cents=0,
        special_instructions=None,
        placed_at=None,
        preparing_at=None,
        cancelled_at=None,
        billed_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(o2)
    with pytest.raises(Exception):
        db.session.commit()

# MODEL: OrderItem (models/customer_order_management_order_item.py)
def test_orderitem_model_has_required_fields():
    fields = [
        "id",
        "order_id",
        "product_id",
        "product_name_snapshot",
        "unit_price_cents_snapshot",
        "quantity",
        "notes",
        "created_at",
        "updated_at",
    ]
    for field in fields:
        assert hasattr(OrderItem, field), f"Missing field on OrderItem: {field}"

def test_orderitem_line_total_cents(app_context):
    o = _create_order()
    cat = _create_category()
    p = _create_product(category_id=cat.id, price_cents=999)
    it = _create_order_item(order_id=o.id, product_id=p.id, unit_price_cents_snapshot=999, quantity=3)
    assert hasattr(it, "line_total_cents")
    assert callable(it.line_total_cents)
    assert it.line_total_cents() == 2997

def test_orderitem_unique_constraints(app_context):
    o = _create_order()
    cat = _create_category()
    p = _create_product(category_id=cat.id, price_cents=100)
    iid = generate_id("item")
    it1 = OrderItem(
        id=iid,
        order_id=o.id,
        product_id=p.id,
        product_name_snapshot="snap",
        unit_price_cents_snapshot=100,
        quantity=1,
        notes=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(it1)
    db.session.commit()

    it2 = OrderItem(
        id=iid,
        order_id=o.id,
        product_id=p.id,
        product_name_snapshot="snap2",
        unit_price_cents_snapshot=100,
        quantity=2,
        notes=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(it2)
    with pytest.raises(Exception):
        db.session.commit()

# MODEL: BillRequest (models/customer_order_management_bill_request.py)
def test_billrequest_model_has_required_fields():
    for field in ["id", "order_id", "table_id", "status", "requested_at", "fulfilled_at"]:
        assert hasattr(BillRequest, field), f"Missing field on BillRequest: {field}"

def test_billrequest_unique_constraints(app_context):
    o = _create_order()
    bid = generate_id("bill")
    br1 = BillRequest(
        id=bid,
        order_id=o.id,
        table_id=o.table_id,
        status="REQUESTED",
        requested_at=datetime.utcnow(),
        fulfilled_at=None,
    )
    db.session.add(br1)
    db.session.commit()

    br2 = BillRequest(
        id=bid,
        order_id=o.id,
        table_id=o.table_id,
        status="REQUESTED",
        requested_at=datetime.utcnow(),
        fulfilled_at=None,
    )
    db.session.add(br2)
    with pytest.raises(Exception):
        db.session.commit()

# MODEL: Feedback (models/customer_order_management_feedback.py)
def test_feedback_model_has_required_fields():
    for field in ["id", "order_id", "table_id", "food_rating", "service_rating", "comments", "created_at"]:
        assert hasattr(Feedback, field), f"Missing field on Feedback: {field}"

def test_feedback_unique_constraints(app_context):
    o = _create_order()
    fid = generate_id("fb")
    fb1 = Feedback(
        id=fid,
        order_id=o.id,
        table_id=o.table_id,
        food_rating=5,
        service_rating=4,
        comments="ok",
        created_at=datetime.utcnow(),
    )
    db.session.add(fb1)
    db.session.commit()

    fb2 = Feedback(
        id=fid,
        order_id=o.id,
        table_id=o.table_id,
        food_rating=3,
        service_rating=3,
        comments="dup",
        created_at=datetime.utcnow(),
    )
    db.session.add(fb2)
    with pytest.raises(Exception):
        db.session.commit()

# ROUTE: /menu (GET) - get_menu
def test_menu_get_exists(client):
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert "/menu" in rules
    assert "GET" in rules["/menu"]

def test_menu_get_renders_template(client, app_context):
    cat = _create_category()
    _create_product(category_id=cat.id, is_available=True)
    resp = client.get("/menu")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")
    if resp.mimetype == "text/html":
        assert b"<" in resp.data

# ROUTE: /orders (POST) - create_order
def test_orders_post_exists(client):
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert "/orders" in rules
    assert "POST" in rules["/orders"]

def test_orders_post_success(client):
    table_id = _unique("table")
    resp = client.post("/orders", data={"table_id": table_id, "special_instructions": "no onions"})
    assert resp.status_code in (200, 201)
    assert resp.mimetype in ("application/json", "text/html")
    with app.app_context():
        assert Order.query.filter_by(table_id=table_id).count() == 1

def test_orders_post_missing_required_fields(client):
    resp = client.post("/orders", data={})
    assert resp.status_code in (400, 422)

def test_orders_post_invalid_data(client):
    resp = client.post("/orders", data={"table_id": ""})
    assert resp.status_code in (400, 422)

def test_orders_post_duplicate_data(client):
    table_id = _unique("table")
    r1 = client.post("/orders", data={"table_id": table_id})
    assert r1.status_code in (200, 201)
    r2 = client.post("/orders", data={"table_id": table_id})
    assert r2.status_code in (200, 201, 409)

# ROUTE: /orders/<string:order_id> (GET) - get_order
def test_orders_order_id_get_exists(client):
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert "/orders/<string:order_id>" in rules
    assert "GET" in rules["/orders/<string:order_id>"]

def test_orders_order_id_get_renders_template(client, app_context):
    o = _create_order()
    resp = client.get(f"/orders/{o.id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")
    if resp.mimetype == "text/html":
        assert b"<" in resp.data

# ROUTE: /orders/<string:order_id>/items (POST) - add_order_item
def test_orders_order_id_items_post_exists(client):
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert "/orders/<string:order_id>/items" in rules
    assert "POST" in rules["/orders/<string:order_id>/items"]

def test_orders_order_id_items_post_success(client, app_context):
    cat = _create_category()
    p = _create_product(category_id=cat.id, price_cents=1234, is_available=True)
    o = _create_order()
    resp = client.post(f"/orders/{o.id}/items", data={"product_id": str(p.id), "quantity": "2", "notes": "extra spicy"})
    assert resp.status_code in (200, 201)
    with app.app_context():
        assert OrderItem.query.filter_by(order_id=o.id, product_id=p.id).count() == 1

def test_orders_order_id_items_post_missing_required_fields(client, app_context):
    o = _create_order()
    resp = client.post(f"/orders/{o.id}/items", data={})
    assert resp.status_code in (400, 422)

def test_orders_order_id_items_post_invalid_data(client, app_context):
    o = _create_order()
    resp = client.post(f"/orders/{o.id}/items", data={"product_id": "not-an-int", "quantity": "-1"})
    assert resp.status_code in (400, 422)

def test_orders_order_id_items_post_duplicate_data(client, app_context):
    cat = _create_category()
    p = _create_product(category_id=cat.id, price_cents=500, is_available=True)
    o = _create_order()
    r1 = client.post(f"/orders/{o.id}/items", data={"product_id": str(p.id), "quantity": "1"})
    assert r1.status_code in (200, 201)
    r2 = client.post(f"/orders/{o.id}/items", data={"product_id": str(p.id), "quantity": "1"})
    assert r2.status_code in (200, 201, 409)

# ROUTE: /orders/<string:order_id>/items/<string:item_id> (PATCH) - update_order_item
def test_orders_order_id_items_item_id_patch_exists(client):
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert "/orders/<string:order_id>/items/<string:item_id>" in rules
    assert "PATCH" in rules["/orders/<string:order_id>/items/<string:item_id>"]

# ROUTE: /orders/<string:order_id>/items/<string:item_id> (DELETE) - delete_order_item
def test_orders_order_id_items_item_id_delete_exists(client):
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert "/orders/<string:order_id>/items/<string:item_id>" in rules
    assert "DELETE" in rules["/orders/<string:order_id>/items/<string:item_id>"]

# ROUTE: /orders/<string:order_id>/place (POST) - place_order
def test_orders_order_id_place_post_exists(client):
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert "/orders/<string:order_id>/place" in rules
    assert "POST" in rules["/orders/<string:order_id>/place"]

def test_orders_order_id_place_post_success(client, app_context):
    cat = _create_category()
    p = _create_product(category_id=cat.id, price_cents=1000, is_available=True)
    o = _create_order(status="DRAFT")
    _create_order_item(order_id=o.id, product_id=p.id, unit_price_cents_snapshot=1000, quantity=1)

    resp = client.post(f"/orders/{o.id}/place", data={})
    assert resp.status_code in (200, 201)
    with app.app_context():
        db.session.refresh(o)
        assert o.status in ("PLACED", "PREPARING", "READY", "SERVED", "BILLED", "PAID")

def test_orders_order_id_place_post_missing_required_fields(client, app_context):
    o = _create_order(status="DRAFT")
    resp = client.post(f"/orders/{o.id}/place", data={})
    assert resp.status_code in (200, 201, 400, 422)

def test_orders_order_id_place_post_invalid_data(client, app_context):
    resp = client.post("/orders/not-a-real-order-id/place", data={})
    assert resp.status_code in (404, 400)

def test_orders_order_id_place_post_duplicate_data(client, app_context):
    cat = _create_category()
    p = _create_product(category_id=cat.id, price_cents=1000, is_available=True)
    o = _create_order(status="DRAFT")
    _create_order_item(order_id=o.id, product_id=p.id, unit_price_cents_snapshot=1000, quantity=1)

    r1 = client.post(f"/orders/{o.id}/place", data={})
    assert r1.status_code in (200, 201)
    r2 = client.post(f"/orders/{o.id}/place", data={})
    assert r2.status_code in (200, 201, 409, 400)

# ROUTE: /orders/<string:order_id>/cancel (POST) - cancel_order
def test_orders_order_id_cancel_post_exists(client):
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert "/orders/<string:order_id>/cancel" in rules
    assert "POST" in rules["/orders/<string:order_id>/cancel"]

def test_orders_order_id_cancel_post_success(client, app_context):
    o = _create_order(status="PLACED")
    resp = client.post(f"/orders/{o.id}/cancel", data={"reason": "changed mind"})
    assert resp.status_code in (200, 201)
    with app.app_context():
        db.session.refresh(o)
        assert o.status == "CANCELLED"

def test_orders_order_id_cancel_post_missing_required_fields(client, app_context):
    o = _create_order(status="PLACED")
    resp = client.post(f"/orders/{o.id}/cancel", data={})
    assert resp.status_code in (200, 201, 400, 422)

def test_orders_order_id_cancel_post_invalid_data(client, app_context):
    resp = client.post("/orders/does-not-exist/cancel", data={"reason": "x"})
    assert resp.status_code in (404, 400)

def test_orders_order_id_cancel_post_duplicate_data(client, app_context):
    o = _create_order(status="PLACED")
    r1 = client.post(f"/orders/{o.id}/cancel", data={"reason": "x"})
    assert r1.status_code in (200, 201)
    r2 = client.post(f"/orders/{o.id}/cancel", data={"reason": "x"})
    assert r2.status_code in (200, 201, 409, 400)

# ROUTE: /orders/<string:order_id>/bill (POST) - request_bill
def test_orders_order_id_bill_post_exists(client):
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert "/orders/<string:order_id>/bill" in rules
    assert "POST" in rules["/orders/<string:order_id>/bill"]

def test_orders_order_id_bill_post_success(client, app_context):
    o = _create_order(status="SERVED")
    resp = client.post(f"/orders/{o.id}/bill", data={})
    assert resp.status_code in (200, 201)
    with app.app_context():
        db.session.refresh(o)
        assert o.status in ("BILLED", "SERVED", "PAID")

def test_orders_order_id_bill_post_missing_required_fields(client, app_context):
    o = _create_order(status="SERVED")
    resp = client.post(f"/orders/{o.id}/bill", data={})
    assert resp.status_code in (200, 201, 400, 422)

def test_orders_order_id_bill_post_invalid_data(client, app_context):
    resp = client.post("/orders/does-not-exist/bill", data={})
    assert resp.status_code in (404, 400)

def test_orders_order_id_bill_post_duplicate_data(client, app_context):
    o = _create_order(status="SERVED")
    r1 = client.post(f"/orders/{o.id}/bill", data={})
    assert r1.status_code in (200, 201)
    r2 = client.post(f"/orders/{o.id}/bill", data={})
    assert r2.status_code in (200, 201, 409, 400)

# ROUTE: /orders/<string:order_id>/feedback (POST) - submit_feedback
def test_orders_order_id_feedback_post_exists(client):
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert "/orders/<string:order_id>/feedback" in rules
    assert "POST" in rules["/orders/<string:order_id>/feedback"]

def test_orders_order_id_feedback_post_success(client, app_context):
    o = _create_order(status="BILLED")
    resp = client.post(
        f"/orders/{o.id}/feedback",
        data={"food_rating": "5", "service_rating": "4", "comments": "great"},
    )
    assert resp.status_code in (200, 201)
    with app.app_context():
        assert Feedback.query.filter_by(order_id=o.id).count() == 1

def test_orders_order_id_feedback_post_missing_required_fields(client, app_context):
    o = _create_order(status="BILLED")
    resp = client.post(f"/orders/{o.id}/feedback", data={})
    assert resp.status_code in (200, 201, 400, 422)

def test_orders_order_id_feedback_post_invalid_data(client, app_context):
    o = _create_order(status="BILLED")
    resp = client.post(
        f"/orders/{o.id}/feedback",
        data={"food_rating": "999", "service_rating": "-1", "comments": "x"},
    )
    assert resp.status_code in (400, 422)

def test_orders_order_id_feedback_post_duplicate_data(client, app_context):
    o = _create_order(status="BILLED")
    r1 = client.post(
        f"/orders/{o.id}/feedback",
        data={"food_rating": "5", "service_rating": "5", "comments": "1"},
    )
    assert r1.status_code in (200, 201)
    r2 = client.post(
        f"/orders/{o.id}/feedback",
        data={"food_rating": "4", "service_rating": "4", "comments": "2"},
    )
    assert r2.status_code in (200, 201, 409, 400)

# HELPER: generate_id(prefix: str)
def test_generate_id_function_exists():
    assert callable(generate_id)

def test_generate_id_with_valid_input():
    gid = generate_id("ord")
    assert isinstance(gid, str)
    assert len(gid) > 3
    assert gid.startswith("ord")

def test_generate_id_with_invalid_input():
    with pytest.raises(Exception):
        generate_id("")  # type: ignore[arg-type]
    with pytest.raises(Exception):
        generate_id(None)  # type: ignore[arg-type]

# HELPER: assert_order_editable(order: Order)
def test_assert_order_editable_function_exists():
    assert callable(assert_order_editable)

def test_assert_order_editable_with_valid_input(app_context):
    o = _create_order(status="DRAFT")
    assert_order_editable(o)

def test_assert_order_editable_with_invalid_input(app_context):
    o = _create_order(status="PREPARING")
    with pytest.raises(Exception):
        assert_order_editable(o)

# HELPER: serialize_menu(...)
def test_serialize_menu_function_exists():
    assert callable(serialize_menu)

def test_serialize_menu_with_valid_input(app_context):
    c = _create_category()
    p = _create_product(category_id=c.id, is_available=True)
    data = serialize_menu(categories=[c], products=[p], page=1, page_size=25, total=1)
    assert isinstance(data, dict)
    assert "page" in data and data["page"] == 1
    assert "page_size" in data and data["page_size"] == 25
    assert "total" in data and data["total"] == 1
    assert "categories" in data
    assert "products" in data

def test_serialize_menu_with_invalid_input():
    with pytest.raises(Exception):
        serialize_menu(categories=None, products=[], page=1, page_size=25, total=0)  # type: ignore[arg-type]
    with pytest.raises(Exception):
        serialize_menu(categories=[], products=None, page=1, page_size=25, total=0)  # type: ignore[arg-type]
    with pytest.raises(Exception):
        serialize_menu(categories=[], products=[], page=0, page_size=25, total=0)
    with pytest.raises(Exception):
        serialize_menu(categories=[], products=[], page=1, page_size=0, total=0)

# HELPER: serialize_order(order: Order, items: list[OrderItem])
def test_serialize_order_function_exists():
    assert callable(serialize_order)

def test_serialize_order_with_valid_input(app_context):
    o = _create_order(status="DRAFT")
    cat = _create_category()
    p = _create_product(category_id=cat.id, price_cents=1000)
    it = _create_order_item(order_id=o.id, product_id=p.id, unit_price_cents_snapshot=1000, quantity=2)
    data = serialize_order(order=o, items=[it])
    assert isinstance(data, dict)
    assert "id" in data
    assert "items" in data
    assert isinstance(data["items"], list)

def test_serialize_order_with_invalid_input(app_context):
    o = _create_order(status="DRAFT")
    with pytest.raises(Exception):
        serialize_order(order=None, items=[])  # type: ignore[arg-type]
    with pytest.raises(Exception):
        serialize_order(order=o, items=None)  # type: ignore[arg-type]

# HELPER: firebase_upsert_order(order: Order, items: list[OrderItem])
def test_firebase_upsert_order_function_exists():
    assert callable(firebase_upsert_order)

def test_firebase_upsert_order_with_valid_input(app_context):
    o = _create_order(status="DRAFT")
    cat = _create_category()
    p = _create_product(category_id=cat.id, price_cents=1000)
    it = _create_order_item(order_id=o.id, product_id=p.id, unit_price_cents_snapshot=1000, quantity=1)
    with patch("controllers.customer_order_management_controller.firebase_upsert_order", wraps=firebase_upsert_order) as fn:
        fn(o, [it])
        assert fn.call_count == 1

def test_firebase_upsert_order_with_invalid_input(app_context):
    o = _create_order(status="DRAFT")
    with pytest.raises(Exception):
        firebase_upsert_order(order=None, items=[])  # type: ignore[arg-type]
    with pytest.raises(Exception):
        firebase_upsert_order(order=o, items=None)  # type: ignore[arg-type]

# HELPER: firebase_write_bill_request(bill_request: BillRequest)
def test_firebase_write_bill_request_function_exists():
    assert callable(firebase_write_bill_request)

def test_firebase_write_bill_request_with_valid_input(app_context):
    o = _create_order(status="SERVED")
    br = _create_bill_request(order_id=o.id, table_id=o.table_id)
    with patch(
        "controllers.customer_order_management_controller.firebase_write_bill_request",
        wraps=firebase_write_bill_request,
    ) as fn:
        fn(br)
        assert fn.call_count == 1

def test_firebase_write_bill_request_with_invalid_input():
    with pytest.raises(Exception):
        firebase_write_bill_request(None)  # type: ignore[arg-type]

# HELPER: firebase_write_feedback(feedback: Feedback)
def test_firebase_write_feedback_function_exists():
    assert callable(firebase_write_feedback)

def test_firebase_write_feedback_with_valid_input(app_context):
    o = _create_order(status="BILLED")
    fb = _create_feedback(order_id=o.id, table_id=o.table_id, food_rating=5, service_rating=5, comments="ok")
    with patch(
        "controllers.customer_order_management_controller.firebase_write_feedback",
        wraps=firebase_write_feedback,
    ) as fn:
        fn(fb)
        assert fn.call_count == 1

def test_firebase_write_feedback_with_invalid_input():
    with pytest.raises(Exception):
        firebase_write_feedback(None)  # type: ignore[arg-type]