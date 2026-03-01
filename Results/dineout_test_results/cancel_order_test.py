import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db  # noqa: E402
from models.user import User  # noqa: E402
from models.cancel_order_order import CancelOrderOrder  # noqa: E402
from models.cancel_order_order_item import CancelOrderOrderItem  # noqa: E402
from models.cancel_order_cancellation_request import CancelOrderCancellationRequest  # noqa: E402
from models.cancel_order_cancellation_dish_approval import CancelOrderCancellationDishApproval  # noqa: E402

from controllers.cancel_order_controller import (  # noqa: E402
    get_current_user,
    ensure_customer_owns_order,
    ensure_head_chef,
    build_cancellation_request_for_order,
    finalize_cancellation_request,
)

from views.cancel_order_views import (  # noqa: E402
    render_cancel_success_popup_payload,
    render_cancel_failure_popup_payload,
    serialize_cancellation_request,
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

def _create_user(*, role="customer"):
    u = User(
        email=f"{_unique('u')}@example.com",
        username=_unique("user"),
        password_hash="",
        role=role,
    )
    u.set_password("password123!")
    db.session.add(u)
    db.session.commit()
    return u

def _login_as(client, user: User):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id

def _create_order(*, customer_id: int, status: str = "PLACED", served_at=None):
    o = CancelOrderOrder(
        customer_id=customer_id,
        status=status,
        created_at=datetime.now(timezone.utc),
        served_at=served_at,
        canceled_at=None,
        cancel_reason=None,
    )
    db.session.add(o)
    db.session.commit()
    return o

def _create_order_item(*, order_id: int, dish_name: str, quantity: int = 1, status: str = "PLACED"):
    oi = CancelOrderOrderItem(
        order_id=order_id,
        dish_name=dish_name,
        quantity=quantity,
        status=status,
        dropped_at=None,
    )
    db.session.add(oi)
    db.session.commit()
    return oi

def _create_cancellation_request(*, order_id: int, requested_by_user_id: int, status: str = "PENDING_APPROVAL"):
    cr = CancelOrderCancellationRequest(
        order_id=order_id,
        requested_by_user_id=requested_by_user_id,
        status=status,
        requested_at=datetime.now(timezone.utc),
        finalized_at=None,
    )
    db.session.add(cr)
    db.session.commit()
    return cr

def _create_dish_approval(
    *,
    cancellation_request_id: int,
    order_item_id: int,
    decision: str = "PENDING",
    decided_by_user_id=None,
    decided_at=None,
    note=None,
):
    da = CancelOrderCancellationDishApproval(
        cancellation_request_id=cancellation_request_id,
        order_item_id=order_item_id,
        decision=decision,
        decided_by_user_id=decided_by_user_id,
        decided_at=decided_at,
        note=note,
    )
    db.session.add(da)
    db.session.commit()
    return da

# =========================
# MODEL: User (models/user.py)
# =========================
def test_user_model_has_required_fields(app_context):
    user = User(email="a@b.com", username="abc", password_hash="x", role="customer")
    for field in ["id", "email", "username", "password_hash", "role"]:
        assert hasattr(user, field), f"Missing field: {field}"

def test_user_set_password(app_context):
    user = User(email=f"{_unique('e')}@example.com", username=_unique("u"), password_hash="", role="customer")
    user.set_password("secret123!")
    assert user.password_hash
    assert user.password_hash != "secret123!"

def test_user_check_password(app_context):
    user = User(email=f"{_unique('e')}@example.com", username=_unique("u"), password_hash="", role="customer")
    user.set_password("secret123!")
    assert user.check_password("secret123!") is True
    assert user.check_password("wrong") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")

    u1 = User(email=email, username=username, password_hash="", role="customer")
    u1.set_password("password123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("otheruser"), password_hash="", role="customer")
    u2.set_password("password123!")
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, password_hash="", role="customer")
    u3.set_password("password123!")
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()

# =========================
# MODEL: CancelOrderOrder (models/cancel_order_order.py)
# =========================
def test_cancelorderorder_model_has_required_fields(app_context):
    order = CancelOrderOrder(
        customer_id=1,
        status="PLACED",
        created_at=datetime.now(timezone.utc),
        served_at=None,
        canceled_at=None,
        cancel_reason=None,
    )
    for field in ["id", "customer_id", "status", "created_at", "served_at", "canceled_at", "cancel_reason"]:
        assert hasattr(order, field), f"Missing field: {field}"

def test_cancelorderorder_is_cancelable(app_context):
    order1 = CancelOrderOrder(
        customer_id=1,
        status="PLACED",
        created_at=datetime.now(timezone.utc),
        served_at=None,
        canceled_at=None,
        cancel_reason=None,
    )
    assert order1.is_cancelable() is True

    order2 = CancelOrderOrder(
        customer_id=1,
        status="SERVED",
        created_at=datetime.now(timezone.utc),
        served_at=datetime.now(timezone.utc),
        canceled_at=None,
        cancel_reason=None,
    )
    assert order2.is_cancelable() is False

def test_cancelorderorder_unique_constraints(app_context):
    order1 = CancelOrderOrder(
        customer_id=1,
        status="PLACED",
        created_at=datetime.now(timezone.utc),
        served_at=None,
        canceled_at=None,
        cancel_reason=None,
    )
    order2 = CancelOrderOrder(
        customer_id=1,
        status="PLACED",
        created_at=datetime.now(timezone.utc),
        served_at=None,
        canceled_at=None,
        cancel_reason=None,
    )
    db.session.add_all([order1, order2])
    db.session.commit()
    assert order1.id is not None and order2.id is not None

# =========================
# MODEL: CancelOrderOrderItem (models/cancel_order_order_item.py)
# =========================
def test_cancelorderorderitem_model_has_required_fields(app_context):
    item = CancelOrderOrderItem(
        order_id=1,
        dish_name="Dish",
        quantity=1,
        status="PLACED",
        dropped_at=None,
    )
    for field in ["id", "order_id", "dish_name", "quantity", "status", "dropped_at"]:
        assert hasattr(item, field), f"Missing field: {field}"

def test_cancelorderorderitem_is_droppable(app_context):
    item1 = CancelOrderOrderItem(order_id=1, dish_name="Dish", quantity=1, status="PLACED", dropped_at=None)
    assert item1.is_droppable() is True

    item2 = CancelOrderOrderItem(
        order_id=1,
        dish_name="Dish",
        quantity=1,
        status="DROPPED",
        dropped_at=datetime.now(timezone.utc),
    )
    assert item2.is_droppable() is False

def test_cancelorderorderitem_unique_constraints(app_context):
    item1 = CancelOrderOrderItem(order_id=1, dish_name="Dish1", quantity=1, status="PLACED", dropped_at=None)
    item2 = CancelOrderOrderItem(order_id=1, dish_name="Dish1", quantity=1, status="PLACED", dropped_at=None)
    db.session.add_all([item1, item2])
    db.session.commit()
    assert item1.id is not None and item2.id is not None

# =========================
# MODEL: CancelOrderCancellationRequest (models/cancel_order_cancellation_request.py)
# =========================
def test_cancelordercancellationrequest_model_has_required_fields(app_context):
    cr = CancelOrderCancellationRequest(
        order_id=1,
        requested_by_user_id=2,
        status="PENDING_APPROVAL",
        requested_at=datetime.now(timezone.utc),
        finalized_at=None,
    )
    for field in ["id", "order_id", "requested_by_user_id", "status", "requested_at", "finalized_at"]:
        assert hasattr(cr, field), f"Missing field: {field}"

def test_cancelordercancellationrequest_is_pending(app_context):
    cr1 = CancelOrderCancellationRequest(
        order_id=1,
        requested_by_user_id=2,
        status="PENDING_APPROVAL",
        requested_at=datetime.now(timezone.utc),
        finalized_at=None,
    )
    assert cr1.is_pending() is True

    cr2 = CancelOrderCancellationRequest(
        order_id=1,
        requested_by_user_id=2,
        status="FINALIZED",
        requested_at=datetime.now(timezone.utc),
        finalized_at=datetime.now(timezone.utc),
    )
    assert cr2.is_pending() is False

def test_cancelordercancellationrequest_unique_constraints(app_context):
    cr1 = CancelOrderCancellationRequest(
        order_id=123,
        requested_by_user_id=1,
        status="PENDING_APPROVAL",
        requested_at=datetime.now(timezone.utc),
        finalized_at=None,
    )
    db.session.add(cr1)
    db.session.commit()

    cr2 = CancelOrderCancellationRequest(
        order_id=123,
        requested_by_user_id=2,
        status="PENDING_APPROVAL",
        requested_at=datetime.now(timezone.utc),
        finalized_at=None,
    )
    db.session.add(cr2)
    with pytest.raises(IntegrityError):
        db.session.commit()

# =========================
# MODEL: CancelOrderCancellationDishApproval (models/cancel_order_cancellation_dish_approval.py)
# =========================
def test_cancelordercancellationdishapproval_model_has_required_fields(app_context):
    da = CancelOrderCancellationDishApproval(
        cancellation_request_id=1,
        order_item_id=2,
        decision="PENDING",
        decided_by_user_id=None,
        decided_at=None,
        note=None,
    )
    for field in [
        "id",
        "cancellation_request_id",
        "order_item_id",
        "decision",
        "decided_by_user_id",
        "decided_at",
        "note",
    ]:
        assert hasattr(da, field), f"Missing field: {field}"

def test_cancelordercancellationdishapproval_is_decided(app_context):
    da1 = CancelOrderCancellationDishApproval(
        cancellation_request_id=1,
        order_item_id=2,
        decision="PENDING",
        decided_by_user_id=None,
        decided_at=None,
        note=None,
    )
    assert da1.is_decided() is False

    da2 = CancelOrderCancellationDishApproval(
        cancellation_request_id=1,
        order_item_id=2,
        decision="APPROVED_DROP",
        decided_by_user_id=10,
        decided_at=datetime.now(timezone.utc),
        note="ok",
    )
    assert da2.is_decided() is True

def test_cancelordercancellationdishapproval_unique_constraints(app_context):
    da1 = CancelOrderCancellationDishApproval(
        cancellation_request_id=1,
        order_item_id=2,
        decision="PENDING",
        decided_by_user_id=None,
        decided_at=None,
        note=None,
    )
    da2 = CancelOrderCancellationDishApproval(
        cancellation_request_id=1,
        order_item_id=2,
        decision="PENDING",
        decided_by_user_id=None,
        decided_at=None,
        note=None,
    )
    db.session.add_all([da1, da2])
    db.session.commit()
    assert da1.id is not None and da2.id is not None

# =========================
# ROUTE: /orders/<int:order_id>/cancel (POST)
# =========================
def test_orders_order_id_cancel_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/orders/<int:order_id>/cancel"]
    assert rules, "Route /orders/<int:order_id>/cancel not registered"
    assert any("POST" in r.methods for r in rules), "Route /orders/<int:order_id>/cancel does not accept POST"

def test_orders_order_id_cancel_post_success(client):
    with app.app_context():
        customer = _create_user(role="customer")
        order = _create_order(customer_id=customer.id, status="IN_PREP", served_at=None)
        _create_order_item(order_id=order.id, dish_name="Pasta", quantity=1, status="IN_PREP")
        _create_order_item(order_id=order.id, dish_name="Salad", quantity=2, status="PLACED")

    _login_as(client, customer)
    resp = client.post(f"/orders/{order.id}/cancel", json={"reason": "Changed mind"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {
        "success": True,
        "message": "Order canceled successfully",
        "order_id": order.id,
        "cancellation_request_id": data["cancellation_request_id"],
        "status": "CANCEL_REQUESTED",
    }
    assert isinstance(data["cancellation_request_id"], int)

    with app.app_context():
        refreshed = CancelOrderOrder.query.filter_by(id=order.id).first()
        assert refreshed is not None
        assert refreshed.status == "CANCEL_REQUESTED"
        assert refreshed.cancel_reason in (None, "Changed mind")

        cr = CancelOrderCancellationRequest.query.filter_by(id=data["cancellation_request_id"]).first()
        assert cr is not None
        assert cr.order_id == order.id
        assert cr.status == "PENDING_APPROVAL"

        approvals = CancelOrderCancellationDishApproval.query.filter_by(cancellation_request_id=cr.id).all()
        assert len(approvals) == 2
        assert all(a.decision == "PENDING" for a in approvals)

def test_orders_order_id_cancel_post_missing_required_fields(client):
    with app.app_context():
        customer = _create_user(role="customer")
        order = _create_order(customer_id=customer.id, status="PLACED", served_at=None)
        _create_order_item(order_id=order.id, dish_name="Soup", quantity=1, status="PLACED")

    _login_as(client, customer)
    resp = client.post(f"/orders/{order.id}/cancel", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["message"] == "Order canceled successfully"
    assert data["order_id"] == order.id
    assert data["status"] == "CANCEL_REQUESTED"
    assert isinstance(data["cancellation_request_id"], int)

def test_orders_order_id_cancel_post_invalid_data(client):
    with app.app_context():
        customer = _create_user(role="customer")
        order = _create_order(customer_id=customer.id, status="PLACED", served_at=None)
        _create_order_item(order_id=order.id, dish_name="Soup", quantity=1, status="PLACED")

    _login_as(client, customer)
    resp = client.post(f"/orders/{order.id}/cancel", json={"reason": "x" * 256})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert data["message"] == "Order cannot be cancelled"
    assert data["order_id"] == order.id
    assert data["reason_code"] in {
        "ORDER_ALREADY_SERVED",
        "ORDER_NOT_FOUND",
        "NOT_AUTHENTICATED",
        "NOT_ORDER_OWNER",
        "CANCELLATION_ALREADY_REQUESTED",
    }

def test_orders_order_id_cancel_post_duplicate_data(client):
    with app.app_context():
        customer = _create_user(role="customer")
        order = _create_order(customer_id=customer.id, status="IN_PREP", served_at=None)
        _create_order_item(order_id=order.id, dish_name="Burger", quantity=1, status="IN_PREP")

    _login_as(client, customer)
    resp1 = client.post(f"/orders/{order.id}/cancel", json={"reason": "First"})
    assert resp1.status_code == 200

    resp2 = client.post(f"/orders/{order.id}/cancel", json={"reason": "Second"})
    assert resp2.status_code == 400
    data2 = resp2.get_json()
    assert data2["success"] is False
    assert data2["message"] == "Order cannot be cancelled"
    assert data2["order_id"] == order.id
    assert data2["reason_code"] == "CANCELLATION_ALREADY_REQUESTED"

# =========================
# ROUTE: /cancellations/<int:cancellation_request_id> (GET)
# =========================
def test_cancellations_cancellation_request_id_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/cancellations/<int:cancellation_request_id>"]
    assert rules, "Route /cancellations/<int:cancellation_request_id> not registered"
    assert any("GET" in r.methods for r in rules), "Route /cancellations/<int:cancellation_request_id> does not accept GET"

def test_cancellations_cancellation_request_id_get_renders_template(client):
    with app.app_context():
        customer = _create_user(role="customer")
        order = _create_order(customer_id=customer.id, status="CANCEL_REQUESTED", served_at=None)
        item = _create_order_item(order_id=order.id, dish_name="Pizza", quantity=1, status="IN_PREP")
        cr = _create_cancellation_request(order_id=order.id, requested_by_user_id=customer.id, status="PENDING_APPROVAL")
        _create_dish_approval(cancellation_request_id=cr.id, order_item_id=item.id, decision="PENDING")

    resp = client.get(f"/cancellations/{cr.id}")
    assert resp.status_code == 200
    assert resp.is_json is True
    data = resp.get_json()
    for key in ["id", "order_id", "status", "requested_by_user_id", "requested_at", "dish_approvals"]:
        assert key in data
    assert data["id"] == cr.id
    assert data["order_id"] == order.id
    assert data["status"] in {"PENDING_APPROVAL", "FINALIZED"}
    assert isinstance(data["dish_approvals"], list)
    assert len(data["dish_approvals"]) == 1
    approval = data["dish_approvals"][0]
    for key in ["id", "order_item_id", "dish_name", "quantity", "decision", "decided_by_user_id", "decided_at", "note"]:
        assert key in approval
    assert approval["order_item_id"] == item.id

# =========================
# ROUTE: /cancellations/<int:cancellation_request_id>/approve (POST)
# =========================
def test_cancellations_cancellation_request_id_approve_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/cancellations/<int:cancellation_request_id>/approve"]
    assert rules, "Route /cancellations/<int:cancellation_request_id>/approve not registered"
    assert any("POST" in r.methods for r in rules), "Route /cancellations/<int:cancellation_request_id>/approve does not accept POST"

def test_cancellations_cancellation_request_id_approve_post_success(client):
    with app.app_context():
        customer = _create_user(role="customer")
        head_chef = _create_user(role="head_chef")
        order = _create_order(customer_id=customer.id, status="CANCEL_REQUESTED", served_at=None)
        item1 = _create_order_item(order_id=order.id, dish_name="Steak", quantity=1, status="IN_PREP")
        item2 = _create_order_item(order_id=order.id, dish_name="Fries", quantity=1, status="READY")
        cr = _create_cancellation_request(order_id=order.id, requested_by_user_id=customer.id, status="PENDING_APPROVAL")
        _create_dish_approval(cancellation_request_id=cr.id, order_item_id=item1.id, decision="PENDING")
        _create_dish_approval(cancellation_request_id=cr.id, order_item_id=item2.id, decision="PENDING")

    _login_as(client, head_chef)
    resp = client.post(
        f"/cancellations/{cr.id}/approve",
        json={
            "decisions": [
                {"order_item_id": item1.id, "decision": "APPROVED_DROP", "note": "ok"},
                {"order_item_id": item2.id, "decision": "REJECTED_KEEP"},
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["cancellation_request_id"] == cr.id
    assert data["order_id"] == order.id
    assert data["status"] == "FINALIZED"
    assert set(data["dropped_order_item_ids"]) == {item1.id}
    assert set(data["kept_order_item_ids"]) == {item2.id}

    with app.app_context():
        refreshed_cr = CancelOrderCancellationRequest.query.filter_by(id=cr.id).first()
        assert refreshed_cr.status == "FINALIZED"
        assert refreshed_cr.finalized_at is not None

        refreshed_item1 = CancelOrderOrderItem.query.filter_by(id=item1.id).first()
        refreshed_item2 = CancelOrderOrderItem.query.filter_by(id=item2.id).first()
        assert refreshed_item1.status == "DROPPED"
        assert refreshed_item1.dropped_at is not None
        assert refreshed_item2.status in {"PLACED", "IN_PREP", "READY", "SERVED"}

        refreshed_order = CancelOrderOrder.query.filter_by(id=order.id).first()
        assert refreshed_order.status in {"CANCELED", "IN_PREP"}

def test_cancellations_cancellation_request_id_approve_post_missing_required_fields(client):
    with app.app_context():
        customer = _create_user(role="customer")
        head_chef = _create_user(role="head_chef")
        order = _create_order(customer_id=customer.id, status="CANCEL_REQUESTED", served_at=None)
        item = _create_order_item(order_id=order.id, dish_name="Tea", quantity=1, status="PLACED")
        cr = _create_cancellation_request(order_id=order.id, requested_by_user_id=customer.id, status="PENDING_APPROVAL")
        _create_dish_approval(cancellation_request_id=cr.id, order_item_id=item.id, decision="PENDING")

    _login_as(client, head_chef)
    resp = client.post(f"/cancellations/{cr.id}/approve", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "message" in data
    assert data["reason_code"] in {
        "NOT_AUTHENTICATED",
        "NOT_HEAD_CHEF",
        "CANCELLATION_NOT_PENDING",
        "INVALID_DECISIONS",
        "ORDER_ITEM_NOT_IN_ORDER",
    }

def test_cancellations_cancellation_request_id_approve_post_invalid_data(client):
    with app.app_context():
        customer = _create_user(role="customer")
        head_chef = _create_user(role="head_chef")
        order = _create_order(customer_id=customer.id, status="CANCEL_REQUESTED", served_at=None)
        item = _create_order_item(order_id=order.id, dish_name="Tea", quantity=1, status="PLACED")
        cr = _create_cancellation_request(order_id=order.id, requested_by_user_id=customer.id, status="PENDING_APPROVAL")
        _create_dish_approval(cancellation_request_id=cr.id, order_item_id=item.id, decision="PENDING")

    _login_as(client, head_chef)
    resp = client.post(
        f"/cancellations/{cr.id}/approve",
        json={"decisions": [{"order_item_id": item.id, "decision": "PENDING"}]},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "message" in data
    assert data["reason_code"] in {
        "NOT_AUTHENTICATED",
        "NOT_HEAD_CHEF",
        "CANCELLATION_NOT_PENDING",
        "INVALID_DECISIONS",
        "ORDER_ITEM_NOT_IN_ORDER",
    }

def test_cancellations_cancellation_request_id_approve_post_duplicate_data(client):
    with app.app_context():
        customer = _create_user(role="customer")
        head_chef = _create_user(role="head_chef")
        order = _create_order(customer_id=customer.id, status="CANCEL_REQUESTED", served_at=None)
        item = _create_order_item(order_id=order.id, dish_name="Cake", quantity=1, status="READY")
        cr = _create_cancellation_request(order_id=order.id, requested_by_user_id=customer.id, status="PENDING_APPROVAL")
        _create_dish_approval(cancellation_request_id=cr.id, order_item_id=item.id, decision="PENDING")

    _login_as(client, head_chef)
    resp = client.post(
        f"/cancellations/{cr.id}/approve",
        json={"decisions": [{"order_item_id": item.id, "decision": "APPROVED_DROP"}]},
    )
    assert resp.status_code == 200

    resp2 = client.post(
        f"/cancellations/{cr.id}/approve",
        json={"decisions": [{"order_item_id": item.id, "decision": "REJECTED_KEEP"}]},
    )
    assert resp2.status_code == 400
    data2 = resp2.get_json()
    assert data2["success"] is False
    assert "message" in data2
    assert data2["reason_code"] in {
        "NOT_AUTHENTICATED",
        "NOT_HEAD_CHEF",
        "CANCELLATION_NOT_PENDING",
        "INVALID_DECISIONS",
        "ORDER_ITEM_NOT_IN_ORDER",
    }

# =========================
# HELPER: get_current_user()
# =========================
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(client):
    with app.app_context():
        user = _create_user(role="customer")
    _login_as(client, user)

    with app.test_request_context("/"):
        from flask import session

        session["user_id"] = user.id
        current = get_current_user()
        assert current is not None
        assert isinstance(current, User)
        assert current.id == user.id

def test_get_current_user_with_invalid_input():
    with app.test_request_context("/"):
        from flask import session

        session.pop("user_id", None)
        current = get_current_user()
        assert current is None

# =========================
# HELPER: ensure_customer_owns_order(user, order)
# =========================
def test_ensure_customer_owns_order_function_exists():
    assert callable(ensure_customer_owns_order)

def test_ensure_customer_owns_order_with_valid_input(app_context):
    customer = _create_user(role="customer")
    order = _create_order(customer_id=customer.id, status="PLACED", served_at=None)
    ensure_customer_owns_order(customer, order)

def test_ensure_customer_owns_order_with_invalid_input(app_context):
    customer = _create_user(role="customer")
    other = _create_user(role="customer")
    order = _create_order(customer_id=other.id, status="PLACED", served_at=None)
    with pytest.raises(Exception):
        ensure_customer_owns_order(customer, order)

# =========================
# HELPER: ensure_head_chef(user)
# =========================
def test_ensure_head_chef_function_exists():
    assert callable(ensure_head_chef)

def test_ensure_head_chef_with_valid_input(app_context):
    head_chef = _create_user(role="head_chef")
    ensure_head_chef(head_chef)

def test_ensure_head_chef_with_invalid_input(app_context):
    customer = _create_user(role="customer")
    with pytest.raises(Exception):
        ensure_head_chef(customer)

# =========================
# HELPER: build_cancellation_request_for_order(order, requested_by_user_id)
# =========================
def test_build_cancellation_request_for_order_function_exists():
    assert callable(build_cancellation_request_for_order)

def test_build_cancellation_request_for_order_with_valid_input(app_context):
    customer = _create_user(role="customer")
    order = _create_order(customer_id=customer.id, status="IN_PREP", served_at=None)
    _create_order_item(order_id=order.id, dish_name="A", quantity=1, status="IN_PREP")
    _create_order_item(order_id=order.id, dish_name="B", quantity=2, status="READY")

    cr = build_cancellation_request_for_order(order, customer.id)
    assert cr is not None
    assert isinstance(cr, CancelOrderCancellationRequest)
    assert cr.order_id == order.id
    assert cr.requested_by_user_id == customer.id
    assert cr.status == "PENDING_APPROVAL"

    db.session.add(cr)
    db.session.commit()

    approvals = CancelOrderCancellationDishApproval.query.filter_by(cancellation_request_id=cr.id).all()
    assert len(approvals) == 2
    assert all(a.decision == "PENDING" for a in approvals)

def test_build_cancellation_request_for_order_with_invalid_input(app_context):
    customer = _create_user(role="customer")
    order = _create_order(customer_id=customer.id, status="IN_PREP", served_at=None)
    with pytest.raises(Exception):
        build_cancellation_request_for_order(None, customer.id)
    with pytest.raises(Exception):
        build_cancellation_request_for_order(order, None)

# =========================
# HELPER: finalize_cancellation_request(cancellation_request, decided_by_user_id)
# =========================
def test_finalize_cancellation_request_function_exists():
    assert callable(finalize_cancellation_request)

def test_finalize_cancellation_request_with_valid_input(app_context):
    customer = _create_user(role="customer")
    head_chef = _create_user(role="head_chef")
    order = _create_order(customer_id=customer.id, status="CANCEL_REQUESTED", served_at=None)
    item1 = _create_order_item(order_id=order.id, dish_name="X", quantity=1, status="IN_PREP")
    item2 = _create_order_item(order_id=order.id, dish_name="Y", quantity=1, status="READY")
    cr = _create_cancellation_request(order_id=order.id, requested_by_user_id=customer.id, status="PENDING_APPROVAL")
    _create_dish_approval(
        cancellation_request_id=cr.id,
        order_item_id=item1.id,
        decision="APPROVED_DROP",
        decided_by_user_id=head_chef.id,
        decided_at=datetime.now(timezone.utc),
        note=None,
    )
    _create_dish_approval(
        cancellation_request_id=cr.id,
        order_item_id=item2.id,
        decision="REJECTED_KEEP",
        decided_by_user_id=head_chef.id,
        decided_at=datetime.now(timezone.utc),
        note="keep",
    )

    result = finalize_cancellation_request(cr, head_chef.id)
    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["cancellation_request_id"] == cr.id
    assert result["order_id"] == order.id
    assert result["status"] == "FINALIZED"
    assert set(result["dropped_order_item_ids"]) == {item1.id}
    assert set(result["kept_order_item_ids"]) == {item2.id}

    refreshed_cr = CancelOrderCancellationRequest.query.filter_by(id=cr.id).first()
    assert refreshed_cr.status == "FINALIZED"
    assert refreshed_cr.finalized_at is not None

def test_finalize_cancellation_request_with_invalid_input(app_context):
    head_chef = _create_user(role="head_chef")
    with pytest.raises(Exception):
        finalize_cancellation_request(None, head_chef.id)
    with pytest.raises(Exception):
        finalize_cancellation_request("not-a-request", head_chef.id)
    with pytest.raises(Exception):
        finalize_cancellation_request(_create_cancellation_request(order_id=999, requested_by_user_id=head_chef.id), None)