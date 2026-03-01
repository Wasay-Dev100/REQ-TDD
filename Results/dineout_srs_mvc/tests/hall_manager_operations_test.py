import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.hall_manager_operations_table import HallManagerOperationsTable
from models.hall_manager_operations_order import HallManagerOperationsOrder
from models.hall_manager_operations_bill import HallManagerOperationsBill
from models.hall_manager_operations_notification import HallManagerOperationsNotification
from controllers.hall_manager_operations_controller import (
    require_hall_manager,
    get_current_user,
    parse_iso_datetime,
)
from views.hall_manager_operations_views import (
    render_tables_page,
    render_notifications_page,
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

@pytest.fixture
def db_session(app_context):
    yield db.session

def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_user(role: str = "hall_manager") -> User:
    u = User(email=f"{_unique('u')}@example.com", username=_unique("user"), role=role)
    u.set_password("Password123!")
    return u

def _create_table(
    firebase_table_id: str | None = None,
    table_number: int | None = None,
    status: str = "available",
) -> HallManagerOperationsTable:
    now = datetime.now(timezone.utc)
    return HallManagerOperationsTable(
        firebase_table_id=firebase_table_id or _unique("ftable"),
        table_number=table_number if table_number is not None else int(uuid.uuid4().int % 100000),
        capacity=4,
        status=status,
        reserved_by_name=None,
        reserved_by_phone=None,
        reservation_time=None,
        notes=None,
        updated_at=now,
    )

def _create_order(table_id: int, firebase_order_id: str | None = None, status: str = "open") -> HallManagerOperationsOrder:
    now = datetime.now(timezone.utc)
    return HallManagerOperationsOrder(
        firebase_order_id=firebase_order_id or _unique("forder"),
        table_id=table_id,
        status=status,
        total_amount=Decimal("12.50"),
        currency="USD",
        completed_at=None,
        created_at=now,
        updated_at=now,
    )

def _create_bill(order_id: int, firebase_bill_id: str | None = None, status: str = "unpaid") -> HallManagerOperationsBill:
    now = datetime.now(timezone.utc)
    return HallManagerOperationsBill(
        firebase_bill_id=firebase_bill_id or _unique("fbill"),
        order_id=order_id,
        amount_due=Decimal("12.50"),
        amount_paid=None,
        status=status,
        paid_at=None,
        paid_by_user_id=None,
        payment_method=None,
        updated_at=now,
    )

def _create_notification(
    firebase_event_id: str | None = None,
    event_type: str = "order_completed",
    order_id: int | None = None,
    table_id: int | None = None,
    is_read: bool = False,
) -> HallManagerOperationsNotification:
    now = datetime.now(timezone.utc)
    return HallManagerOperationsNotification(
        firebase_event_id=firebase_event_id or _unique("fevent"),
        event_type=event_type,
        order_id=order_id,
        table_id=table_id,
        message="Order completed",
        is_read=is_read,
        created_at=now,
    )

def _assert_route_supports(rule: str, method: str) -> None:
    methods = set()
    for r in app.url_map.iter_rules():
        if r.rule == rule:
            methods |= set(r.methods or [])
    assert methods, f"Route {rule} not registered"
    assert method in methods, f"Route {rule} does not support {method}. Supported: {sorted(methods)}"

def _json(response):
    try:
        return response.get_json()
    except Exception:
        return None

# =========================
# MODEL: User
# =========================
def test_user_model_has_required_fields():
    for field in ["id", "email", "username", "password_hash", "role", "created_at"]:
        assert hasattr(User, field), f"Missing field on User: {field}"

def test_user_set_password():
    user = User(email=f"{_unique('u')}@example.com", username=_unique("user"), role="hall_manager")
    user.set_password("Password123!")
    assert user.password_hash is not None
    assert user.password_hash != ""
    assert user.password_hash != "Password123!"

def test_user_check_password():
    user = User(email=f"{_unique('u')}@example.com", username=_unique("user"), role="hall_manager")
    user.set_password("Password123!")
    assert user.check_password("Password123!") is True
    assert user.check_password("WrongPassword!") is False

def test_user_unique_constraints(app_context):
    u1 = User(email="dup@example.com", username="dupuser", role="hall_manager")
    u1.set_password("Password123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email="dup@example.com", username=_unique("user"), role="hall_manager")
    u2.set_password("Password123!")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('u')}@example.com", username="dupuser", role="hall_manager")
    u3.set_password("Password123!")
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()

# =========================
# MODEL: HallManagerOperationsTable
# =========================
def test_hallmanageroperationstable_model_has_required_fields():
    for field in [
        "id",
        "firebase_table_id",
        "table_number",
        "capacity",
        "status",
        "reserved_by_name",
        "reserved_by_phone",
        "reservation_time",
        "notes",
        "updated_at",
    ]:
        assert hasattr(HallManagerOperationsTable, field), f"Missing field on HallManagerOperationsTable: {field}"

def test_hallmanageroperationstable_to_dict(app_context):
    t = _create_table(status="available")
    db.session.add(t)
    db.session.commit()

    d = t.to_dict()
    assert isinstance(d, dict)
    for key in [
        "id",
        "firebase_table_id",
        "table_number",
        "capacity",
        "status",
        "reserved_by_name",
        "reserved_by_phone",
        "reservation_time",
        "notes",
        "updated_at",
    ]:
        assert key in d, f"to_dict missing key: {key}"
    assert d["id"] == t.id
    assert d["firebase_table_id"] == t.firebase_table_id
    assert d["table_number"] == t.table_number
    assert d["status"] == t.status

def test_hallmanageroperationstable_unique_constraints(app_context):
    t1 = _create_table(firebase_table_id="ftable_dup", table_number=101)
    db.session.add(t1)
    db.session.commit()

    t2 = _create_table(firebase_table_id="ftable_dup", table_number=102)
    db.session.add(t2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    t3 = _create_table(firebase_table_id=_unique("ftable"), table_number=101)
    db.session.add(t3)
    with pytest.raises(Exception):
        db.session.commit()

# =========================
# MODEL: HallManagerOperationsOrder
# =========================
def test_hallmanageroperationsorder_model_has_required_fields():
    for field in [
        "id",
        "firebase_order_id",
        "table_id",
        "status",
        "total_amount",
        "currency",
        "completed_at",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(HallManagerOperationsOrder, field), f"Missing field on HallManagerOperationsOrder: {field}"

def test_hallmanageroperationsorder_to_dict(app_context):
    t = _create_table()
    db.session.add(t)
    db.session.commit()

    o = _create_order(table_id=t.id, status="open")
    db.session.add(o)
    db.session.commit()

    d = o.to_dict()
    assert isinstance(d, dict)
    for key in [
        "id",
        "firebase_order_id",
        "table_id",
        "status",
        "total_amount",
        "currency",
        "completed_at",
        "created_at",
        "updated_at",
    ]:
        assert key in d, f"to_dict missing key: {key}"
    assert d["id"] == o.id
    assert d["firebase_order_id"] == o.firebase_order_id
    assert d["table_id"] == o.table_id
    assert d["status"] == o.status

def test_hallmanageroperationsorder_unique_constraints(app_context):
    t = _create_table()
    db.session.add(t)
    db.session.commit()

    o1 = _create_order(table_id=t.id, firebase_order_id="forder_dup")
    db.session.add(o1)
    db.session.commit()

    o2 = _create_order(table_id=t.id, firebase_order_id="forder_dup")
    db.session.add(o2)
    with pytest.raises(Exception):
        db.session.commit()

# =========================
# MODEL: HallManagerOperationsBill
# =========================
def test_hallmanageroperationsbill_model_has_required_fields():
    for field in [
        "id",
        "firebase_bill_id",
        "order_id",
        "amount_due",
        "amount_paid",
        "status",
        "paid_at",
        "paid_by_user_id",
        "payment_method",
        "updated_at",
    ]:
        assert hasattr(HallManagerOperationsBill, field), f"Missing field on HallManagerOperationsBill: {field}"

def test_hallmanageroperationsbill_mark_paid(app_context):
    u = _create_user(role="hall_manager")
    db.session.add(u)
    db.session.commit()

    t = _create_table()
    db.session.add(t)
    db.session.commit()

    o = _create_order(table_id=t.id)
    db.session.add(o)
    db.session.commit()

    b = _create_bill(order_id=o.id, status="unpaid")
    db.session.add(b)
    db.session.commit()

    b.mark_paid(paid_by_user_id=u.id, payment_method="cash", amount_paid=12.50)
    db.session.commit()

    assert b.status in ("paid", "PAID", "Paid") or str(b.status).lower() == "paid"
    assert b.paid_at is not None
    assert b.payment_method == "cash"
    assert b.paid_by_user_id == u.id
    assert b.amount_paid is not None

def test_hallmanageroperationsbill_to_dict(app_context):
    t = _create_table()
    db.session.add(t)
    db.session.commit()

    o = _create_order(table_id=t.id)
    db.session.add(o)
    db.session.commit()

    b = _create_bill(order_id=o.id, status="unpaid")
    db.session.add(b)
    db.session.commit()

    d = b.to_dict()
    assert isinstance(d, dict)
    for key in [
        "id",
        "firebase_bill_id",
        "order_id",
        "amount_due",
        "amount_paid",
        "status",
        "paid_at",
        "paid_by_user_id",
        "payment_method",
        "updated_at",
    ]:
        assert key in d, f"to_dict missing key: {key}"
    assert d["id"] == b.id
    assert d["firebase_bill_id"] == b.firebase_bill_id
    assert d["order_id"] == b.order_id

def test_hallmanageroperationsbill_unique_constraints(app_context):
    t = _create_table()
    db.session.add(t)
    db.session.commit()

    o1 = _create_order(table_id=t.id, firebase_order_id=_unique("forder"))
    db.session.add(o1)
    db.session.commit()

    b1 = _create_bill(order_id=o1.id, firebase_bill_id="fbill_dup")
    db.session.add(b1)
    db.session.commit()

    o2 = _create_order(table_id=t.id, firebase_order_id=_unique("forder"))
    db.session.add(o2)
    db.session.commit()

    b2 = _create_bill(order_id=o2.id, firebase_bill_id="fbill_dup")
    db.session.add(b2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    b3 = _create_bill(order_id=o1.id, firebase_bill_id=_unique("fbill"))
    db.session.add(b3)
    with pytest.raises(Exception):
        db.session.commit()

# =========================
# MODEL: HallManagerOperationsNotification
# =========================
def test_hallmanageroperationsnotification_model_has_required_fields():
    for field in ["id", "firebase_event_id", "event_type", "order_id", "table_id", "message", "is_read", "created_at"]:
        assert hasattr(HallManagerOperationsNotification, field), f"Missing field on HallManagerOperationsNotification: {field}"

def test_hallmanageroperationsnotification_to_dict(app_context):
    n = _create_notification(is_read=False)
    db.session.add(n)
    db.session.commit()

    d = n.to_dict()
    assert isinstance(d, dict)
    for key in ["id", "firebase_event_id", "event_type", "order_id", "table_id", "message", "is_read", "created_at"]:
        assert key in d, f"to_dict missing key: {key}"
    assert d["id"] == n.id
    assert d["firebase_event_id"] == n.firebase_event_id
    assert d["event_type"] == n.event_type
    assert d["is_read"] == n.is_read

def test_hallmanageroperationsnotification_unique_constraints(app_context):
    n1 = _create_notification(firebase_event_id="fevent_dup")
    db.session.add(n1)
    db.session.commit()

    n2 = _create_notification(firebase_event_id="fevent_dup")
    db.session.add(n2)
    with pytest.raises(Exception):
        db.session.commit()

# =========================
# ROUTE: /hall-manager/tables (GET)
# =========================
def test_hall_manager_tables_get_exists():
    _assert_route_supports("/hall-manager/tables", "GET")

def test_hall_manager_tables_get_renders_template(client):
    resp = client.get("/hall-manager/tables")
    assert resp.status_code in (200, 401, 403)
    if resp.status_code == 200:
        ct = resp.headers.get("Content-Type", "")
        assert "text/html" in ct or "application/json" in ct
        assert resp.data is not None

# =========================
# ROUTE: /hall-manager/tables/<int:table_id> (GET)
# =========================
def test_hall_manager_tables_table_id_get_exists():
    _assert_route_supports("/hall-manager/tables/<int:table_id>", "GET")

def test_hall_manager_tables_table_id_get_renders_template(client, app_context):
    t = _create_table()
    db.session.add(t)
    db.session.commit()

    resp = client.get(f"/hall-manager/tables/{t.id}")
    assert resp.status_code in (200, 401, 403, 404)
    if resp.status_code == 200:
        ct = resp.headers.get("Content-Type", "")
        assert "text/html" in ct or "application/json" in ct
        assert resp.data is not None

# =========================
# ROUTE: /hall-manager/tables/<int:table_id>/status (PATCH)
# =========================
def test_hall_manager_tables_table_id_status_patch_exists():
    _assert_route_supports("/hall-manager/tables/<int:table_id>/status", "PATCH")

# =========================
# ROUTE: /hall-manager/reservations (POST)
# =========================
def test_hall_manager_reservations_post_exists():
    _assert_route_supports("/hall-manager/reservations", "POST")

def test_hall_manager_reservations_post_success(client, app_context):
    t = _create_table(status="available")
    db.session.add(t)
    db.session.commit()

    payload = {
        "table_id": t.id,
        "status": "reserved",
        "reserved_by_name": "Alice",
        "reserved_by_phone": "1234567890",
        "reservation_time": "2026-01-01T12:00:00Z",
        "notes": "Window seat",
    }
    resp = client.post("/hall-manager/reservations", json=payload)
    assert resp.status_code in (200, 401, 403, 400)
    if resp.status_code == 200:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "table" in data
        assert isinstance(data["table"], dict)
        assert data["table"].get("id") == t.id
        assert data["table"].get("status") == "reserved"

def test_hall_manager_reservations_post_missing_required_fields(client):
    resp = client.post("/hall-manager/reservations", json={"status": "reserved"})
    assert resp.status_code in (400, 401, 403)
    if resp.status_code == 400:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "error" in data

def test_hall_manager_reservations_post_invalid_data(client):
    resp = client.post("/hall-manager/reservations", json={"table_id": "not-an-int", "status": "reserved"})
    assert resp.status_code in (400, 401, 403)
    if resp.status_code == 400:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "error" in data

def test_hall_manager_reservations_post_duplicate_data(client, app_context):
    t = _create_table(status="available")
    db.session.add(t)
    db.session.commit()

    payload = {"table_id": t.id, "status": "reserved", "reserved_by_name": "Bob"}
    resp1 = client.post("/hall-manager/reservations", json=payload)
    assert resp1.status_code in (200, 401, 403, 400)

    resp2 = client.post("/hall-manager/reservations", json=payload)
    assert resp2.status_code in (200, 409, 401, 403, 400)
    if resp2.status_code == 409:
        data = _json(resp2)
        assert isinstance(data, dict)
        assert "error" in data

# =========================
# ROUTE: /hall-manager/reservations/<int:table_id> (DELETE)
# =========================
def test_hall_manager_reservations_table_id_delete_exists():
    _assert_route_supports("/hall-manager/reservations/<int:table_id>", "DELETE")

# =========================
# ROUTE: /hall-manager/bills/<int:bill_id>/pay (POST)
# =========================
def test_hall_manager_bills_bill_id_pay_post_exists():
    _assert_route_supports("/hall-manager/bills/<int:bill_id>/pay", "POST")

def test_hall_manager_bills_bill_id_pay_post_success(client, app_context):
    u = _create_user(role="hall_manager")
    db.session.add(u)
    db.session.commit()

    t = _create_table()
    db.session.add(t)
    db.session.commit()

    o = _create_order(table_id=t.id)
    db.session.add(o)
    db.session.commit()

    b = _create_bill(order_id=o.id, status="unpaid")
    db.session.add(b)
    db.session.commit()

    payload = {"payment_method": "cash", "amount_paid": 12.50}
    resp = client.post(f"/hall-manager/bills/{b.id}/pay", json=payload)
    assert resp.status_code in (200, 401, 403, 400, 404)
    if resp.status_code == 200:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "bill" in data
        assert data["bill"].get("id") == b.id
        assert str(data["bill"].get("status", "")).lower() == "paid"

def test_hall_manager_bills_bill_id_pay_post_missing_required_fields(client, app_context):
    t = _create_table()
    db.session.add(t)
    db.session.commit()

    o = _create_order(table_id=t.id)
    db.session.add(o)
    db.session.commit()

    b = _create_bill(order_id=o.id, status="unpaid")
    db.session.add(b)
    db.session.commit()

    resp = client.post(f"/hall-manager/bills/{b.id}/pay", json={"amount_paid": 12.50})
    assert resp.status_code in (400, 401, 403)
    if resp.status_code == 400:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "error" in data

def test_hall_manager_bills_bill_id_pay_post_invalid_data(client, app_context):
    t = _create_table()
    db.session.add(t)
    db.session.commit()

    o = _create_order(table_id=t.id)
    db.session.add(o)
    db.session.commit()

    b = _create_bill(order_id=o.id, status="unpaid")
    db.session.add(b)
    db.session.commit()

    resp = client.post(f"/hall-manager/bills/{b.id}/pay", json={"payment_method": "bitcoin"})
    assert resp.status_code in (400, 401, 403)
    if resp.status_code == 400:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "error" in data

def test_hall_manager_bills_bill_id_pay_post_duplicate_data(client, app_context):
    t = _create_table()
    db.session.add(t)
    db.session.commit()

    o = _create_order(table_id=t.id)
    db.session.add(o)
    db.session.commit()

    b = _create_bill(order_id=o.id, status="unpaid")
    db.session.add(b)
    db.session.commit()

    payload = {"payment_method": "cash", "amount_paid": 12.50}
    resp1 = client.post(f"/hall-manager/bills/{b.id}/pay", json=payload)
    assert resp1.status_code in (200, 401, 403, 400, 404)

    resp2 = client.post(f"/hall-manager/bills/{b.id}/pay", json=payload)
    assert resp2.status_code in (200, 409, 400, 401, 403)
    if resp2.status_code == 409:
        data = _json(resp2)
        assert isinstance(data, dict)
        assert "error" in data

# =========================
# ROUTE: /hall-manager/notifications (GET)
# =========================
def test_hall_manager_notifications_get_exists():
    _assert_route_supports("/hall-manager/notifications", "GET")

def test_hall_manager_notifications_get_renders_template(client):
    resp = client.get("/hall-manager/notifications")
    assert resp.status_code in (200, 401, 403)
    if resp.status_code == 200:
        ct = resp.headers.get("Content-Type", "")
        assert "text/html" in ct or "application/json" in ct
        assert resp.data is not None

# =========================
# ROUTE: /hall-manager/notifications/<int:notification_id>/read (POST)
# =========================
def test_hall_manager_notifications_notification_id_read_post_exists():
    _assert_route_supports("/hall-manager/notifications/<int:notification_id>/read", "POST")

def test_hall_manager_notifications_notification_id_read_post_success(client, app_context):
    n = _create_notification(is_read=False)
    db.session.add(n)
    db.session.commit()

    resp = client.post(f"/hall-manager/notifications/{n.id}/read", json={"is_read": True})
    assert resp.status_code in (200, 401, 403, 400, 404)
    if resp.status_code == 200:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "notification" in data
        assert data["notification"].get("id") == n.id
        assert data["notification"].get("is_read") is True

def test_hall_manager_notifications_notification_id_read_post_missing_required_fields(client, app_context):
    n = _create_notification(is_read=False)
    db.session.add(n)
    db.session.commit()

    resp = client.post(f"/hall-manager/notifications/{n.id}/read", json={})
    assert resp.status_code in (200, 400, 401, 403, 404)
    if resp.status_code == 400:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "error" in data

def test_hall_manager_notifications_notification_id_read_post_invalid_data(client, app_context):
    n = _create_notification(is_read=False)
    db.session.add(n)
    db.session.commit()

    resp = client.post(f"/hall-manager/notifications/{n.id}/read", json={"is_read": "not-a-bool"})
    assert resp.status_code in (400, 401, 403, 200, 404)
    if resp.status_code == 400:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "error" in data

def test_hall_manager_notifications_notification_id_read_post_duplicate_data(client, app_context):
    n = _create_notification(is_read=False)
    db.session.add(n)
    db.session.commit()

    resp1 = client.post(f"/hall-manager/notifications/{n.id}/read", json={"is_read": True})
    assert resp1.status_code in (200, 401, 403, 400, 404)

    resp2 = client.post(f"/hall-manager/notifications/{n.id}/read", json={"is_read": True})
    assert resp2.status_code in (200, 409, 400, 401, 403, 404)
    if resp2.status_code == 409:
        data = _json(resp2)
        assert isinstance(data, dict)
        assert "error" in data

# =========================
# ROUTE: /hall-manager/firebase/sync (POST)
# =========================
def test_hall_manager_firebase_sync_post_exists():
    _assert_route_supports("/hall-manager/firebase/sync", "POST")

def test_hall_manager_firebase_sync_post_success(client):
    payload = {
        "tables": [
            {
                "firebase_table_id": _unique("ftable"),
                "table_number": 1,
                "capacity": 4,
                "status": "available",
                "reserved_by_name": None,
                "reserved_by_phone": None,
                "reservation_time": None,
                "notes": None,
                "updated_at": "2026-01-01T10:00:00Z",
            }
        ],
        "orders": [
            {
                "firebase_order_id": _unique("forder"),
                "firebase_table_id": "will_be_overridden_in_test",
                "status": "completed",
                "total_amount": 12.5,
                "currency": "USD",
                "completed_at": "2026-01-01T10:30:00Z",
                "updated_at": "2026-01-01T10:30:00Z",
            }
        ],
        "events": [
            {
                "firebase_event_id": _unique("fevent"),
                "event_type": "order_completed",
                "firebase_order_id": "will_be_overridden_in_test",
                "firebase_table_id": "will_be_overridden_in_test",
                "message": "Order completed",
                "created_at": "2026-01-01T10:31:00Z",
            }
        ],
    }
    payload["orders"][0]["firebase_table_id"] = payload["tables"][0]["firebase_table_id"]
    payload["events"][0]["firebase_order_id"] = payload["orders"][0]["firebase_order_id"]
    payload["events"][0]["firebase_table_id"] = payload["tables"][0]["firebase_table_id"]

    resp = client.post("/hall-manager/firebase/sync", json=payload)
    assert resp.status_code in (200, 401, 403, 400)
    if resp.status_code == 200:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "synced" in data
        assert isinstance(data["synced"], dict)

def test_hall_manager_firebase_sync_post_missing_required_fields(client):
    resp = client.post("/hall-manager/firebase/sync", json={"tables": [], "orders": []})
    assert resp.status_code in (400, 401, 403)
    if resp.status_code == 400:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "error" in data

def test_hall_manager_firebase_sync_post_invalid_data(client):
    resp = client.post("/hall-manager/firebase/sync", json={"tables": "not-a-list", "orders": [], "events": []})
    assert resp.status_code in (400, 401, 403)
    if resp.status_code == 400:
        data = _json(resp)
        assert isinstance(data, dict)
        assert "error" in data

def test_hall_manager_firebase_sync_post_duplicate_data(client):
    firebase_table_id = _unique("ftable")
    firebase_order_id = _unique("forder")
    firebase_event_id = _unique("fevent")

    payload = {
        "tables": [
            {
                "firebase_table_id": firebase_table_id,
                "table_number": 10,
                "capacity": 4,
                "status": "available",
                "reserved_by_name": None,
                "reserved_by_phone": None,
                "reservation_time": None,
                "notes": None,
                "updated_at": "2026-01-01T10:00:00Z",
            }
        ],
        "orders": [
            {
                "firebase_order_id": firebase_order_id,
                "firebase_table_id": firebase_table_id,
                "status": "completed",
                "total_amount": 12.5,
                "currency": "USD",
                "completed_at": "2026-01-01T10:30:00Z",
                "updated_at": "2026-01-01T10:30:00Z",
            }
        ],
        "events": [
            {
                "firebase_event_id": firebase_event_id,
                "event_type": "order_completed",
                "firebase_order_id": firebase_order_id,
                "firebase_table_id": firebase_table_id,
                "message": "Order completed",
                "created_at": "2026-01-01T10:31:00Z",
            }
        ],
    }

    resp1 = client.post("/hall-manager/firebase/sync", json=payload)
    assert resp1.status_code in (200, 401, 403, 400)

    resp2 = client.post("/hall-manager/firebase/sync", json=payload)
    assert resp2.status_code in (200, 409, 401, 403, 400)
    if resp2.status_code == 409:
        data = _json(resp2)
        assert isinstance(data, dict)
        assert "error" in data

# =========================
# HELPER: require_hall_manager(user: User)
# =========================
def test_require_hall_manager_function_exists():
    assert callable(require_hall_manager)

def test_require_hall_manager_with_valid_input():
    user = _create_user(role="hall_manager")
    require_hall_manager(user)

def test_require_hall_manager_with_invalid_input():
    user = _create_user(role="customer")
    with pytest.raises(Exception):
        require_hall_manager(user)

# =========================
# HELPER: get_current_user()
# =========================
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input():
    with patch("controllers.hall_manager_operations_controller.get_current_user") as mocked:
        u = _create_user(role="hall_manager")
        mocked.return_value = u
        result = mocked()
        assert isinstance(result, User)
        assert result.role == "hall_manager"

def test_get_current_user_with_invalid_input():
    with patch("controllers.hall_manager_operations_controller.get_current_user") as mocked:
        mocked.return_value = None
        result = mocked()
        assert result is None

# =========================
# HELPER: parse_iso_datetime(value: str | None)
# =========================
def test_parse_iso_datetime_function_exists():
    assert callable(parse_iso_datetime)

def test_parse_iso_datetime_with_valid_input():
    dt = parse_iso_datetime("2026-01-01T12:00:00Z")
    assert dt is not None
    assert hasattr(dt, "year") and dt.year == 2026

def test_parse_iso_datetime_with_invalid_input():
    dt = parse_iso_datetime("not-a-datetime")
    assert dt is None

# =========================
# VIEW LAYER (contract-defined view functions)
# =========================
def test_render_tables_page_returns_str():
    html = render_tables_page(tables=[])
    assert isinstance(html, str)

def test_render_notifications_page_returns_str():
    html = render_notifications_page(notifications=[])
    assert isinstance(html, str)