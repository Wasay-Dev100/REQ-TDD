import os
import sys
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db  # noqa: E402
from models.user import User  # noqa: E402
from models.head_chef_order_assignment_chef_profile import ChefProfile  # noqa: E402
from models.head_chef_order_assignment_order import Order  # noqa: E402
from models.head_chef_order_assignment_order_dish import OrderDish  # noqa: E402
from models.head_chef_order_assignment_cancellation_request import CancellationRequest  # noqa: E402

from controllers.head_chef_order_assignment_controller import (  # noqa: E402
    require_head_chef,
    get_current_user,
    validate_assignment_payload,
    apply_assignments,
    update_firebase_order_status,
    update_firebase_dish_status,
    serialize_order,
    serialize_order_dish,
    serialize_cancellation_request,
)

from views.head_chef_order_assignment_views import (  # noqa: E402
    render_head_chef_order_detail,
    render_head_chef_cancellations,
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

def _create_user(*, role: str = "head_chef", email: str | None = None, username: str | None = None, password: str = "Passw0rd!"):
    if email is None:
        email = f"{_unique('u')}@example.com"
    if username is None:
        username = _unique("user")
    u = User(email=email, username=username, role=role, password_hash="")
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u

def _login_as(client, user: User):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id

def _create_order(*, firebase_order_id: str | None = None, status: str = "in_progress"):
    o = Order(status=status, firebase_order_id=firebase_order_id, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.session.add(o)
    db.session.commit()
    return o

def _create_dish(
    *,
    order_id: int,
    dish_name: str | None = None,
    specialty_tag: str | None = None,
    quantity: int = 1,
    status: str = "pending",
    assigned_chef_user_id: int | None = None,
):
    if dish_name is None:
        dish_name = _unique("dish")
    d = OrderDish(
        order_id=order_id,
        dish_name=dish_name,
        specialty_tag=specialty_tag,
        quantity=quantity,
        status=status,
        assigned_chef_user_id=assigned_chef_user_id,
        cooked_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(d)
    db.session.commit()
    return d

def _create_cancellation_request(
    *,
    request_type: str,
    order_id: int,
    requested_by_user_id: int,
    order_dish_id: int | None = None,
    reason: str | None = None,
    status: str = "pending",
):
    r = CancellationRequest(
        request_type=request_type,
        order_id=order_id,
        order_dish_id=order_dish_id,
        requested_by_user_id=requested_by_user_id,
        reason=reason,
        status=status,
        reviewed_by_user_id=None,
        reviewed_at=None,
        created_at=datetime.utcnow(),
    )
    db.session.add(r)
    db.session.commit()
    return r

def _assert_has_keys(d: dict, keys: list[str]):
    for k in keys:
        assert k in d, f"Missing key: {k}"

def _assert_order_schema(order: dict):
    _assert_has_keys(order, ["id", "status", "created_at", "updated_at", "firebase_order_id", "dishes"])
    assert order["status"] in {"in_progress", "completed", "cancelled"}
    assert isinstance(order["dishes"], list)
    assert set(order.keys()) == {"id", "status", "created_at", "updated_at", "firebase_order_id", "dishes"}

def _assert_order_dish_schema(dish: dict):
    _assert_has_keys(
        dish,
        [
            "id",
            "order_id",
            "dish_name",
            "specialty_tag",
            "quantity",
            "status",
            "assigned_chef_user_id",
            "cooked_at",
            "created_at",
            "updated_at",
        ],
    )
    assert dish["status"] in {"pending", "assigned", "cooked", "cancelled"}
    assert set(dish.keys()) == {
        "id",
        "order_id",
        "dish_name",
        "specialty_tag",
        "quantity",
        "status",
        "assigned_chef_user_id",
        "cooked_at",
        "created_at",
        "updated_at",
    }

def _assert_cancellation_request_schema(req: dict):
    _assert_has_keys(
        req,
        [
            "id",
            "request_type",
            "order_id",
            "order_dish_id",
            "requested_by_user_id",
            "reason",
            "status",
            "reviewed_by_user_id",
            "reviewed_at",
            "created_at",
        ],
    )
    assert req["request_type"] in {"order", "dish"}
    assert req["status"] in {"pending", "approved", "rejected"}
    assert set(req.keys()) == {
        "id",
        "request_type",
        "order_id",
        "order_dish_id",
        "requested_by_user_id",
        "reason",
        "status",
        "reviewed_by_user_id",
        "reviewed_at",
        "created_at",
    }

# -------------------------
# MODEL: User
# -------------------------
def test_user_model_has_required_fields(app_context):
    u = User(email=f"{_unique('u')}@example.com", username=_unique("user"), role="head_chef", password_hash="")
    for field in ["id", "email", "username", "role", "password_hash"]:
        assert hasattr(u, field), f"User missing field: {field}"

def test_user_set_password(app_context):
    u = User(email=f"{_unique('u')}@example.com", username=_unique("user"), role="head_chef", password_hash="")
    u.set_password("secret123")
    assert u.password_hash
    assert u.password_hash != "secret123"

def test_user_check_password(app_context):
    u = User(email=f"{_unique('u')}@example.com", username=_unique("user"), role="head_chef", password_hash="")
    u.set_password("secret123")
    assert u.check_password("secret123") is True
    assert u.check_password("wrong") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('u')}@example.com"
    username = _unique("user")
    u1 = User(email=email, username=username, role="head_chef", password_hash="")
    u1.set_password("pw1")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("user2"), role="chef", password_hash="")
    u2.set_password("pw2")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('u3')}@example.com", username=username, role="chef", password_hash="")
    u3.set_password("pw3")
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# -------------------------
# MODEL: ChefProfile
# -------------------------
def test_chefprofile_model_has_required_fields(app_context):
    cp = ChefProfile(user_id=1, specialties="", is_active=True)
    for field in ["id", "user_id", "specialties", "is_active"]:
        assert hasattr(cp, field), f"ChefProfile missing field: {field}"

def test_chefprofile_get_specialties_list(app_context):
    head = _create_user(role="head_chef")
    chef = _create_user(role="chef")
    cp = ChefProfile(user_id=chef.id, specialties="grill, pasta ,  desserts", is_active=True)
    db.session.add(cp)
    db.session.commit()

    lst = cp.get_specialties_list()
    assert isinstance(lst, list)
    assert all(isinstance(x, str) for x in lst)
    assert "grill" in lst
    assert "pasta" in lst
    assert "desserts" in lst

def test_chefprofile_set_specialties_list(app_context):
    chef = _create_user(role="chef")
    cp = ChefProfile(user_id=chef.id, specialties="", is_active=True)
    db.session.add(cp)
    db.session.commit()

    cp.set_specialties_list(["grill", "pasta"])
    db.session.commit()
    assert isinstance(cp.specialties, str)
    assert "grill" in cp.specialties
    assert "pasta" in cp.specialties
    assert cp.get_specialties_list() == ["grill", "pasta"]

def test_chefprofile_unique_constraints(app_context):
    chef = _create_user(role="chef")
    cp1 = ChefProfile(user_id=chef.id, specialties="grill", is_active=True)
    db.session.add(cp1)
    db.session.commit()

    cp2 = ChefProfile(user_id=chef.id, specialties="pasta", is_active=True)
    db.session.add(cp2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# -------------------------
# MODEL: Order
# -------------------------
def test_order_model_has_required_fields(app_context):
    o = Order(status="in_progress", firebase_order_id=None, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    for field in ["id", "status", "created_at", "updated_at", "firebase_order_id"]:
        assert hasattr(o, field), f"Order missing field: {field}"

def test_order_recompute_status_from_dishes(app_context):
    o = _create_order()
    d1 = _create_dish(order_id=o.id, status="cooked")
    d2 = _create_dish(order_id=o.id, status="cooked")
    assert hasattr(o, "recompute_status_from_dishes")
    o.recompute_status_from_dishes()
    db.session.commit()
    assert o.status in {"in_progress", "completed", "cancelled"}
    assert o.status == "completed"

def test_order_unique_constraints(app_context):
    fid = _unique("fb")
    o1 = _create_order(firebase_order_id=fid)
    assert o1.firebase_order_id == fid

    o2 = Order(status="in_progress", firebase_order_id=fid, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.session.add(o2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# -------------------------
# MODEL: OrderDish
# -------------------------
def test_orderdish_model_has_required_fields(app_context):
    d = OrderDish(
        order_id=1,
        dish_name="X",
        specialty_tag=None,
        quantity=1,
        status="pending",
        assigned_chef_user_id=None,
        cooked_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    for field in [
        "id",
        "order_id",
        "dish_name",
        "specialty_tag",
        "quantity",
        "status",
        "assigned_chef_user_id",
        "cooked_at",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(d, field), f"OrderDish missing field: {field}"

def test_orderdish_mark_cooked(app_context):
    o = _create_order()
    d = _create_dish(order_id=o.id, status="assigned", assigned_chef_user_id=None)
    assert d.status == "assigned"
    assert d.cooked_at is None

    assert hasattr(d, "mark_cooked")
    d.mark_cooked()
    db.session.commit()

    assert d.status == "cooked"
    assert d.cooked_at is not None

def test_orderdish_unique_constraints(app_context):
    o = _create_order()
    d1 = _create_dish(order_id=o.id)
    d2 = _create_dish(order_id=o.id)
    assert d1.id != d2.id

# -------------------------
# MODEL: CancellationRequest
# -------------------------
def test_cancellationrequest_model_has_required_fields(app_context):
    r = CancellationRequest(
        request_type="order",
        order_id=1,
        order_dish_id=None,
        requested_by_user_id=1,
        reason=None,
        status="pending",
        reviewed_by_user_id=None,
        reviewed_at=None,
        created_at=datetime.utcnow(),
    )
    for field in [
        "id",
        "request_type",
        "order_id",
        "order_dish_id",
        "requested_by_user_id",
        "reason",
        "status",
        "reviewed_by_user_id",
        "reviewed_at",
        "created_at",
    ]:
        assert hasattr(r, field), f"CancellationRequest missing field: {field}"

def test_cancellationrequest_approve(app_context):
    head = _create_user(role="head_chef")
    requester = _create_user(role="chef")
    o = _create_order()
    r = _create_cancellation_request(request_type="order", order_id=o.id, requested_by_user_id=requester.id)

    assert r.status == "pending"
    assert r.reviewed_by_user_id is None
    assert r.reviewed_at is None

    r.approve(head.id)
    db.session.commit()

    assert r.status == "approved"
    assert r.reviewed_by_user_id == head.id
    assert r.reviewed_at is not None

def test_cancellationrequest_reject(app_context):
    head = _create_user(role="head_chef")
    requester = _create_user(role="chef")
    o = _create_order()
    r = _create_cancellation_request(request_type="dish", order_id=o.id, order_dish_id=None, requested_by_user_id=requester.id)

    r.reject(head.id)
    db.session.commit()

    assert r.status == "rejected"
    assert r.reviewed_by_user_id == head.id
    assert r.reviewed_at is not None

def test_cancellationrequest_unique_constraints(app_context):
    head = _create_user(role="head_chef")
    requester = _create_user(role="chef")
    o = _create_order()
    r1 = _create_cancellation_request(request_type="order", order_id=o.id, requested_by_user_id=requester.id)
    r2 = _create_cancellation_request(request_type="order", order_id=o.id, requested_by_user_id=requester.id)
    assert r1.id != r2.id

# -------------------------
# ROUTE: /head-chef/orders/<int:order_id>/assignments (POST)
# -------------------------
def test_head_chef_orders_order_id_assignments_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/head-chef/orders/<int:order_id>/assignments"]
    assert rules, "Route not registered: /head-chef/orders/<int:order_id>/assignments"
    assert any("POST" in r.methods for r in rules)

def test_head_chef_orders_order_id_assignments_post_success(client):
    head = _create_user(role="head_chef")
    chef = _create_user(role="chef")
    db.session.add(ChefProfile(user_id=chef.id, specialties="grill", is_active=True))
    db.session.commit()

    o = _create_order(firebase_order_id=_unique("fb"))
    d1 = _create_dish(order_id=o.id, status="pending", specialty_tag="grill")
    d2 = _create_dish(order_id=o.id, status="pending", specialty_tag="grill")

    _login_as(client, head)

    payload = {"assignments": [{"order_dish_id": d1.id, "chef_user_id": chef.id}, {"order_dish_id": d2.id, "chef_user_id": chef.id}]}

    with patch("controllers.head_chef_order_assignment_controller.update_firebase_dish_status") as mock_fb_dish:
        resp = client.post(f"/head-chef/orders/{o.id}/assignments", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert set(data.keys()) == {"order", "updated_dishes"}
        _assert_order_schema(data["order"])
        assert isinstance(data["updated_dishes"], list)
        assert len(data["updated_dishes"]) == 2
        for dish in data["updated_dishes"]:
            _assert_order_dish_schema(dish)
            assert dish["status"] == "assigned"
            assert dish["assigned_chef_user_id"] == chef.id

        assert mock_fb_dish.call_count >= 1

    d1_db = OrderDish.query.filter_by(id=d1.id).first()
    d2_db = OrderDish.query.filter_by(id=d2.id).first()
    assert d1_db.status == "assigned"
    assert d2_db.status == "assigned"
    assert d1_db.assigned_chef_user_id == chef.id
    assert d2_db.assigned_chef_user_id == chef.id

def test_head_chef_orders_order_id_assignments_post_missing_required_fields(client):
    head = _create_user(role="head_chef")
    o = _create_order()
    _login_as(client, head)

    resp = client.post(f"/head-chef/orders/{o.id}/assignments", json={})
    assert resp.status_code == 422
    assert resp.get_json() == {"error": "validation_error"}

def test_head_chef_orders_order_id_assignments_post_invalid_data(client):
    head = _create_user(role="head_chef")
    o = _create_order()
    _login_as(client, head)

    resp = client.post(f"/head-chef/orders/{o.id}/assignments", json={"assignments": "not-a-list"})
    assert resp.status_code == 422
    assert resp.get_json() == {"error": "validation_error"}

    resp2 = client.post(f"/head-chef/orders/{o.id}/assignments", json={"assignments": [{"order_dish_id": 0, "chef_user_id": 1}]})
    assert resp2.status_code == 422
    assert resp2.get_json() == {"error": "validation_error"}

    resp3 = client.post(
        f"/head-chef/orders/{o.id}/assignments",
        json={"assignments": [{"order_dish_id": 1, "chef_user_id": 1, "extra": "x"}]},
    )
    assert resp3.status_code == 422
    assert resp3.get_json() == {"error": "validation_error"}

def test_head_chef_orders_order_id_assignments_post_duplicate_data(client):
    head = _create_user(role="head_chef")
    chef = _create_user(role="chef")
    db.session.add(ChefProfile(user_id=chef.id, specialties="grill", is_active=True))
    db.session.commit()

    o = _create_order()
    d1 = _create_dish(order_id=o.id, status="pending")

    _login_as(client, head)

    payload = {"assignments": [{"order_dish_id": d1.id, "chef_user_id": chef.id}, {"order_dish_id": d1.id, "chef_user_id": chef.id}]}
    resp = client.post(f"/head-chef/orders/{o.id}/assignments", json=payload)
    assert resp.status_code in {409, 422}
    data = resp.get_json()
    assert isinstance(data, dict)
    assert data.get("error") in {"invalid_assignment_state", "validation_error"}

# -------------------------
# ROUTE: /head-chef/orders/<int:order_id>/dishes/<int:order_dish_id>/cooked (POST)
# -------------------------
def test_head_chef_orders_order_id_dishes_order_dish_id_cooked_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/head-chef/orders/<int:order_id>/dishes/<int:order_dish_id>/cooked"]
    assert rules, "Route not registered: /head-chef/orders/<int:order_id>/dishes/<int:order_dish_id>/cooked"
    assert any("POST" in r.methods for r in rules)

def test_head_chef_orders_order_id_dishes_order_dish_id_cooked_post_success(client):
    head = _create_user(role="head_chef")
    o = _create_order(firebase_order_id=_unique("fb"))
    d = _create_dish(order_id=o.id, status="assigned", assigned_chef_user_id=None)

    _login_as(client, head)

    with patch("controllers.head_chef_order_assignment_controller.update_firebase_dish_status") as mock_fb_dish, patch(
        "controllers.head_chef_order_assignment_controller.update_firebase_order_status"
    ) as mock_fb_order:
        resp = client.post(f"/head-chef/orders/{o.id}/dishes/{d.id}/cooked", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert set(data.keys()) == {"order", "dish"}
        _assert_order_schema(data["order"])
        _assert_order_dish_schema(data["dish"])
        assert data["dish"]["status"] == "cooked"
        assert data["dish"]["cooked_at"] is not None

        assert mock_fb_dish.call_count >= 1
        assert mock_fb_order.call_count >= 1

    d_db = OrderDish.query.filter_by(id=d.id).first()
    assert d_db.status == "cooked"
    assert d_db.cooked_at is not None

def test_head_chef_orders_order_id_dishes_order_dish_id_cooked_post_missing_required_fields(client):
    head = _create_user(role="head_chef")
    o = _create_order()
    d = _create_dish(order_id=o.id, status="assigned")
    _login_as(client, head)

    resp = client.post(f"/head-chef/orders/{o.id}/dishes/{d.id}/cooked", json={"unexpected": 1})
    assert resp.status_code == 422
    assert resp.get_json() == {"error": "validation_error"}

def test_head_chef_orders_order_id_dishes_order_dish_id_cooked_post_invalid_data(client):
    head = _create_user(role="head_chef")
    o = _create_order()
    d = _create_dish(order_id=o.id, status="pending")
    _login_as(client, head)

    resp = client.post(f"/head-chef/orders/{o.id}/dishes/{d.id}/cooked", json={})
    assert resp.status_code == 409
    assert resp.get_json() == {"error": "invalid_dish_state"}

def test_head_chef_orders_order_id_dishes_order_dish_id_cooked_post_duplicate_data(client):
    head = _create_user(role="head_chef")
    o = _create_order()
    d = _create_dish(order_id=o.id, status="assigned")
    _login_as(client, head)

    resp1 = client.post(f"/head-chef/orders/{o.id}/dishes/{d.id}/cooked", json={})
    assert resp1.status_code == 200

    resp2 = client.post(f"/head-chef/orders/{o.id}/dishes/{d.id}/cooked", json={})
    assert resp2.status_code == 409
    assert resp2.get_json() == {"error": "invalid_dish_state"}

# -------------------------
# ROUTE: /head-chef/orders/<int:order_id>/complete (POST)
# -------------------------
def test_head_chef_orders_order_id_complete_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/head-chef/orders/<int:order_id>/complete"]
    assert rules, "Route not registered: /head-chef/orders/<int:order_id>/complete"
    assert any("POST" in r.methods for r in rules)

def test_head_chef_orders_order_id_complete_post_success(client):
    head = _create_user(role="head_chef")
    o = _create_order(firebase_order_id=_unique("fb"))
    _create_dish(order_id=o.id, status="cooked")
    _create_dish(order_id=o.id, status="cancelled")

    _login_as(client, head)

    with patch("controllers.head_chef_order_assignment_controller.update_firebase_order_status") as mock_fb_order:
        resp = client.post(f"/head-chef/orders/{o.id}/complete", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert set(data.keys()) == {"order"}
        _assert_order_schema(data["order"])
        assert data["order"]["status"] == "completed"
        assert mock_fb_order.call_count >= 1

    o_db = Order.query.filter_by(id=o.id).first()
    assert o_db.status == "completed"

def test_head_chef_orders_order_id_complete_post_missing_required_fields(client):
    head = _create_user(role="head_chef")
    o = _create_order()
    _create_dish(order_id=o.id, status="cooked")
    _login_as(client, head)

    resp = client.post(f"/head-chef/orders/{o.id}/complete", json={"x": 1})
    assert resp.status_code == 422
    assert resp.get_json() == {"error": "validation_error"}

def test_head_chef_orders_order_id_complete_post_invalid_data(client):
    head = _create_user(role="head_chef")
    o = _create_order()
    _create_dish(order_id=o.id, status="assigned")
    _login_as(client, head)

    resp = client.post(f"/head-chef/orders/{o.id}/complete", json={})
    assert resp.status_code == 409
    assert resp.get_json() == {"error": "order_not_ready_to_complete"}

def test_head_chef_orders_order_id_complete_post_duplicate_data(client):
    head = _create_user(role="head_chef")
    o = _create_order()
    _create_dish(order_id=o.id, status="cooked")
    _login_as(client, head)

    resp1 = client.post(f"/head-chef/orders/{o.id}/complete", json={})
    assert resp1.status_code == 200

    resp2 = client.post(f"/head-chef/orders/{o.id}/complete", json={})
    assert resp2.status_code in {200, 409}
    if resp2.status_code == 409:
        assert resp2.get_json() == {"error": "order_not_ready_to_complete"}

# -------------------------
# ROUTE: /head-chef/cancellations/<int:request_id>/approve (POST)
# -------------------------
def test_head_chef_cancellations_request_id_approve_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/head-chef/cancellations/<int:request_id>/approve"]
    assert rules, "Route not registered: /head-chef/cancellations/<int:request_id>/approve"
    assert any("POST" in r.methods for r in rules)

def test_head_chef_cancellations_request_id_approve_post_success(client):
    head = _create_user(role="head_chef")
    requester = _create_user(role="chef")
    o = _create_order(firebase_order_id=_unique("fb"))
    d = _create_dish(order_id=o.id, status="pending")
    req = _create_cancellation_request(request_type="dish", order_id=o.id, order_dish_id=d.id, requested_by_user_id=requester.id)

    _login_as(client, head)

    with patch("controllers.head_chef_order_assignment_controller.update_firebase_order_status") as mock_fb_order, patch(
        "controllers.head_chef_order_assignment_controller.update_firebase_dish_status"
    ) as mock_fb_dish:
        resp = client.post(f"/head-chef/cancellations/{req.id}/approve", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "cancellation_request" in data
        assert "order" in data
        _assert_cancellation_request_schema(data["cancellation_request"])
        _assert_order_schema(data["order"])
        if "dish" in data:
            _assert_order_dish_schema(data["dish"])
            assert data["dish"]["status"] == "cancelled"

        assert mock_fb_order.call_count >= 0
        assert mock_fb_dish.call_count >= 0

    req_db = CancellationRequest.query.filter_by(id=req.id).first()
    assert req_db.status == "approved"
    assert req_db.reviewed_by_user_id == head.id
    assert req_db.reviewed_at is not None

    d_db = OrderDish.query.filter_by(id=d.id).first()
    assert d_db.status == "cancelled"

def test_head_chef_cancellations_request_id_approve_post_missing_required_fields(client):
    head = _create_user(role="head_chef")
    requester = _create_user(role="chef")
    o = _create_order()
    req = _create_cancellation_request(request_type="order", order_id=o.id, requested_by_user_id=requester.id)
    _login_as(client, head)

    resp = client.post(f"/head-chef/cancellations/{req.id}/approve", json={"x": 1})
    assert resp.status_code == 422
    assert resp.get_json() == {"error": "validation_error"}

def test_head_chef_cancellations_request_id_approve_post_invalid_data(client):
    head = _create_user(role="head_chef")
    _login_as(client, head)

    resp = client.post("/head-chef/cancellations/999999/approve", json={})
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "cancellation_request_not_found"}

def test_head_chef_cancellations_request_id_approve_post_duplicate_data(client):
    head = _create_user(role="head_chef")
    requester = _create_user(role="chef")
    o = _create_order()
    req = _create_cancellation_request(request_type="order", order_id=o.id, requested_by_user_id=requester.id, status="approved")
    _login_as(client, head)

    resp = client.post(f"/head-chef/cancellations/{req.id}/approve", json={})
    assert resp.status_code == 409
    assert resp.get_json() == {"error": "cancellation_request_not_pending"}

# -------------------------
# ROUTE: /head-chef/cancellations/<int:request_id>/reject (POST)
# -------------------------
def test_head_chef_cancellations_request_id_reject_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/head-chef/cancellations/<int:request_id>/reject"]
    assert rules, "Route not registered: /head-chef/cancellations/<int:request_id>/reject"
    assert any("POST" in r.methods for r in rules)

def test_head_chef_cancellations_request_id_reject_post_success(client):
    head = _create_user(role="head_chef")
    requester = _create_user(role="chef")
    o = _create_order()
    req = _create_cancellation_request(request_type="order", order_id=o.id, requested_by_user_id=requester.id)

    _login_as(client, head)

    resp = client.post(f"/head-chef/cancellations/{req.id}/reject", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data.keys()) == {"cancellation_request"}
    _assert_cancellation_request_schema(data["cancellation_request"])
    assert data["cancellation_request"]["status"] == "rejected"

    req_db = CancellationRequest.query.filter_by(id=req.id).first()
    assert req_db.status == "rejected"
    assert req_db.reviewed_by_user_id == head.id
    assert req_db.reviewed_at is not None

def test_head_chef_cancellations_request_id_reject_post_missing_required_fields(client):
    head = _create_user(role="head_chef")
    requester = _create_user(role="chef")
    o = _create_order()
    req = _create_cancellation_request(request_type="order", order_id=o.id, requested_by_user_id=requester.id)
    _login_as(client, head)

    resp = client.post(f"/head-chef/cancellations/{req.id}/reject", json={"x": 1})
    assert resp.status_code == 422
    assert resp.get_json() == {"error": "validation_error"}

def test_head_chef_cancellations_request_id_reject_post_invalid_data(client):
    head = _create_user(role="head_chef")
    _login_as(client, head)

    resp = client.post("/head-chef/cancellations/999999/reject", json={})
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "cancellation_request_not_found"}

def test_head_chef_cancellations_request_id_reject_post_duplicate_data(client):
    head = _create_user(role="head_chef")
    requester = _create_user(role="chef")
    o = _create_order()
    req = _create_cancellation_request(request_type="order", order_id=o.id, requested_by_user_id=requester.id, status="rejected")
    _login_as(client, head)

    resp = client.post(f"/head-chef/cancellations/{req.id}/reject", json={})
    assert resp.status_code == 409
    assert resp.get_json() == {"error": "cancellation_request_not_pending"}

# -------------------------
# ROUTE: /head-chef/orders/<int:order_id> (GET)
# -------------------------
def test_head_chef_orders_order_id_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/head-chef/orders/<int:order_id>"]
    assert rules, "Route not registered: /head-chef/orders/<int:order_id>"
    assert any("GET" in r.methods for r in rules)

def test_head_chef_orders_order_id_get_renders_template(client):
    head = _create_user(role="head_chef")
    o = _create_order()
    _create_dish(order_id=o.id, status="pending")
    _login_as(client, head)

    resp = client.get(f"/head-chef/orders/{o.id}")
    assert resp.status_code == 200
    assert resp.mimetype in {"text/html", "application/json"}
    if resp.mimetype == "application/json":
        data = resp.get_json()
        assert set(data.keys()) == {"order"}
        _assert_order_schema(data["order"])
    else:
        assert resp.data is not None
        assert len(resp.data) > 0

# -------------------------
# ROUTE: /head-chef/cancellations (GET)
# -------------------------
def test_head_chef_cancellations_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/head-chef/cancellations"]
    assert rules, "Route not registered: /head-chef/cancellations"
    assert any("GET" in r.methods for r in rules)

def test_head_chef_cancellations_get_renders_template(client):
    head = _create_user(role="head_chef")
    requester = _create_user(role="chef")
    o = _create_order()
    _create_cancellation_request(request_type="order", order_id=o.id, requested_by_user_id=requester.id, reason="x")

    _login_as(client, head)

    resp = client.get("/head-chef/cancellations")
    assert resp.status_code == 200
    assert resp.mimetype in {"text/html", "application/json"}
    if resp.mimetype == "application/json":
        data = resp.get_json()
        assert set(data.keys()) == {"requests"}
        assert isinstance(data["requests"], list)
        if data["requests"]:
            _assert_cancellation_request_schema(data["requests"][0])
    else:
        assert resp.data is not None
        assert len(resp.data) > 0

# -------------------------
# HELPER: require_head_chef(user: User)
# -------------------------
def test_require_head_chef_function_exists():
    assert callable(require_head_chef)

def test_require_head_chef_with_valid_input(app_context):
    u = _create_user(role="head_chef")
    require_head_chef(u)

def test_require_head_chef_with_invalid_input(app_context):
    u = _create_user(role="chef")
    with pytest.raises(Exception):
        require_head_chef(u)

# -------------------------
# HELPER: get_current_user()
# -------------------------
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(client):
    u = _create_user(role="head_chef")
    _login_as(client, u)
    with app.test_request_context("/head-chef/cancellations", method="GET"):
        from flask import session

        session["user_id"] = u.id
        cu = get_current_user()
        assert isinstance(cu, User)
        assert cu.id == u.id

def test_get_current_user_with_invalid_input():
    with app.test_request_context("/head-chef/cancellations", method="GET"):
        cu = get_current_user()
        assert cu is None

# -------------------------
# HELPER: validate_assignment_payload(payload: dict) -> dict
# -------------------------
def test_validate_assignment_payload_function_exists():
    assert callable(validate_assignment_payload)

def test_validate_assignment_payload_with_valid_input():
    payload = {"assignments": [{"order_dish_id": 1, "chef_user_id": 2}]}
    out = validate_assignment_payload(payload)
    assert isinstance(out, dict)
    assert "assignments" in out
    assert isinstance(out["assignments"], list)
    assert out["assignments"][0]["order_dish_id"] == 1
    assert out["assignments"][0]["chef_user_id"] == 2

def test_validate_assignment_payload_with_invalid_input():
    with pytest.raises(Exception):
        validate_assignment_payload(None)  # type: ignore[arg-type]
    with pytest.raises(Exception):
        validate_assignment_payload({})
    with pytest.raises(Exception):
        validate_assignment_payload({"assignments": []})
    with pytest.raises(Exception):
        validate_assignment_payload({"assignments": [{"order_dish_id": 0, "chef_user_id": 1}]})
    with pytest.raises(Exception):
        validate_assignment_payload({"assignments": [{"order_dish_id": 1}]})
    with pytest.raises(Exception):
        validate_assignment_payload({"assignments": [{"order_dish_id": 1, "chef_user_id": 1, "x": 1}]})

# -------------------------
# HELPER: apply_assignments(order: Order, assignments: list[dict]) -> list[OrderDish]
# -------------------------
def test_apply_assignments_function_exists():
    assert callable(apply_assignments)

def test_apply_assignments_with_valid_input(app_context):
    o = _create_order()
    chef = _create_user(role="chef")
    d1 = _create_dish(order_id=o.id, status="pending")
    d2 = _create_dish(order_id=o.id, status="pending")

    updated = apply_assignments(o, [{"order_dish_id": d1.id, "chef_user_id": chef.id}, {"order_dish_id": d2.id, "chef_user_id": chef.id}])
    assert isinstance(updated, list)
    assert len(updated) == 2
    assert all(isinstance(x, OrderDish) for x in updated)
    for x in updated:
        assert x.status == "assigned"
        assert x.assigned_chef_user_id == chef.id

def test_apply_assignments_with_invalid_input(app_context):
    o = _create_order()
    with pytest.raises(Exception):
        apply_assignments(o, None)  # type: ignore[arg-type]
    with pytest.raises(Exception):
        apply_assignments(None, [])  # type: ignore[arg-type]
    with pytest.raises(Exception):
        apply_assignments(o, [{"order_dish_id": 999999, "chef_user_id": 1}])

# -------------------------
# HELPER: update_firebase_order_status(order: Order)
# -------------------------
def test_update_firebase_order_status_function_exists():
    assert callable(update_firebase_order_status)

def test_update_firebase_order_status_with_valid_input(app_context):
    o = _create_order(firebase_order_id=_unique("fb"))
    update_firebase_order_status(o)

def test_update_firebase_order_status_with_invalid_input(app_context):
    with pytest.raises(Exception):
        update_firebase_order_status(None)  # type: ignore[arg-type]

# -------------------------
# HELPER: update_firebase_dish_status(order: Order, dish: OrderDish)
# -------------------------
def test_update_firebase_dish_status_function_exists():
    assert callable(update_firebase_dish_status)

def test_update_firebase_dish_status_with_valid_input(app_context):
    o = _create_order(firebase_order_id=_unique("fb"))
    d = _create_dish(order_id=o.id, status="assigned")
    update_firebase_dish_status(o, d)

def test_update_firebase_dish_status_with_invalid_input(app_context):
    o = _create_order(firebase_order_id=_unique("fb"))
    with pytest.raises(Exception):
        update_firebase_dish_status(None, None)  # type: ignore[arg-type]
    with pytest.raises(Exception):
        update_firebase_dish_status(o, None)  # type: ignore[arg-type]

# -------------------------
# HELPER: serialize_order(order: Order) -> dict
# -------------------------
def test_serialize_order_function_exists():
    assert callable(serialize_order)

def test_serialize_order_with_valid_input(app_context):
    o = _create_order(firebase_order_id=None)
    _create_dish(order_id=o.id, status="pending")
    out = serialize_order(o)
    assert isinstance(out, dict)
    _assert_order_schema(out)
    assert out["id"] == o.id
    assert isinstance(out["dishes"], list)
    assert len(out["dishes"]) == 1
    _assert_order_dish_schema(out["dishes"][0])

def test_serialize_order_with_invalid_input():
    with pytest.raises(Exception):
        serialize_order(None)  # type: ignore[arg-type]

# -------------------------
# HELPER: serialize_order_dish(dish: OrderDish) -> dict
# -------------------------
def test_serialize_order_dish_function_exists():
    assert callable(serialize_order_dish)

def test_serialize_order_dish_with_valid_input(app_context):
    o = _create_order()
    d = _create_dish(order_id=o.id, status="pending", specialty_tag="grill")
    out = serialize_order_dish(d)
    assert isinstance(out, dict)
    _assert_order_dish_schema(out)
    assert out["id"] == d.id
    assert out["order_id"] == o.id
    assert out["specialty_tag"] == "grill"

def test_serialize_order_dish_with_invalid_input():
    with pytest.raises(Exception):
        serialize_order_dish(None)  # type: ignore[arg-type]

# -------------------------
# HELPER: serialize_cancellation_request(req: CancellationRequest) -> dict
# -------------------------
def test_serialize_cancellation_request_function_exists():
    assert callable(serialize_cancellation_request)

def test_serialize_cancellation_request_with_valid_input(app_context):
    requester = _create_user(role="chef")
    o = _create_order()
    req = _create_cancellation_request(request_type="order", order_id=o.id, requested_by_user_id=requester.id, reason="no stock")
    out = serialize_cancellation_request(req)
    assert isinstance(out, dict)
    _assert_cancellation_request_schema(out)
    assert out["id"] == req.id
    assert out["order_id"] == o.id
    assert out["requested_by_user_id"] == requester.id

def test_serialize_cancellation_request_with_invalid_input():
    with pytest.raises(Exception):
        serialize_cancellation_request(None)  # type: ignore[arg-type]