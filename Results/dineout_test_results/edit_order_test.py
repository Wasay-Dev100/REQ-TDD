import os
import sys
import uuid
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db  # noqa: E402
from models.user import User  # noqa: E402
from models.edit_order_order import EditOrderOrder  # noqa: E402
from models.edit_order_order_item import EditOrderOrderItem  # noqa: E402
from models.edit_order_chef_approval_request import EditOrderChefApprovalRequest  # noqa: E402

from controllers.edit_order_controller import (  # noqa: E402
    get_current_user,
    serialize_order,
    serialize_order_item,
    compute_order_totals,
    validate_edit_payload,
    requires_head_chef_approval,
    create_approval_request,
    apply_change_set,
)

from views.edit_order_views import render_edit_order_page  # noqa: E402

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

def _create_user(email=None, username=None, password="Passw0rd!"):
    if email is None:
        email = f"{_unique('user')}@example.com"
    if username is None:
        username = _unique("user")
    u = User(email=email, username=username, role="customer", password_hash="")
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u

def _create_order(customer_id=None, status="pending", version=1):
    if customer_id is None:
        customer = _create_user()
        customer_id = customer.id
    o = EditOrderOrder(customer_id=customer_id, status=status, version=version)
    db.session.add(o)
    db.session.commit()
    return o

def _create_item(order_id=None, dish_id=1, dish_name="Dish", unit_price_cents=500, quantity=1, notes=None):
    if order_id is None:
        order = _create_order()
        order_id = order.id
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

def _create_approval_request(order_id=None, requested_by_user_id=None, status="pending", reason="Change", change_set=None):
    if order_id is None:
        order = _create_order()
        order_id = order.id
    if requested_by_user_id is None:
        user = _create_user()
        requested_by_user_id = user.id
    if change_set is None:
        change_set = {"op": "update", "items": []}
    req = EditOrderChefApprovalRequest(
        order_id=order_id,
        requested_by_user_id=requested_by_user_id,
        approved_by_user_id=None,
        status=status,
        reason=reason,
        change_set_json=json.dumps(change_set),
    )
    db.session.add(req)
    db.session.commit()
    return req

def _route_exists(rule: str, method: str) -> bool:
    for r in app.url_map.iter_rules():
        if r.rule == rule and method in r.methods:
            return True
    return False

# MODEL: User (models/user.py)
def test_user_model_has_required_fields():
    for field in ["id", "email", "username", "password_hash", "role"]:
        assert hasattr(User, field), f"Missing required field on User: {field}"

def test_user_set_password():
    u = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="customer", password_hash="")
    u.set_password("MyS3cret!")
    assert u.password_hash
    assert u.password_hash != "MyS3cret!"

def test_user_check_password():
    u = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="customer", password_hash="")
    u.set_password("MyS3cret!")
    assert u.check_password("MyS3cret!") is True
    assert u.check_password("wrong") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")
    u1 = User(email=email, username=username, role="customer", password_hash="")
    u1.set_password("Passw0rd!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("otheruser"), role="customer", password_hash="")
    u2.set_password("Passw0rd!")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, role="customer", password_hash="")
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
    order = _create_order(status="pending")
    assert hasattr(order, "is_editable") and callable(order.is_editable)
    result = order.is_editable()
    assert isinstance(result, bool)

def test_editorderorder_unique_constraints(app_context):
    order1 = _create_order(status="pending")
    order2 = _create_order(status="pending")
    assert order1.id != order2.id

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
    item = _create_item(unit_price_cents=250, quantity=3)
    assert hasattr(item, "line_total_cents") and callable(item.line_total_cents)
    total = item.line_total_cents()
    assert isinstance(total, int)
    assert total == 750

def test_editorderorderitem_unique_constraints(app_context):
    order = _create_order()
    i1 = _create_item(order_id=order.id, dish_id=1, dish_name="A")
    i2 = _create_item(order_id=order.id, dish_id=1, dish_name="A")
    assert i1.id != i2.id

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
        assert hasattr(EditOrderChefApprovalRequest, field), f"Missing required field on EditOrderChefApprovalRequest: {field}"

def test_editorderchefapprovalrequest_is_pending(app_context):
    req = _create_approval_request(status="pending")
    assert hasattr(req, "is_pending") and callable(req.is_pending)
    result = req.is_pending()
    assert isinstance(result, bool)

def test_editorderchefapprovalrequest_unique_constraints(app_context):
    r1 = _create_approval_request()
    r2 = _create_approval_request()
    assert r1.id != r2.id

# ROUTE: /orders/<int:order_id>/edit (GET) - enter_edit_mode
def test_orders_order_id_edit_get_exists():
    assert _route_exists("/orders/<int:order_id>/edit", "GET"), "Route /orders/<int:order_id>/edit (GET) not registered"

def test_orders_order_id_edit_get_renders_template(client, app_context):
    order = _create_order(status="pending")
    with patch("controllers.edit_order_controller.get_current_user", return_value=_create_user()):
        resp = client.get(f"/orders/{order.id}/edit")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/xhtml+xml", "text/plain")
    assert resp.data is not None
    assert len(resp.data) > 0

# ROUTE: /orders/<int:order_id> (PATCH) - edit_order
def test_orders_order_id_patch_exists():
    assert _route_exists("/orders/<int:order_id>", "PATCH"), "Route /orders/<int:order_id> (PATCH) not registered"

# ROUTE: /orders/<int:order_id>/items (POST) - add_dish_to_order
def test_orders_order_id_items_post_exists():
    assert _route_exists("/orders/<int:order_id>/items", "POST"), "Route /orders/<int:order_id>/items (POST) not registered"

def test_orders_order_id_items_post_success(client, app_context):
    order = _create_order(status="pending")
    payload = {
        "dish_id": 101,
        "dish_name": "Margherita Pizza",
        "unit_price_cents": 1299,
        "quantity": 2,
        "notes": "extra basil",
    }
    with patch("controllers.edit_order_controller.get_current_user", return_value=_create_user()):
        resp = client.post(f"/orders/{order.id}/items", json=payload)
    assert resp.status_code in (200, 201)
    assert resp.is_json
    data = resp.get_json()
    assert isinstance(data, dict)
    assert ("order" in data) or ("item" in data) or ("items" in data)

def test_orders_order_id_items_post_missing_required_fields(client, app_context):
    order = _create_order(status="pending")
    payload = {"dish_id": 101}
    with patch("controllers.edit_order_controller.get_current_user", return_value=_create_user()):
        resp = client.post(f"/orders/{order.id}/items", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        data = resp.get_json()
        assert isinstance(data, dict)

def test_orders_order_id_items_post_invalid_data(client, app_context):
    order = _create_order(status="pending")
    payload = {
        "dish_id": "not-an-int",
        "dish_name": "",
        "unit_price_cents": -5,
        "quantity": 0,
    }
    with patch("controllers.edit_order_controller.get_current_user", return_value=_create_user()):
        resp = client.post(f"/orders/{order.id}/items", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        data = resp.get_json()
        assert isinstance(data, dict)

def test_orders_order_id_items_post_duplicate_data(client, app_context):
    order = _create_order(status="pending")
    payload = {
        "dish_id": 202,
        "dish_name": "Soup",
        "unit_price_cents": 599,
        "quantity": 1,
    }
    with patch("controllers.edit_order_controller.get_current_user", return_value=_create_user()):
        resp1 = client.post(f"/orders/{order.id}/items", json=payload)
        resp2 = client.post(f"/orders/{order.id}/items", json=payload)
    assert resp1.status_code in (200, 201)
    assert resp2.status_code in (200, 201, 400, 409, 422)
    if resp2.status_code in (400, 409, 422) and resp2.is_json:
        data = resp2.get_json()
        assert isinstance(data, dict)

# ROUTE: /orders/<int:order_id>/items/<int:item_id> (PATCH) - update_order_item
def test_orders_order_id_items_item_id_patch_exists():
    assert _route_exists(
        "/orders/<int:order_id>/items/<int:item_id>", "PATCH"
    ), "Route /orders/<int:order_id>/items/<int:item_id> (PATCH) not registered"

# ROUTE: /orders/<int:order_id>/items/<int:item_id> (DELETE) - remove_dish_from_order
def test_orders_order_id_items_item_id_delete_exists():
    assert _route_exists(
        "/orders/<int:order_id>/items/<int:item_id>", "DELETE"
    ), "Route /orders/<int:order_id>/items/<int:item_id> (DELETE) not registered"

# ROUTE: /chef-approvals/<int:approval_id> (POST) - decide_chef_approval
def test_chef_approvals_approval_id_post_exists():
    assert _route_exists(
        "/chef-approvals/<int:approval_id>", "POST"
    ), "Route /chef-approvals/<int:approval_id> (POST) not registered"

def test_chef_approvals_approval_id_post_success(client, app_context):
    req = _create_approval_request(status="pending")
    payload = {"decision": "approve"}
    with patch("controllers.edit_order_controller.get_current_user", return_value=_create_user(role="head_chef")):
        resp = client.post(f"/chef-approvals/{req.id}", json=payload)
    assert resp.status_code in (200, 201)
    assert resp.is_json
    data = resp.get_json()
    assert isinstance(data, dict)
    assert ("approval" in data) or ("order" in data) or ("status" in data)

def test_chef_approvals_approval_id_post_missing_required_fields(client, app_context):
    req = _create_approval_request(status="pending")
    payload = {}
    with patch("controllers.edit_order_controller.get_current_user", return_value=_create_user(role="head_chef")):
        resp = client.post(f"/chef-approvals/{req.id}", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        data = resp.get_json()
        assert isinstance(data, dict)

def test_chef_approvals_approval_id_post_invalid_data(client, app_context):
    req = _create_approval_request(status="pending")
    payload = {"decision": "not-a-valid-decision"}
    with patch("controllers.edit_order_controller.get_current_user", return_value=_create_user(role="head_chef")):
        resp = client.post(f"/chef-approvals/{req.id}", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        data = resp.get_json()
        assert isinstance(data, dict)

def test_chef_approvals_approval_id_post_duplicate_data(client, app_context):
    req = _create_approval_request(status="pending")
    payload = {"decision": "approve"}
    with patch("controllers.edit_order_controller.get_current_user", return_value=_create_user(role="head_chef")):
        resp1 = client.post(f"/chef-approvals/{req.id}", json=payload)
        resp2 = client.post(f"/chef-approvals/{req.id}", json=payload)
    assert resp1.status_code in (200, 201)
    assert resp2.status_code in (200, 201, 400, 409, 422)
    if resp2.status_code in (400, 409, 422) and resp2.is_json:
        data = resp2.get_json()
        assert isinstance(data, dict)

# HELPER: get_current_user(N/A)
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(app_context):
    user = _create_user()
    with patch("controllers.edit_order_controller.get_current_user", return_value=user):
        result = get_current_user()
    assert result is user

def test_get_current_user_with_invalid_input(app_context):
    with patch("controllers.edit_order_controller.get_current_user", return_value=None):
        result = get_current_user()
    assert result is None

# HELPER: serialize_order(order)
def test_serialize_order_function_exists():
    assert callable(serialize_order)

def test_serialize_order_with_valid_input(app_context):
    order = _create_order()
    result = serialize_order(order)
    assert isinstance(result, dict)
    assert "id" in result

def test_serialize_order_with_invalid_input():
    with pytest.raises(Exception):
        serialize_order(None)

# HELPER: serialize_order_item(item)
def test_serialize_order_item_function_exists():
    assert callable(serialize_order_item)

def test_serialize_order_item_with_valid_input(app_context):
    item = _create_item()
    result = serialize_order_item(item)
    assert isinstance(result, dict)
    assert "id" in result

def test_serialize_order_item_with_invalid_input():
    with pytest.raises(Exception):
        serialize_order_item(None)

# HELPER: compute_order_totals(order)
def test_compute_order_totals_function_exists():
    assert callable(compute_order_totals)

def test_compute_order_totals_with_valid_input(app_context):
    order = _create_order()
    _create_item(order_id=order.id, unit_price_cents=100, quantity=2)
    _create_item(order_id=order.id, unit_price_cents=250, quantity=1)
    result = compute_order_totals(order)
    assert isinstance(result, dict)
    assert any(k in result for k in ["subtotal_cents", "total_cents", "items_total_cents"])

def test_compute_order_totals_with_invalid_input():
    with pytest.raises(Exception):
        compute_order_totals(None)

# HELPER: validate_edit_payload(payload)
def test_validate_edit_payload_function_exists():
    assert callable(validate_edit_payload)

def test_validate_edit_payload_with_valid_input():
    payload = {"items": [{"dish_id": 1, "quantity": 2}]}
    result = validate_edit_payload(payload)
    assert isinstance(result, dict)

def test_validate_edit_payload_with_invalid_input():
    with pytest.raises(Exception):
        validate_edit_payload(None)

# HELPER: requires_head_chef_approval(order, change_set)
def test_requires_head_chef_approval_function_exists():
    assert callable(requires_head_chef_approval)

def test_requires_head_chef_approval_with_valid_input(app_context):
    order = _create_order()
    change_set = {"op": "update", "items": [{"dish_id": 1, "quantity": 2}]}
    result = requires_head_chef_approval(order, change_set)
    assert isinstance(result, bool)

def test_requires_head_chef_approval_with_invalid_input(app_context):
    order = _create_order()
    with pytest.raises(Exception):
        requires_head_chef_approval(order, None)

# HELPER: create_approval_request(order, requested_by_user, reason, change_set)
def test_create_approval_request_function_exists():
    assert callable(create_approval_request)

def test_create_approval_request_with_valid_input(app_context):
    order = _create_order()
    user = _create_user()
    change_set = {"op": "update", "items": [{"dish_id": 1, "quantity": 2}]}
    req = create_approval_request(order, user, "Need chef approval", change_set)
    assert isinstance(req, EditOrderChefApprovalRequest)
    assert req.order_id == order.id
    assert req.requested_by_user_id == user.id
    assert isinstance(req.change_set_json, str)
    assert req.change_set_json

def test_create_approval_request_with_invalid_input(app_context):
    order = _create_order()
    user = _create_user()
    with pytest.raises(Exception):
        create_approval_request(order, user, None, None)

# HELPER: apply_change_set(order, change_set)
def test_apply_change_set_function_exists():
    assert callable(apply_change_set)

def test_apply_change_set_with_valid_input(app_context):
    order = _create_order()
    _create_item(order_id=order.id, dish_id=10, dish_name="X", unit_price_cents=100, quantity=1)
    change_set = {
        "op": "update",
        "items": [
            {"action": "add", "dish_id": 11, "dish_name": "Y", "unit_price_cents": 200, "quantity": 2},
            {"action": "update", "dish_id": 10, "quantity": 3},
        ],
    }
    result = apply_change_set(order, change_set)
    assert result is None

def test_apply_change_set_with_invalid_input(app_context):
    order = _create_order()
    with pytest.raises(Exception):
        apply_change_set(order, None)