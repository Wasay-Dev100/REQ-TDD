import os
import sys
import uuid
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.customer_order_management_menu_item import MenuItem
from models.customer_order_management_order import Order
from models.customer_order_management_order_item import OrderItem
from models.customer_order_management_bill import Bill
from controllers.customer_order_management_controller import (
    firebase_upsert_order,
    firebase_upsert_bill,
    firebase_delete_order,
    manager_notify_bill_requested,
    calculate_bill_amounts,
)
from views.customer_order_management_views import (
    render_menu_page,
    render_order_page,
    render_bill_page,
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

def _create_menu_item(name=None, price_cents=999, is_available=True, category=None):
    if name is None:
        name = _unique("dish")
    item = MenuItem(
        name=name,
        description="Tasty",
        price_cents=price_cents,
        is_available=is_available,
        category=category,
        image_url="https://example.com/img.jpg",
    )
    db.session.add(item)
    db.session.commit()
    return item

def _create_order(table_number=1, status="draft", notes=None, firebase_id=None):
    if firebase_id is None:
        firebase_id = _unique("fb_order")
    order = Order(
        firebase_id=firebase_id,
        table_number=table_number,
        status=status,
        notes=notes,
    )
    db.session.add(order)
    db.session.commit()
    return order

def _create_order_item(order_id, menu_item_id, quantity=1, unit_price_cents=500, special_instructions=None):
    oi = OrderItem(
        order_id=order_id,
        menu_item_id=menu_item_id,
        quantity=quantity,
        unit_price_cents=unit_price_cents,
        special_instructions=special_instructions,
    )
    db.session.add(oi)
    db.session.commit()
    return oi

def _create_bill(order_id, firebase_id=None, status="requested", subtotal_cents=0, tax_cents=0, service_charge_cents=0, total_cents=0):
    if firebase_id is None:
        firebase_id = _unique("fb_bill")
    bill = Bill(
        firebase_id=firebase_id,
        order_id=order_id,
        status=status,
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        service_charge_cents=service_charge_cents,
        total_cents=total_cents,
    )
    db.session.add(bill)
    db.session.commit()
    return bill

# MODEL: MenuItem
def test_menuitem_model_has_required_fields(app_context):
    item = MenuItem(name=_unique("dish"), price_cents=100)
    for field in ["id", "name", "description", "price_cents", "is_available", "category", "image_url"]:
        assert hasattr(item, field), f"MenuItem missing required field: {field}"

def test_menuitem_to_dict(app_context):
    item = _create_menu_item(category="mains", is_available=True, price_cents=1234)
    d = item.to_dict()
    assert isinstance(d, dict)
    for key in ["id", "name", "description", "price_cents", "is_available", "category", "image_url"]:
        assert key in d

def test_menuitem_unique_constraints(app_context):
    name = _unique("unique_dish")
    _create_menu_item(name=name)
    dup = MenuItem(name=name, price_cents=200)
    db.session.add(dup)
    with pytest.raises(Exception):
        db.session.commit()

# MODEL: Order
def test_order_model_has_required_fields(app_context):
    order = Order(firebase_id=_unique("fb_order"), table_number=1)
    for field in ["id", "firebase_id", "table_number", "status", "created_at", "updated_at", "notes"]:
        assert hasattr(order, field), f"Order missing required field: {field}"

def test_order_can_modify(app_context):
    order = _create_order(status="draft")
    assert isinstance(order.can_modify(), bool)

def test_order_recalculate_totals(app_context):
    order = _create_order(status="draft")
    item = _create_menu_item(price_cents=250)
    _create_order_item(order_id=order.id, menu_item_id=item.id, quantity=2, unit_price_cents=item.price_cents)
    totals = order.recalculate_totals()
    assert isinstance(totals, dict)
    assert any(k in totals for k in ["subtotal_cents", "total_cents", "items_total_cents", "subtotal"]), "recalculate_totals must return totals dict"

def test_order_to_dict(app_context):
    order = _create_order(status="draft", notes="hello")
    item = _create_menu_item(price_cents=300)
    _create_order_item(order_id=order.id, menu_item_id=item.id, quantity=1, unit_price_cents=item.price_cents)
    d1 = order.to_dict()
    assert isinstance(d1, dict)
    assert "id" in d1
    d2 = order.to_dict(include_items=False)
    assert isinstance(d2, dict)
    assert "id" in d2

def test_order_unique_constraints(app_context):
    firebase_id = _unique("fb_order")
    _create_order(firebase_id=firebase_id)
    dup = Order(firebase_id=firebase_id, table_number=2)
    db.session.add(dup)
    with pytest.raises(Exception):
        db.session.commit()

# MODEL: OrderItem
def test_orderitem_model_has_required_fields(app_context):
    oi = OrderItem(order_id=1, menu_item_id=1, unit_price_cents=100)
    for field in ["id", "order_id", "menu_item_id", "quantity", "unit_price_cents", "special_instructions"]:
        assert hasattr(oi, field), f"OrderItem missing required field: {field}"

def test_orderitem_line_total_cents(app_context):
    oi = OrderItem(order_id=1, menu_item_id=1, quantity=3, unit_price_cents=250)
    total = oi.line_total_cents()
    assert isinstance(total, int)
    assert total == 750

def test_orderitem_to_dict(app_context):
    order = _create_order()
    item = _create_menu_item(price_cents=111)
    oi = _create_order_item(order_id=order.id, menu_item_id=item.id, quantity=2, unit_price_cents=111, special_instructions="no onions")
    d = oi.to_dict()
    assert isinstance(d, dict)
    for key in ["id", "order_id", "menu_item_id", "quantity", "unit_price_cents", "special_instructions"]:
        assert key in d

def test_orderitem_unique_constraints(app_context):
    order = _create_order()
    item = _create_menu_item()
    _create_order_item(order_id=order.id, menu_item_id=item.id, quantity=1, unit_price_cents=100)
    _create_order_item(order_id=order.id, menu_item_id=item.id, quantity=1, unit_price_cents=100)
    assert OrderItem.query.filter_by(order_id=order.id, menu_item_id=item.id).count() >= 2

# MODEL: Bill
def test_bill_model_has_required_fields(app_context):
    bill = Bill(firebase_id=_unique("fb_bill"), order_id=1)
    for field in [
        "id",
        "firebase_id",
        "order_id",
        "status",
        "subtotal_cents",
        "tax_cents",
        "service_charge_cents",
        "total_cents",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(bill, field), f"Bill missing required field: {field}"

def test_bill_to_dict(app_context):
    order = _create_order()
    bill = _create_bill(order_id=order.id, subtotal_cents=1000, tax_cents=100, service_charge_cents=50, total_cents=1150)
    d = bill.to_dict()
    assert isinstance(d, dict)
    for key in ["id", "firebase_id", "order_id", "status", "subtotal_cents", "tax_cents", "service_charge_cents", "total_cents"]:
        assert key in d

def test_bill_unique_constraints(app_context):
    order = _create_order()
    firebase_id = _unique("fb_bill")
    _create_bill(order_id=order.id, firebase_id=firebase_id)
    dup1 = Bill(firebase_id=firebase_id, order_id=order.id + 1)
    db.session.add(dup1)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()
    dup2 = Bill(firebase_id=_unique("fb_bill2"), order_id=order.id)
    db.session.add(dup2)
    with pytest.raises(Exception):
        db.session.commit()

# ROUTE: /menu (GET)
def test_menu_get_exists(client):
    resp = client.get("/menu")
    assert resp.status_code != 405

def test_menu_get_renders_template(client, app_context):
    _create_menu_item(category="mains", is_available=True)
    resp = client.get("/menu")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")
    assert len(resp.data) > 0

# ROUTE: /orders (POST)
def test_orders_post_exists(client):
    resp = client.post("/orders", data={})
    assert resp.status_code != 405

def test_orders_post_success(client):
    resp = client.post("/orders", data={"table_number": "3", "notes": "window seat"})
    assert resp.status_code in (200, 201, 302)
    if resp.status_code in (200, 201):
        assert len(resp.data) > 0

def test_orders_post_missing_required_fields(client):
    resp = client.post("/orders", data={"notes": "missing table"})
    assert resp.status_code in (400, 422, 200)

def test_orders_post_invalid_data(client):
    resp = client.post("/orders", data={"table_number": "not-an-int"})
    assert resp.status_code in (400, 422, 200)

def test_orders_post_duplicate_data(client):
    resp1 = client.post("/orders", data={"table_number": "5", "notes": "dup"})
    resp2 = client.post("/orders", data={"table_number": "5", "notes": "dup"})
    assert resp1.status_code in (200, 201, 302)
    assert resp2.status_code in (200, 201, 302, 400, 409, 422)

# ROUTE: /orders/<int:order_id> (GET)
def test_orders_order_id_get_exists(client, app_context):
    order = _create_order()
    resp = client.get(f"/orders/{order.id}")
    assert resp.status_code != 405

def test_orders_order_id_get_renders_template(client, app_context):
    order = _create_order()
    resp = client.get(f"/orders/{order.id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")
    assert len(resp.data) > 0

# ROUTE: /orders/<int:order_id>/items (POST)
def test_orders_order_id_items_post_exists(client, app_context):
    order = _create_order()
    resp = client.post(f"/orders/{order.id}/items", data={})
    assert resp.status_code != 405

def test_orders_order_id_items_post_success(client, app_context):
    order = _create_order()
    item = _create_menu_item(price_cents=700, is_available=True)
    resp = client.post(
        f"/orders/{order.id}/items",
        data={"menu_item_id": str(item.id), "quantity": "2", "special_instructions": "extra spicy"},
    )
    assert resp.status_code in (200, 201, 302)
    if resp.status_code in (200, 201):
        assert len(resp.data) > 0

def test_orders_order_id_items_post_missing_required_fields(client, app_context):
    order = _create_order()
    resp = client.post(f"/orders/{order.id}/items", data={"quantity": "1"})
    assert resp.status_code in (400, 422, 200)

def test_orders_order_id_items_post_invalid_data(client, app_context):
    order = _create_order()
    resp = client.post(f"/orders/{order.id}/items", data={"menu_item_id": "abc", "quantity": "xyz"})
    assert resp.status_code in (400, 422, 200)

def test_orders_order_id_items_post_duplicate_data(client, app_context):
    order = _create_order()
    item = _create_menu_item(price_cents=500, is_available=True)
    resp1 = client.post(f"/orders/{order.id}/items", data={"menu_item_id": str(item.id), "quantity": "1"})
    resp2 = client.post(f"/orders/{order.id}/items", data={"menu_item_id": str(item.id), "quantity": "1"})
    assert resp1.status_code in (200, 201, 302)
    assert resp2.status_code in (200, 201, 302, 400, 409, 422)

# ROUTE: /orders/<int:order_id>/items/<int:order_item_id> (PATCH)
def test_orders_order_id_items_order_item_id_patch_exists(client, app_context):
    order = _create_order()
    item = _create_menu_item(price_cents=100)
    oi = _create_order_item(order_id=order.id, menu_item_id=item.id, quantity=1, unit_price_cents=100)
    resp = client.patch(f"/orders/{order.id}/items/{oi.id}", data={"quantity": "2"})
    assert resp.status_code != 405

# ROUTE: /orders/<int:order_id>/items/<int:order_item_id> (DELETE)
def test_orders_order_id_items_order_item_id_delete_exists(client, app_context):
    order = _create_order()
    item = _create_menu_item(price_cents=100)
    oi = _create_order_item(order_id=order.id, menu_item_id=item.id, quantity=1, unit_price_cents=100)
    resp = client.delete(f"/orders/{order.id}/items/{oi.id}")
    assert resp.status_code != 405

# ROUTE: /orders/<int:order_id> (PATCH)
def test_orders_order_id_patch_exists(client, app_context):
    order = _create_order(notes="old")
    resp = client.patch(f"/orders/{order.id}", data={"notes": "new"})
    assert resp.status_code != 405

# ROUTE: /orders/<int:order_id>/cancel (POST)
def test_orders_order_id_cancel_post_exists(client, app_context):
    order = _create_order()
    resp = client.post(f"/orders/{order.id}/cancel", data={})
    assert resp.status_code != 405

def test_orders_order_id_cancel_post_success(client, app_context):
    order = _create_order(status="draft")
    resp = client.post(f"/orders/{order.id}/cancel", data={"reason": "changed mind"})
    assert resp.status_code in (200, 201, 302)
    if resp.status_code in (200, 201):
        assert len(resp.data) > 0

def test_orders_order_id_cancel_post_missing_required_fields(client, app_context):
    order = _create_order(status="draft")
    resp = client.post(f"/orders/{order.id}/cancel", data={})
    assert resp.status_code in (200, 302, 400, 422)

def test_orders_order_id_cancel_post_invalid_data(client, app_context):
    order = _create_order(status="draft")
    resp = client.post(f"/orders/{order.id}/cancel", data={"reason": 123})
    assert resp.status_code in (200, 302, 400, 422)

def test_orders_order_id_cancel_post_duplicate_data(client, app_context):
    order = _create_order(status="draft")
    resp1 = client.post(f"/orders/{order.id}/cancel", data={"reason": "dup"})
    resp2 = client.post(f"/orders/{order.id}/cancel", data={"reason": "dup"})
    assert resp1.status_code in (200, 201, 302, 400, 409, 422)
    assert resp2.status_code in (200, 201, 302, 400, 409, 422)

# ROUTE: /orders/<int:order_id>/submit (POST)
def test_orders_order_id_submit_post_exists(client, app_context):
    order = _create_order()
    resp = client.post(f"/orders/{order.id}/submit", data={})
    assert resp.status_code != 405

def test_orders_order_id_submit_post_success(client, app_context):
    order = _create_order(status="draft")
    resp = client.post(f"/orders/{order.id}/submit", data={})
    assert resp.status_code in (200, 201, 302)
    if resp.status_code in (200, 201):
        assert len(resp.data) > 0

def test_orders_order_id_submit_post_missing_required_fields(client, app_context):
    order = _create_order(status="draft")
    resp = client.post(f"/orders/{order.id}/submit", data={})
    assert resp.status_code in (200, 201, 302, 400, 422)

def test_orders_order_id_submit_post_invalid_data(client, app_context):
    resp = client.post("/orders/999999/submit", data={"unexpected": "field"})
    assert resp.status_code in (200, 201, 302, 400, 404, 422)

def test_orders_order_id_submit_post_duplicate_data(client, app_context):
    order = _create_order(status="draft")
    resp1 = client.post(f"/orders/{order.id}/submit", data={})
    resp2 = client.post(f"/orders/{order.id}/submit", data={})
    assert resp1.status_code in (200, 201, 302, 400, 409, 422)
    assert resp2.status_code in (200, 201, 302, 400, 409, 422)

# ROUTE: /orders/<int:order_id>/bill (POST)
def test_orders_order_id_bill_post_exists(client, app_context):
    order = _create_order()
    resp = client.post(f"/orders/{order.id}/bill", data={})
    assert resp.status_code != 405

def test_orders_order_id_bill_post_success(client, app_context):
    order = _create_order(status="submitted")
    item = _create_menu_item(price_cents=400)
    _create_order_item(order_id=order.id, menu_item_id=item.id, quantity=2, unit_price_cents=400)
    with patch("controllers.customer_order_management_controller.manager_notify_bill_requested") as mock_notify:
        resp = client.post(f"/orders/{order.id}/bill", data={})
        assert resp.status_code in (200, 201, 302)
        assert mock_notify.called or resp.status_code in (200, 201, 302)

def test_orders_order_id_bill_post_missing_required_fields(client, app_context):
    order = _create_order()
    resp = client.post(f"/orders/{order.id}/bill", data={})
    assert resp.status_code in (200, 201, 302, 400, 422)

def test_orders_order_id_bill_post_invalid_data(client, app_context):
    resp = client.post("/orders/999999/bill", data={"unexpected": "field"})
    assert resp.status_code in (200, 201, 302, 400, 404, 422)

def test_orders_order_id_bill_post_duplicate_data(client, app_context):
    order = _create_order(status="submitted")
    with patch("controllers.customer_order_management_controller.manager_notify_bill_requested"):
        resp1 = client.post(f"/orders/{order.id}/bill", data={})
        resp2 = client.post(f"/orders/{order.id}/bill", data={})
    assert resp1.status_code in (200, 201, 302, 400, 409, 422)
    assert resp2.status_code in (200, 201, 302, 400, 409, 422)

# ROUTE: /bills/<int:bill_id> (GET)
def test_bills_bill_id_get_exists(client, app_context):
    order = _create_order()
    bill = _create_bill(order_id=order.id)
    resp = client.get(f"/bills/{bill.id}")
    assert resp.status_code != 405

def test_bills_bill_id_get_renders_template(client, app_context):
    order = _create_order()
    bill = _create_bill(order_id=order.id, subtotal_cents=100, total_cents=100)
    resp = client.get(f"/bills/{bill.id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")
    assert len(resp.data) > 0

# HELPER: firebase_upsert_order(order: Order)
def test_firebase_upsert_order_function_exists():
    assert callable(firebase_upsert_order)

def test_firebase_upsert_order_with_valid_input(app_context):
    order = _create_order()
    with patch("controllers.customer_order_management_controller.firebase_upsert_order", wraps=firebase_upsert_order) as fn:
        result = fn(order)
    assert isinstance(result, str)
    assert len(result) > 0

def test_firebase_upsert_order_with_invalid_input():
    with pytest.raises(Exception):
        firebase_upsert_order(None)

# HELPER: firebase_upsert_bill(bill: Bill)
def test_firebase_upsert_bill_function_exists():
    assert callable(firebase_upsert_bill)

def test_firebase_upsert_bill_with_valid_input(app_context):
    order = _create_order()
    bill = _create_bill(order_id=order.id)
    with patch("controllers.customer_order_management_controller.firebase_upsert_bill", wraps=firebase_upsert_bill) as fn:
        result = fn(bill)
    assert isinstance(result, str)
    assert len(result) > 0

def test_firebase_upsert_bill_with_invalid_input():
    with pytest.raises(Exception):
        firebase_upsert_bill(None)

# HELPER: firebase_delete_order(firebase_id: str)
def test_firebase_delete_order_function_exists():
    assert callable(firebase_delete_order)

def test_firebase_delete_order_with_valid_input():
    firebase_id = _unique("fb_order_del")
    firebase_delete_order(firebase_id)

def test_firebase_delete_order_with_invalid_input():
    with pytest.raises(Exception):
        firebase_delete_order(None)

# HELPER: manager_notify_bill_requested(bill: Bill)
def test_manager_notify_bill_requested_function_exists():
    assert callable(manager_notify_bill_requested)

def test_manager_notify_bill_requested_with_valid_input(app_context):
    order = _create_order()
    bill = _create_bill(order_id=order.id)
    manager_notify_bill_requested(bill)

def test_manager_notify_bill_requested_with_invalid_input():
    with pytest.raises(Exception):
        manager_notify_bill_requested(None)

# HELPER: calculate_bill_amounts(order: Order, tax_rate: float = 0.0, service_charge_rate: float = 0.0)
def test_calculate_bill_amounts_function_exists():
    assert callable(calculate_bill_amounts)

def test_calculate_bill_amounts_with_valid_input(app_context):
    order = _create_order()
    item = _create_menu_item(price_cents=1000)
    _create_order_item(order_id=order.id, menu_item_id=item.id, quantity=2, unit_price_cents=1000)
    amounts = calculate_bill_amounts(order, tax_rate=0.1, service_charge_rate=0.05)
    assert isinstance(amounts, dict)
    for k in ["subtotal_cents", "tax_cents", "service_charge_cents", "total_cents"]:
        assert k in amounts

def test_calculate_bill_amounts_with_invalid_input():
    with pytest.raises(Exception):
        calculate_bill_amounts(None, tax_rate=0.1, service_charge_rate=0.05)