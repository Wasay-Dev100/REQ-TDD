import os
import sys
import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.cancel_order_order import CancelOrderOrder
from models.cancel_order_order_item import CancelOrderOrderItem
from models.cancel_order_cancellation_request import CancelOrderCancellationRequest
from models.cancel_order_dish_cancellation_decision import CancelOrderDishCancellationDecision
from controllers.cancel_order_controller import (
    get_current_user,
    require_role,
    serialize_order_item,
    serialize_cancellation_request,
    create_cancellation_request_with_pending_decisions,
    apply_approved_cancellations,
)
from views.cancel_order_views import render_cancel_confirmation_popup

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

def _create_user(*, role="CUSTOMER"):
    u = User(email=f"{_unique('email')}@example.com", username=_unique("user"), role=role)
    u.set_password("Password123!")
    db.session.add(u)
    db.session.commit()
    return u

def _create_order(*, customer_id: int, status="PLACED", served_at=None):
    o = CancelOrderOrder(customer_id=customer_id, status=status, served_at=served_at)
    db.session.add(o)
    db.session.commit()
    return o

def _create_order_item(*, order_id: int, dish_name=None, quantity=1, status="PENDING"):
    name = dish_name or _unique("dish")
    item = CancelOrderOrderItem(order_id=order_id, dish_name=name, quantity=quantity, status=status)
    db.session.add(item)
    db.session.commit()
    return item

def _create_cancellation_request(*, order_id: int, requested_by_user_id: int, status="PENDING_CHEF_APPROVAL", reason=None):
    req = CancelOrderCancellationRequest(
        order_id=order_id,
        requested_by_user_id=requested_by_user_id,
        status=status,
        customer_reason=reason,
    )
    db.session.add(req)
    db.session.commit()
    return req

def _create_decision(
    *,
    cancellation_request_id: int,
    order_item_id: int,
    decision_status="PENDING",
    decided_by_user_id=None,
    decision_note=None,
    decided_at=None,
):
    d = CancelOrderDishCancellationDecision(
        cancellation_request_id=cancellation_request_id,
        order_item_id=order_item_id,
        decision_status=decision_status,
        decided_by_user_id=decided_by_user_id,
        decision_note=decision_note,
        decided_at=decided_at,
    )
    db.session.add(d)
    db.session.commit()
    return d

def _set_current_user_in_session(client, user_id: int, role: str):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["role"] = role

def _route_exists(rule: str, method: str) -> bool:
    for r in app.url_map.iter_rules():
        if r.rule == rule and method in r.methods:
            return True
    return False

def _find_rule_by_endpoint_suffix(suffix: str):
    for r in app.url_map.iter_rules():
        if r.endpoint.endswith(suffix):
            return r
    return None

def _assert_error_json(resp, expected_status: int):
    assert resp.status_code == expected_status
    data = resp.get_json(silent=True)
    assert isinstance(data, dict)
    assert "error" in data
    assert isinstance(data["error"], str)
    assert data["error"]

def _assert_cancellation_request_schema(obj: dict):
    assert isinstance(obj, dict)
    required = [
        "id",
        "order_id",
        "requested_by_user_id",
        "status",
        "customer_reason",
        "created_at",
        "updated_at",
        "dish_decisions",
    ]
    for k in required:
        assert k in obj
    assert isinstance(obj["id"], int)
    assert isinstance(obj["order_id"], int)
    assert isinstance(obj["requested_by_user_id"], int)
    assert obj["status"] in {"PENDING_CHEF_APPROVAL", "PARTIALLY_APPROVED", "APPROVED", "REJECTED"}
    assert (obj["customer_reason"] is None) or isinstance(obj["customer_reason"], str)
    assert isinstance(obj["created_at"], str)
    assert isinstance(obj["updated_at"], str)
    assert isinstance(obj["dish_decisions"], list)
    for d in obj["dish_decisions"]:
        assert isinstance(d, dict)
        d_required = [
            "id",
            "order_item_id",
            "dish_name",
            "quantity",
            "decision_status",
            "decided_by_user_id",
            "decision_note",
            "decided_at",
        ]
        for k in d_required:
            assert k in d
        assert isinstance(d["id"], int)
        assert isinstance(d["order_item_id"], int)
        assert isinstance(d["dish_name"], str)
        assert isinstance(d["quantity"], int)
        assert d["decision_status"] in {"PENDING", "APPROVED_DROP", "REJECTED_KEEP"}
        assert (d["decided_by_user_id"] is None) or isinstance(d["decided_by_user_id"], int)
        assert (d["decision_note"] is None) or isinstance(d["decision_note"], str)
        assert (d["decided_at"] is None) or isinstance(d["decided_at"], str)

def _assert_submit_result_schema(obj: dict):
    assert isinstance(obj, dict)
    required = ["order_id", "order_status", "dropped_item_ids", "kept_item_ids"]
    for k in required:
        assert k in obj
    assert isinstance(obj["order_id"], int)
    assert obj["order_status"] in {"PLACED", "IN_PROGRESS", "SERVED", "CANCEL_PENDING_CHEF", "CANCELLED"}
    assert isinstance(obj["dropped_item_ids"], list)
    assert isinstance(obj["kept_item_ids"], list)
    assert all(isinstance(x, int) for x in obj["dropped_item_ids"])
    assert all(isinstance(x, int) for x in obj["kept_item_ids"])

# MODEL: User (models/user.py)
def test_user_model_has_required_fields():
    for field in ["id", "email", "username", "password_hash", "role", "created_at"]:
        assert hasattr(User, field), f"Missing required field on User: {field}"

def test_user_set_password():
    u = User(email=f"{_unique('email')}@example.com", username=_unique("user"), role="CUSTOMER")
    u.set_password("Password123!")
    assert u.password_hash
    assert isinstance(u.password_hash, str)
    assert "Password123!" not in u.password_hash

def test_user_check_password():
    u = User(email=f"{_unique('email')}@example.com", username=_unique("user"), role="CUSTOMER")
    u.set_password("Password123!")
    assert u.check_password("Password123!") is True
    assert u.check_password("WrongPassword!") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('email')}@example.com"
    username = _unique("user")

    u1 = User(email=email, username=username, role="CUSTOMER")
    u1.set_password("Password123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("user2"), role="CUSTOMER")
    u2.set_password("Password123!")
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('email2')}@example.com", username=username, role="CUSTOMER")
    u3.set_password("Password123!")
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: CancelOrderOrder (models/cancel_order_order.py)
def test_cancelorderorder_model_has_required_fields():
    for field in ["id", "customer_id", "status", "served_at", "created_at", "updated_at"]:
        assert hasattr(CancelOrderOrder, field), f"Missing required field on CancelOrderOrder: {field}"

def test_cancelorderorder_is_cancellable(app_context):
    order1 = _create_order(customer_id=1, status="PLACED", served_at=None)
    assert hasattr(order1, "is_cancellable")
    assert callable(order1.is_cancellable)
    assert order1.is_cancellable() is True

    served_time = datetime.utcnow()
    order2 = _create_order(customer_id=1, status="SERVED", served_at=served_time)
    assert order2.is_cancellable() is False

def test_cancelorderorder_unique_constraints(app_context):
    order1 = _create_order(customer_id=1, status="PLACED", served_at=None)
    order2 = _create_order(customer_id=1, status="PLACED", served_at=None)
    assert order1.id != order2.id

# MODEL: CancelOrderOrderItem (models/cancel_order_order_item.py)
def test_cancelorderorderitem_model_has_required_fields():
    for field in ["id", "order_id", "dish_name", "quantity", "status", "created_at", "updated_at"]:
        assert hasattr(CancelOrderOrderItem, field), f"Missing required field on CancelOrderOrderItem: {field}"

def test_cancelorderorderitem_unique_constraints(app_context):
    order = _create_order(customer_id=1, status="PLACED")
    i1 = _create_order_item(order_id=order.id, dish_name="SameDish", quantity=1)
    i2 = _create_order_item(order_id=order.id, dish_name="SameDish", quantity=2)
    assert i1.id != i2.id

# MODEL: CancelOrderCancellationRequest (models/cancel_order_cancellation_request.py)
def test_cancelordercancellationrequest_model_has_required_fields():
    for field in ["id", "order_id", "requested_by_user_id", "status", "customer_reason", "created_at", "updated_at"]:
        assert hasattr(CancelOrderCancellationRequest, field), f"Missing required field on CancelOrderCancellationRequest: {field}"

def test_cancelordercancellationrequest_unique_constraints(app_context):
    user = _create_user(role="CUSTOMER")
    order = _create_order(customer_id=user.id, status="PLACED")
    r1 = _create_cancellation_request(order_id=order.id, requested_by_user_id=user.id, status="PENDING_CHEF_APPROVAL")
    r2 = _create_cancellation_request(order_id=order.id, requested_by_user_id=user.id, status="REJECTED")
    assert r1.id != r2.id

# MODEL: CancelOrderDishCancellationDecision (models/cancel_order_dish_cancellation_decision.py)
def test_cancelorderdishcancellationdecision_model_has_required_fields():
    for field in [
        "id",
        "cancellation_request_id",
        "order_item_id",
        "decision_status",
        "decided_by_user_id",
        "decision_note",
        "decided_at",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(CancelOrderDishCancellationDecision, field), (
            f"Missing required field on CancelOrderDishCancellationDecision: {field}"
        )

def test_cancelorderdishcancellationdecision_unique_constraints(app_context):
    user = _create_user(role="CUSTOMER")
    order = _create_order(customer_id=user.id, status="PLACED")
    item = _create_order_item(order_id=order.id)
    req = _create_cancellation_request(order_id=order.id, requested_by_user_id=user.id)
    d1 = _create_decision(cancellation_request_id=req.id, order_item_id=item.id, decision_status="PENDING")
    d2 = _create_decision(cancellation_request_id=req.id, order_item_id=item.id, decision_status="PENDING")
    assert d1.id != d2.id

# ROUTE: /orders/<int:order_id>/cancel (POST) - request_cancel_order
def test_orders_order_id_cancel_post_exists():
    assert _route_exists("/orders/<int:order_id>/cancel", "POST"), "Missing POST route /orders/<int:order_id>/cancel"

def test_orders_order_id_cancel_post_success(client):
    user = _create_user(role="CUSTOMER")
    order = _create_order(customer_id=user.id, status="IN_PROGRESS", served_at=None)
    _create_order_item(order_id=order.id, dish_name="DishA", quantity=1, status="PENDING")
    _create_order_item(order_id=order.id, dish_name="DishB", quantity=2, status="COOKING")

    _set_current_user_in_session(client, user.id, user.role)

    resp = client.post(f"/orders/{order.id}/cancel", json={"reason": "Changed my mind"})
    assert resp.status_code == 202
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "cancellation_request" in data
    _assert_cancellation_request_schema(data["cancellation_request"])
    assert data["cancellation_request"]["order_id"] == order.id
    assert data["cancellation_request"]["requested_by_user_id"] == user.id
    assert data["cancellation_request"]["customer_reason"] == "Changed my mind"
    assert len(data["cancellation_request"]["dish_decisions"]) == 2
    assert all(d["decision_status"] == "PENDING" for d in data["cancellation_request"]["dish_decisions"])

def test_orders_order_id_cancel_post_missing_required_fields(client):
    user = _create_user(role="CUSTOMER")
    order = _create_order(customer_id=user.id, status="PLACED", served_at=None)
    _create_order_item(order_id=order.id, dish_name="DishA", quantity=1, status="PENDING")
    _set_current_user_in_session(client, user.id, user.role)

    resp = client.post(f"/orders/{order.id}/cancel", json={})
    assert resp.status_code == 202
    data = resp.get_json()
    assert "cancellation_request" in data
    _assert_cancellation_request_schema(data["cancellation_request"])
    assert data["cancellation_request"]["customer_reason"] in (None, "")

def test_orders_order_id_cancel_post_invalid_data(client):
    user = _create_user(role="CUSTOMER")
    order = _create_order(customer_id=user.id, status="PLACED", served_at=None)
    _create_order_item(order_id=order.id, dish_name="DishA", quantity=1, status="PENDING")
    _set_current_user_in_session(client, user.id, user.role)

    resp = client.post(f"/orders/{order.id}/cancel", json={"reason": "x" * 256})
    _assert_error_json(resp, 400)

def test_orders_order_id_cancel_post_duplicate_data(client):
    user = _create_user(role="CUSTOMER")
    order = _create_order(customer_id=user.id, status="IN_PROGRESS", served_at=None)
    _create_order_item(order_id=order.id, dish_name="DishA", quantity=1, status="PENDING")
    _set_current_user_in_session(client, user.id, user.role)

    resp1 = client.post(f"/orders/{order.id}/cancel", json={"reason": "First"})
    assert resp1.status_code == 202

    resp2 = client.post(f"/orders/{order.id}/cancel", json={"reason": "Second"})
    _assert_error_json(resp2, 409)

# ROUTE: /cancellation-requests/<int:request_id> (GET) - get_cancellation_request
def test_cancellation_requests_request_id_get_exists():
    assert _route_exists("/cancellation-requests/<int:request_id>", "GET"), (
        "Missing GET route /cancellation-requests/<int:request_id>"
    )

def test_cancellation_requests_request_id_get_renders_template(client):
    user = _create_user(role="CUSTOMER")
    order = _create_order(customer_id=user.id, status="CANCEL_PENDING_CHEF", served_at=None)
    item = _create_order_item(order_id=order.id, dish_name="DishA", quantity=1, status="PENDING")
    req = _create_cancellation_request(order_id=order.id, requested_by_user_id=user.id, status="PENDING_CHEF_APPROVAL")
    _create_decision(cancellation_request_id=req.id, order_item_id=item.id, decision_status="PENDING")

    _set_current_user_in_session(client, user.id, user.role)

    resp = client.get(f"/cancellation-requests/{req.id}")
    assert resp.status_code == 200
    content_type = resp.headers.get("Content-Type", "")
    assert ("text/html" in content_type) or ("application/json" in content_type)

    if "application/json" in content_type:
        data = resp.get_json()
        _assert_cancellation_request_schema(data)
        assert data["id"] == req.id
    else:
        assert resp.data is not None
        assert len(resp.data) > 0

# ROUTE: /cancellation-requests/<int:request_id>/chef-decisions (POST) - submit_chef_decisions
def test_cancellation_requests_request_id_chef_decisions_post_exists():
    assert _route_exists("/cancellation-requests/<int:request_id>/chef-decisions", "POST"), (
        "Missing POST route /cancellation-requests/<int:request_id>/chef-decisions"
    )

def test_cancellation_requests_request_id_chef_decisions_post_success(client):
    customer = _create_user(role="CUSTOMER")
    chef = _create_user(role="HEAD_CHEF")
    order = _create_order(customer_id=customer.id, status="CANCEL_PENDING_CHEF", served_at=None)
    item1 = _create_order_item(order_id=order.id, dish_name="DishA", quantity=1, status="COOKING")
    item2 = _create_order_item(order_id=order.id, dish_name="DishB", quantity=2, status="READY")
    req = _create_cancellation_request(order_id=order.id, requested_by_user_id=customer.id, status="PENDING_CHEF_APPROVAL")
    _create_decision(cancellation_request_id=req.id, order_item_id=item1.id, decision_status="PENDING")
    _create_decision(cancellation_request_id=req.id, order_item_id=item2.id, decision_status="PENDING")

    _set_current_user_in_session(client, chef.id, chef.role)

    payload = {
        "decisions": [
            {"order_item_id": item1.id, "decision_status": "APPROVED_DROP", "decision_note": "Ok"},
            {"order_item_id": item2.id, "decision_status": "REJECTED_KEEP", "decision_note": "Already prepared"},
        ]
    }
    resp = client.post(f"/cancellation-requests/{req.id}/chef-decisions", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "cancellation_request" in data
    assert "result" in data
    _assert_cancellation_request_schema(data["cancellation_request"])
    _assert_submit_result_schema(data["result"])
    assert data["result"]["order_id"] == order.id
    assert item1.id in data["result"]["dropped_item_ids"]
    assert item2.id in data["result"]["kept_item_ids"]

def test_cancellation_requests_request_id_chef_decisions_post_missing_required_fields(client):
    chef = _create_user(role="HEAD_CHEF")
    _set_current_user_in_session(client, chef.id, chef.role)

    resp = client.post("/cancellation-requests/1/chef-decisions", json={})
    _assert_error_json(resp, 400)

def test_cancellation_requests_request_id_chef_decisions_post_invalid_data(client):
    customer = _create_user(role="CUSTOMER")
    chef = _create_user(role="HEAD_CHEF")
    order = _create_order(customer_id=customer.id, status="CANCEL_PENDING_CHEF", served_at=None)
    item = _create_order_item(order_id=order.id, dish_name="DishA", quantity=1, status="PENDING")
    req = _create_cancellation_request(order_id=order.id, requested_by_user_id=customer.id, status="PENDING_CHEF_APPROVAL")
    _create_decision(cancellation_request_id=req.id, order_item_id=item.id, decision_status="PENDING")

    _set_current_user_in_session(client, chef.id, chef.role)

    resp = client.post(
        f"/cancellation-requests/{req.id}/chef-decisions",
        json={"decisions": [{"order_item_id": item.id, "decision_status": "INVALID"}]},
    )
    _assert_error_json(resp, 400)

def test_cancellation_requests_request_id_chef_decisions_post_duplicate_data(client):
    customer = _create_user(role="CUSTOMER")
    chef = _create_user(role="HEAD_CHEF")
    order = _create_order(customer_id=customer.id, status="CANCEL_PENDING_CHEF", served_at=None)
    item = _create_order_item(order_id=order.id, dish_name="DishA", quantity=1, status="PENDING")
    req = _create_cancellation_request(order_id=order.id, requested_by_user_id=customer.id, status="PENDING_CHEF_APPROVAL")
    _create_decision(cancellation_request_id=req.id, order_item_id=item.id, decision_status="PENDING")

    _set_current_user_in_session(client, chef.id, chef.role)

    payload = {
        "decisions": [
            {"order_item_id": item.id, "decision_status": "APPROVED_DROP"},
            {"order_item_id": item.id, "decision_status": "REJECTED_KEEP"},
        ]
    }
    resp = client.post(f"/cancellation-requests/{req.id}/chef-decisions", json=payload)
    assert resp.status_code in (200, 400)

# HELPER: get_current_user(N/A)
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(app_context):
    user = _create_user(role="CUSTOMER")
    with app.test_request_context("/"):
        from flask import session

        session["user_id"] = user.id
        session["role"] = user.role
        current = get_current_user()
        assert current is not None
        assert isinstance(current, User)
        assert current.id == user.id

def test_get_current_user_with_invalid_input(app_context):
    with app.test_request_context("/"):
        from flask import session

        session.pop("user_id", None)
        session.pop("role", None)
        current = get_current_user()
        assert current is None

# HELPER: require_role(user, role)
def test_require_role_function_exists():
    assert callable(require_role)

def test_require_role_with_valid_input(app_context):
    user = _create_user(role="HEAD_CHEF")
    require_role(user, "HEAD_CHEF")

def test_require_role_with_invalid_input(app_context):
    user = _create_user(role="CUSTOMER")
    with pytest.raises(Exception):
        require_role(user, "HEAD_CHEF")

# HELPER: serialize_order_item(item)
def test_serialize_order_item_function_exists():
    assert callable(serialize_order_item)

def test_serialize_order_item_with_valid_input(app_context):
    user = _create_user(role="CUSTOMER")
    order = _create_order(customer_id=user.id, status="PLACED")
    item = _create_order_item(order_id=order.id, dish_name="DishA", quantity=2, status="PENDING")
    data = serialize_order_item(item)
    assert isinstance(data, dict)
    for k in ["id", "order_item_id", "dish_name", "quantity"]:
        assert k in data
    assert data["dish_name"] == "DishA"
    assert data["quantity"] == 2

def test_serialize_order_item_with_invalid_input():
    with pytest.raises(Exception):
        serialize_order_item(None)

# HELPER: serialize_cancellation_request(req)
def test_serialize_cancellation_request_function_exists():
    assert callable(serialize_cancellation_request)

def test_serialize_cancellation_request_with_valid_input(app_context):
    customer = _create_user(role="CUSTOMER")
    order = _create_order(customer_id=customer.id, status="CANCEL_PENDING_CHEF")
    item = _create_order_item(order_id=order.id, dish_name="DishA", quantity=1, status="PENDING")
    req = _create_cancellation_request(order_id=order.id, requested_by_user_id=customer.id, status="PENDING_CHEF_APPROVAL", reason="Reason")
    _create_decision(cancellation_request_id=req.id, order_item_id=item.id, decision_status="PENDING")

    data = serialize_cancellation_request(req)
    _assert_cancellation_request_schema(data)
    assert data["id"] == req.id
    assert data["order_id"] == order.id
    assert data["requested_by_user_id"] == customer.id
    assert data["customer_reason"] == "Reason"
    assert len(data["dish_decisions"]) == 1

def test_serialize_cancellation_request_with_invalid_input():
    with pytest.raises(Exception):
        serialize_cancellation_request(None)

# HELPER: create_cancellation_request_with_pending_decisions(order, requested_by_user_id, customer_reason)
def test_create_cancellation_request_with_pending_decisions_function_exists():
    assert callable(create_cancellation_request_with_pending_decisions)

def test_create_cancellation_request_with_pending_decisions_with_valid_input(app_context):
    customer = _create_user(role="CUSTOMER")
    order = _create_order(customer_id=customer.id, status="IN_PROGRESS", served_at=None)
    item1 = _create_order_item(order_id=order.id, dish_name="DishA", quantity=1, status="PENDING")
    item2 = _create_order_item(order_id=order.id, dish_name="DishB", quantity=2, status="COOKING")

    req = create_cancellation_request_with_pending_decisions(order, customer.id, "Need to leave")
    assert req is not None
    assert isinstance(req, CancelOrderCancellationRequest)
    assert req.order_id == order.id
    assert req.requested_by_user_id == customer.id
    assert req.customer_reason == "Need to leave"

    decisions = CancelOrderDishCancellationDecision.query.filter_by(cancellation_request_id=req.id).all()
    assert len(decisions) == 2
    decision_item_ids = {d.order_item_id for d in decisions}
    assert decision_item_ids == {item1.id, item2.id}
    assert all(d.decision_status == "PENDING" for d in decisions)

def test_create_cancellation_request_with_pending_decisions_with_invalid_input(app_context):
    with pytest.raises(Exception):
        create_cancellation_request_with_pending_decisions(None, 1, None)

# HELPER: apply_approved_cancellations(req)
def test_apply_approved_cancellations_function_exists():
    assert callable(apply_approved_cancellations)

def test_apply_approved_cancellations_with_valid_input(app_context):
    customer = _create_user(role="CUSTOMER")
    chef = _create_user(role="HEAD_CHEF")
    order = _create_order(customer_id=customer.id, status="CANCEL_PENDING_CHEF", served_at=None)
    item1 = _create_order_item(order_id=order.id, dish_name="DishA", quantity=1, status="COOKING")
    item2 = _create_order_item(order_id=order.id, dish_name="DishB", quantity=2, status="READY")
    req = _create_cancellation_request(order_id=order.id, requested_by_user_id=customer.id, status="PENDING_CHEF_APPROVAL")

    d1 = _create_decision(
        cancellation_request_id=req.id,
        order_item_id=item1.id,
        decision_status="APPROVED_DROP",
        decided_by_user_id=chef.id,
        decision_note="Ok",
        decided_at=datetime.utcnow(),
    )
    d2 = _create_decision(
        cancellation_request_id=req.id,
        order_item_id=item2.id,
        decision_status="REJECTED_KEEP",
        decided_by_user_id=chef.id,
        decision_note="Keep",
        decided_at=datetime.utcnow(),
    )
    assert d1.id != d2.id

    result = apply_approved_cancellations(req)
    _assert_submit_result_schema(result)
    assert result["order_id"] == order.id
    assert item1.id in result["dropped_item_ids"]
    assert item2.id in result["kept_item_ids"]

def test_apply_approved_cancellations_with_invalid_input():
    with pytest.raises(Exception):
        apply_approved_cancellations(None)