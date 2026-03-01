import os
import sys
import uuid
import json
import inspect
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.edit_order_order import EditOrderOrder
from models.edit_order_order_item import EditOrderOrderItem
from models.edit_order_chef_approval_request import EditOrderChefApprovalRequest

from controllers.edit_order_controller import (
    get_current_user,
    serialize_order,
    serialize_order_item,
    compute_order_totals,
    validate_edit_payload,
    requires_head_chef_approval,
    create_approval_request,
    apply_change_set,
)

from views.edit_order_views import render_edit_order_page

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

def _unique_email():
    return f"u_{uuid.uuid4().hex[:10]}@example.com"

def _unique_username():
    return f"user_{uuid.uuid4().hex[:10]}"

def _create_user(role="customer", password="Passw0rd!"):
    u = User(email=_unique_email(), username=_unique_username(), role=role)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u

def _create_order(customer_id, status="draft", version=1):
    o = EditOrderOrder(customer_id=customer_id, status=status, version=version)
    db.session.add(o)
    db.session.commit()
    return o

def _create_item(order_id, dish_id=101, dish_name="Dish", unit_price_cents=500, quantity=2, notes=None):
    it = EditOrderOrderItem(
        order_id=order_id,
        dish_id=dish_id,
        dish_name=dish_name,
        unit_price_cents=unit_price_cents,
        quantity=quantity,
        notes=notes,
    )
    db.session.add(it)
    db.session.commit()
    return it

def _create_approval_request(order_id, requested_by_user_id, status="pending", reason="reason", change_set=None):
    if change_set is None:
        change_set = {"op": "update", "items": []}
    ar = EditOrderChefApprovalRequest(
        order_id=order_id,
        requested_by_user_id=requested_by_user_id,
        approved_by_user_id=None,
        status=status,
        reason=reason,
        change_set_json=json.dumps(change_set),
    )
    db.session.add(ar)
    db.session.commit()
    return ar

def _route_rule_exists(path, method):
    for rule in app.url_map.iter_rules():
        if rule.rule == path and method in rule.methods:
            return True
    return False

def _find_rule(path):
    for rule in app.url_map.iter_rules():
        if rule.rule == path:
            return rule
    return None

# MODEL: User (models/user.py)
def test_user_model_has_required_fields():
    for field in ["id", "email", "username", "password_hash", "role"]:
        assert hasattr(User, field), f"Missing required field on User: {field}"

def test_user_set_password():
    u = User(email=_unique_email(), username=_unique_username(), role="customer")
    u.set_password("MyS3cret!")
    assert getattr(u, "password_hash", None)
    assert u.password_hash != "MyS3cret!"

def test_user_check_password():
    u = User(email=_unique_email(), username=_unique_username(), role="customer")
    u.set_password("MyS3cret!")
    assert u.check_password("MyS3cret!") is True
    assert u.check_password("wrong") is False

def test_user_unique_constraints(app_context):
    u1 = User(email=_unique_email(), username=_unique_username(), role="customer")
    u1.set_password("Passw0rd!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=u1.email, username=_unique_username(), role="customer")
    u2.set_password("Passw0rd!")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=_unique_email(), username=u1.username, role="customer")
    u3.set_password("Passw0rd!")
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# MODEL: EditOrderOrder (models/edit_order_order.py)
def test_editorderorder_model_has_required_fields():
    for field in ["id", "customer_id", "status", "version", "created_at", "updated_at"]:
        assert hasattr(EditOrderOrder, field), f"Missing required field on EditOrderOrder: {field}"

def test_editorderorder_is_editable(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id, status="draft", version=1)
    assert hasattr(o, "is_editable")
    assert callable(o.is_editable)
    result = o.is_editable()
    assert isinstance(result, bool)

def test_editorderorder_unique_constraints(app_context):
    u = _create_user()
    o1 = _create_order(customer_id=u.id, status="draft", version=1)
    o2 = _create_order(customer_id=u.id, status="draft", version=1)
    assert o1.id != o2.id

# MODEL: EditOrderOrderItem (models/edit_order_order_item.py)
def test_editorderorderitem_model_has_required_fields():
    for field in [
        "id",
        "order_id",
        "dish_id",
        "dish_name",
        "unit_price_cents",
        "quantity",
        "notes",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(EditOrderOrderItem, field), f"Missing required field on EditOrderOrderItem: {field}"

def test_editorderorderitem_line_total_cents(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id)
    it = _create_item(order_id=o.id, unit_price_cents=123, quantity=4)
    assert hasattr(it, "line_total_cents")
    assert callable(it.line_total_cents)
    total = it.line_total_cents()
    assert isinstance(total, int)
    assert total == 492

def test_editorderorderitem_unique_constraints(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id)
    it1 = _create_item(order_id=o.id, dish_id=1, dish_name="A")
    it2 = _create_item(order_id=o.id, dish_id=1, dish_name="A")
    assert it1.id != it2.id

# MODEL: EditOrderChefApprovalRequest (models/edit_order_chef_approval_request.py)
def test_editorderchefapprovalrequest_model_has_required_fields():
    for field in [
        "id",
        "order_id",
        "requested_by_user_id",
        "approved_by_user_id",
        "status",
        "reason",
        "change_set_json",
        "created_at",
        "decided_at",
    ]:
        assert hasattr(EditOrderChefApprovalRequest, field), (
            f"Missing required field on EditOrderChefApprovalRequest: {field}"
        )

def test_editorderchefapprovalrequest_is_pending(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id)
    ar = _create_approval_request(order_id=o.id, requested_by_user_id=u.id, status="pending")
    assert hasattr(ar, "is_pending")
    assert callable(ar.is_pending)
    result = ar.is_pending()
    assert isinstance(result, bool)

def test_editorderchefapprovalrequest_unique_constraints(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id)
    ar1 = _create_approval_request(order_id=o.id, requested_by_user_id=u.id, status="pending")
    ar2 = _create_approval_request(order_id=o.id, requested_by_user_id=u.id, status="pending")
    assert ar1.id != ar2.id

# ROUTE: /orders/<int:order_id>/edit (GET) - enter_edit_mode
def test_orders_order_id_edit_get_exists():
    assert _route_rule_exists("/orders/<int:order_id>/edit", "GET"), "Route GET /orders/<int:order_id>/edit missing"

def test_orders_order_id_edit_get_renders_template(client):
    with app.app_context():
        u = _create_user()
        o = _create_order(customer_id=u.id, status="draft")
        _create_item(order_id=o.id, dish_id=11, dish_name="Soup", unit_price_cents=250, quantity=1)

    with patch("controllers.edit_order_controller.get_current_user", return_value=MagicMock(id=u.id, role="customer")):
        resp = client.get(f"/orders/{o.id}/edit")
        assert resp.status_code == 200
        assert b"<" in resp.data
        assert b"order" in resp.data.lower() or b"edit" in resp.data.lower()

# ROUTE: /orders/<int:order_id> (PATCH) - edit_order
def test_orders_order_id_patch_exists():
    assert _route_rule_exists("/orders/<int:order_id>", "PATCH"), "Route PATCH /orders/<int:order_id> missing"

# ROUTE: /orders/<int:order_id>/items (POST) - add_dish_to_order
def test_orders_order_id_items_post_exists():
    assert _route_rule_exists("/orders/<int:order_id>/items", "POST"), "Route POST /orders/<int:order_id>/items missing"

def test_orders_order_id_items_post_success(client):
    with app.app_context():
        u = _create_user()
        o = _create_order(customer_id=u.id, status="draft")

    payload = {
        "dish_id": 999,
        "dish_name": "Pasta",
        "unit_price_cents": 1200,
        "quantity": 2,
        "notes": "no cheese",
    }

    with patch("controllers.edit_order_controller.get_current_user", return_value=MagicMock(id=u.id, role="customer")):
        resp = client.post(f"/orders/{o.id}/items", json=payload)
        assert resp.status_code in (200, 201)

    with app.app_context():
        items = EditOrderOrderItem.query.filter_by(order_id=o.id, dish_id=999).all()
        assert len(items) >= 1
        assert items[-1].quantity == 2

def test_orders_order_id_items_post_missing_required_fields(client):
    with app.app_context():
        u = _create_user()
        o = _create_order(customer_id=u.id, status="draft")

    payload = {"dish_id": 1, "quantity": 1}
    with patch("controllers.edit_order_controller.get_current_user", return_value=MagicMock(id=u.id, role="customer")):
        resp = client.post(f"/orders/{o.id}/items", json=payload)
        assert resp.status_code in (400, 422)

def test_orders_order_id_items_post_invalid_data(client):
    with app.app_context():
        u = _create_user()
        o = _create_order(customer_id=u.id, status="draft")

    payload = {"dish_id": "abc", "dish_name": "X", "unit_price_cents": "free", "quantity": -1}
    with patch("controllers.edit_order_controller.get_current_user", return_value=MagicMock(id=u.id, role="customer")):
        resp = client.post(f"/orders/{o.id}/items", json=payload)
        assert resp.status_code in (400, 422)

def test_orders_order_id_items_post_duplicate_data(client):
    with app.app_context():
        u = _create_user()
        o = _create_order(customer_id=u.id, status="draft")
        _create_item(order_id=o.id, dish_id=777, dish_name="Burger", unit_price_cents=800, quantity=1)

    payload = {"dish_id": 777, "dish_name": "Burger", "unit_price_cents": 800, "quantity": 1}
    with patch("controllers.edit_order_controller.get_current_user", return_value=MagicMock(id=u.id, role="customer")):
        resp = client.post(f"/orders/{o.id}/items", json=payload)
        assert resp.status_code in (200, 201, 409)

    with app.app_context():
        items = EditOrderOrderItem.query.filter_by(order_id=o.id, dish_id=777).all()
        assert len(items) >= 1

# ROUTE: /orders/<int:order_id>/items/<int:item_id> (PATCH) - update_order_item
def test_orders_order_id_items_item_id_patch_exists():
    assert _route_rule_exists(
        "/orders/<int:order_id>/items/<int:item_id>", "PATCH"
    ), "Route PATCH /orders/<int:order_id>/items/<int:item_id> missing"

# ROUTE: /orders/<int:order_id>/items/<int:item_id> (DELETE) - remove_dish_from_order
def test_orders_order_id_items_item_id_delete_exists():
    assert _route_rule_exists(
        "/orders/<int:order_id>/items/<int:item_id>", "DELETE"
    ), "Route DELETE /orders/<int:order_id>/items/<int:item_id> missing"

# ROUTE: /chef-approvals/<int:approval_id> (POST) - decide_chef_approval
def test_chef_approvals_approval_id_post_exists():
    assert _route_rule_exists(
        "/chef-approvals/<int:approval_id>", "POST"
    ), "Route POST /chef-approvals/<int:approval_id> missing"

def test_chef_approvals_approval_id_post_success(client):
    with app.app_context():
        customer = _create_user(role="customer")
        chef = _create_user(role="head_chef")
        o = _create_order(customer_id=customer.id, status="draft")
        ar = _create_approval_request(order_id=o.id, requested_by_user_id=customer.id, status="pending")

    payload = {"decision": "approve", "approved_by_user_id": chef.id}

    with patch("controllers.edit_order_controller.get_current_user", return_value=MagicMock(id=chef.id, role="head_chef")):
        resp = client.post(f"/chef-approvals/{ar.id}", json=payload)
        assert resp.status_code in (200, 201)

    with app.app_context():
        refreshed = EditOrderChefApprovalRequest.query.filter_by(id=ar.id).first()
        assert refreshed is not None
        assert refreshed.status != "pending"

def test_chef_approvals_approval_id_post_missing_required_fields(client):
    with app.app_context():
        customer = _create_user(role="customer")
        chef = _create_user(role="head_chef")
        o = _create_order(customer_id=customer.id, status="draft")
        ar = _create_approval_request(order_id=o.id, requested_by_user_id=customer.id, status="pending")

    payload = {}
    with patch("controllers.edit_order_controller.get_current_user", return_value=MagicMock(id=chef.id, role="head_chef")):
        resp = client.post(f"/chef-approvals/{ar.id}", json=payload)
        assert resp.status_code in (400, 422)

def test_chef_approvals_approval_id_post_invalid_data(client):
    with app.app_context():
        customer = _create_user(role="customer")
        chef = _create_user(role="head_chef")
        o = _create_order(customer_id=customer.id, status="draft")
        ar = _create_approval_request(order_id=o.id, requested_by_user_id=customer.id, status="pending")

    payload = {"decision": "maybe", "approved_by_user_id": "not-an-int"}
    with patch("controllers.edit_order_controller.get_current_user", return_value=MagicMock(id=chef.id, role="head_chef")):
        resp = client.post(f"/chef-approvals/{ar.id}", json=payload)
        assert resp.status_code in (400, 422)

def test_chef_approvals_approval_id_post_duplicate_data(client):
    with app.app_context():
        customer = _create_user(role="customer")
        chef = _create_user(role="head_chef")
        o = _create_order(customer_id=customer.id, status="draft")
        ar = _create_approval_request(order_id=o.id, requested_by_user_id=customer.id, status="pending")

    payload = {"decision": "approve", "approved_by_user_id": chef.id}

    with patch("controllers.edit_order_controller.get_current_user", return_value=MagicMock(id=chef.id, role="head_chef")):
        resp1 = client.post(f"/chef-approvals/{ar.id}", json=payload)
        assert resp1.status_code in (200, 201)
        resp2 = client.post(f"/chef-approvals/{ar.id}", json=payload)
        assert resp2.status_code in (200, 201, 400, 409, 422)

# HELPER: get_current_user(N/A)
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input():
    user = get_current_user()
    assert user is None or isinstance(user, User)

def test_get_current_user_with_invalid_input():
    with pytest.raises(TypeError):
        get_current_user("unexpected")

# HELPER: serialize_order(order)
def test_serialize_order_function_exists():
    assert callable(serialize_order)
    sig = inspect.signature(serialize_order)
    assert len(sig.parameters) == 1

def test_serialize_order_with_valid_input(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id, status="draft", version=1)
    d = serialize_order(o)
    assert isinstance(d, dict)
    assert "id" in d
    assert d["id"] == o.id

def test_serialize_order_with_invalid_input():
    with pytest.raises(Exception):
        serialize_order(None)

# HELPER: serialize_order_item(item)
def test_serialize_order_item_function_exists():
    assert callable(serialize_order_item)
    sig = inspect.signature(serialize_order_item)
    assert len(sig.parameters) == 1

def test_serialize_order_item_with_valid_input(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id)
    it = _create_item(order_id=o.id, dish_id=55, dish_name="Salad", unit_price_cents=300, quantity=3)
    d = serialize_order_item(it)
    assert isinstance(d, dict)
    assert "id" in d
    assert d["id"] == it.id
    assert d.get("quantity") == 3

def test_serialize_order_item_with_invalid_input():
    with pytest.raises(Exception):
        serialize_order_item(None)

# HELPER: compute_order_totals(order)
def test_compute_order_totals_function_exists():
    assert callable(compute_order_totals)
    sig = inspect.signature(compute_order_totals)
    assert len(sig.parameters) == 1

def test_compute_order_totals_with_valid_input(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id)
    _create_item(order_id=o.id, unit_price_cents=100, quantity=2)
    _create_item(order_id=o.id, unit_price_cents=250, quantity=1)
    totals = compute_order_totals(o)
    assert isinstance(totals, dict)
    assert any(k in totals for k in ["total_cents", "subtotal_cents", "items_total_cents"])

def test_compute_order_totals_with_invalid_input():
    with pytest.raises(Exception):
        compute_order_totals(None)

# HELPER: validate_edit_payload(payload)
def test_validate_edit_payload_function_exists():
    assert callable(validate_edit_payload)
    sig = inspect.signature(validate_edit_payload)
    assert len(sig.parameters) == 1

def test_validate_edit_payload_with_valid_input():
    payload = {"change_set": {"op": "update", "items": []}}
    result = validate_edit_payload(payload)
    assert isinstance(result, dict)

def test_validate_edit_payload_with_invalid_input():
    with pytest.raises(Exception):
        validate_edit_payload("not-a-dict")

# HELPER: requires_head_chef_approval(order, change_set)
def test_requires_head_chef_approval_function_exists():
    assert callable(requires_head_chef_approval)
    sig = inspect.signature(requires_head_chef_approval)
    assert len(sig.parameters) == 2

def test_requires_head_chef_approval_with_valid_input(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id, status="draft")
    change_set = {"op": "update", "items": [{"dish_id": 1, "quantity": 2}]}
    result = requires_head_chef_approval(o, change_set)
    assert isinstance(result, bool)

def test_requires_head_chef_approval_with_invalid_input(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id, status="draft")
    with pytest.raises(Exception):
        requires_head_chef_approval(o, None)

# HELPER: create_approval_request(order, requested_by_user, reason, change_set)
def test_create_approval_request_function_exists():
    assert callable(create_approval_request)
    sig = inspect.signature(create_approval_request)
    assert len(sig.parameters) == 4

def test_create_approval_request_with_valid_input(app_context):
    customer = _create_user(role="customer")
    o = _create_order(customer_id=customer.id, status="draft")
    change_set = {"op": "update", "items": [{"dish_id": 1, "quantity": 10}]}
    ar = create_approval_request(o, customer, "Large quantity change", change_set)
    assert isinstance(ar, EditOrderChefApprovalRequest)
    assert ar.order_id == o.id
    assert ar.requested_by_user_id == customer.id
    assert isinstance(ar.change_set_json, str)
    parsed = json.loads(ar.change_set_json)
    assert parsed["op"] == "update"

def test_create_approval_request_with_invalid_input(app_context):
    customer = _create_user(role="customer")
    o = _create_order(customer_id=customer.id, status="draft")
    with pytest.raises(Exception):
        create_approval_request(o, customer, None, {"op": "update"})

# HELPER: apply_change_set(order, change_set)
def test_apply_change_set_function_exists():
    assert callable(apply_change_set)
    sig = inspect.signature(apply_change_set)
    assert len(sig.parameters) == 2

def test_apply_change_set_with_valid_input(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id, status="draft", version=1)
    _create_item(order_id=o.id, dish_id=10, dish_name="Tea", unit_price_cents=100, quantity=1)

    change_set = {
        "op": "update",
        "items": [
            {"action": "update", "dish_id": 10, "quantity": 3},
            {"action": "add", "dish_id": 20, "dish_name": "Cake", "unit_price_cents": 450, "quantity": 1},
        ],
    }
    apply_change_set(o, change_set)

    db.session.commit()

    items_10 = EditOrderOrderItem.query.filter_by(order_id=o.id, dish_id=10).all()
    assert len(items_10) >= 1
    assert items_10[-1].quantity == 3

    items_20 = EditOrderOrderItem.query.filter_by(order_id=o.id, dish_id=20).all()
    assert len(items_20) >= 1

def test_apply_change_set_with_invalid_input(app_context):
    u = _create_user()
    o = _create_order(customer_id=u.id, status="draft")
    with pytest.raises(Exception):
        apply_change_set(o, None)