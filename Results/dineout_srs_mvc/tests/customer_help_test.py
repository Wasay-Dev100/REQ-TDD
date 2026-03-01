import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
from werkzeug.exceptions import NotFound

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.customer_help_request import CustomerHelpRequest
from models.order import Order
from controllers.customer_help_controller import (
    validate_request_type,
    get_order_or_404,
    get_help_request_or_404,
)
from views.customer_help_views import render_help_home

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

def _unique_table_number():
    return int(uuid.uuid4().int % 10000) + 1

def _create_help_request_in_db(
    *,
    table_number=None,
    request_type="call_manager",
    message="Need help",
    status="open",
    created_at=None,
    resolved_at=None,
):
    if table_number is None:
        table_number = _unique_table_number()
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    req = CustomerHelpRequest(
        table_number=table_number,
        request_type=request_type,
        message=message,
        status=status,
        created_at=created_at,
        resolved_at=resolved_at,
    )
    db.session.add(req)
    db.session.commit()
    return req

def _create_order_in_db(
    *,
    table_number=None,
    status="pending",
    given_by_waiter=False,
    created_at=None,
    updated_at=None,
):
    if table_number is None:
        table_number = _unique_table_number()
    now = datetime.now(timezone.utc)
    if created_at is None:
        created_at = now
    if updated_at is None:
        updated_at = now
    order = Order(
        table_number=table_number,
        status=status,
        given_by_waiter=given_by_waiter,
        created_at=created_at,
        updated_at=updated_at,
    )
    db.session.add(order)
    db.session.commit()
    return order

# MODEL: CustomerHelpRequest (models/customer_help_request.py)
def test_customerhelprequest_model_has_required_fields(app_context):
    required_fields = [
        "id",
        "table_number",
        "request_type",
        "message",
        "status",
        "created_at",
        "resolved_at",
    ]
    for field in required_fields:
        assert hasattr(CustomerHelpRequest, field), f"Missing field on CustomerHelpRequest: {field}"

def test_customerhelprequest_mark_resolved(app_context):
    req = _create_help_request_in_db(status="open", resolved_at=None)
    resolved_at = datetime.now(timezone.utc)

    assert hasattr(req, "mark_resolved"), "CustomerHelpRequest.mark_resolved is missing"
    req.mark_resolved(resolved_at)
    db.session.commit()

    refreshed = CustomerHelpRequest.query.filter_by(id=req.id).first()
    assert refreshed is not None
    assert refreshed.resolved_at == resolved_at

def test_customerhelprequest_unique_constraints(app_context):
    tnum = _unique_table_number()
    created_at = datetime.now(timezone.utc)

    r1 = CustomerHelpRequest(
        table_number=tnum,
        request_type="call_manager",
        message="First",
        status="open",
        created_at=created_at,
        resolved_at=None,
    )
    r2 = CustomerHelpRequest(
        table_number=tnum,
        request_type="call_manager",
        message="Second",
        status="open",
        created_at=created_at,
        resolved_at=None,
    )
    db.session.add_all([r1, r2])
    db.session.commit()

    assert r1.id is not None
    assert r2.id is not None
    assert r1.id != r2.id

# MODEL: Order (models/order.py)
def test_order_model_has_required_fields(app_context):
    required_fields = [
        "id",
        "table_number",
        "status",
        "given_by_waiter",
        "created_at",
        "updated_at",
    ]
    for field in required_fields:
        assert hasattr(Order, field), f"Missing field on Order: {field}"

def test_order_set_given_by_waiter(app_context):
    order = _create_order_in_db(given_by_waiter=False)

    assert hasattr(order, "set_given_by_waiter"), "Order.set_given_by_waiter is missing"
    order.set_given_by_waiter(True)
    db.session.commit()

    refreshed = Order.query.filter_by(id=order.id).first()
    assert refreshed is not None
    assert refreshed.given_by_waiter is True

def test_order_unique_constraints(app_context):
    tnum = _unique_table_number()
    now = datetime.now(timezone.utc)

    o1 = Order(
        table_number=tnum,
        status="pending",
        given_by_waiter=False,
        created_at=now,
        updated_at=now,
    )
    o2 = Order(
        table_number=tnum,
        status="pending",
        given_by_waiter=False,
        created_at=now,
        updated_at=now,
    )
    db.session.add_all([o1, o2])
    db.session.commit()

    assert o1.id is not None
    assert o2.id is not None
    assert o1.id != o2.id

# ROUTE: /help (GET) - help_home
def test_help_get_exists(client):
    resp = client.get("/help")
    assert resp.status_code != 404

def test_help_get_renders_template(client):
    resp = client.get("/help")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/xhtml+xml")

# ROUTE: /help/request (POST) - create_help_request
def test_help_request_post_exists(client):
    resp = client.post("/help/request", data={})
    assert resp.status_code != 404

def test_help_request_post_success(client):
    table_number = _unique_table_number()
    resp = client.post(
        "/help/request",
        data={
            "table_number": str(table_number),
            "request_type": "call_manager",
            "message": "Need assistance",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 201, 302)

    with app.app_context():
        created = CustomerHelpRequest.query.filter_by(table_number=table_number).first()
        assert created is not None
        assert created.request_type == "call_manager"
        assert created.message == "Need assistance"

def test_help_request_post_missing_required_fields(client):
    table_number = _unique_table_number()
    resp = client.post(
        "/help/request",
        data={
            "table_number": str(table_number),
            "message": "Missing request_type",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)

    with app.app_context():
        created = CustomerHelpRequest.query.filter_by(table_number=table_number).first()
        assert created is None

def test_help_request_post_invalid_data(client):
    unique_marker = uuid.uuid4().hex[:8]
    resp = client.post(
        "/help/request",
        data={
            "table_number": f"not-an-int-{unique_marker}",
            "request_type": "call_manager",
            "message": "Bad table number",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)

def test_help_request_post_duplicate_data(client):
    table_number = _unique_table_number()
    resp1 = client.post(
        "/help/request",
        data={
            "table_number": str(table_number),
            "request_type": "call_manager",
            "message": "First",
        },
        follow_redirects=False,
    )
    assert resp1.status_code in (200, 201, 302)

    resp2 = client.post(
        "/help/request",
        data={
            "table_number": str(table_number),
            "request_type": "call_manager",
            "message": "Second",
        },
        follow_redirects=False,
    )
    assert resp2.status_code in (200, 201, 302)

    with app.app_context():
        count = CustomerHelpRequest.query.filter_by(table_number=table_number, request_type="call_manager").count()
        assert count >= 2

# ROUTE: /help/requests/<int:request_id> (GET) - get_help_request
def test_help_requests_request_id_get_exists(client):
    with app.app_context():
        req = _create_help_request_in_db()
        rid = req.id

    resp = client.get(f"/help/requests/{rid}")
    assert resp.status_code != 404

def test_help_requests_request_id_get_renders_template(client):
    with app.app_context():
        req = _create_help_request_in_db()
        rid = req.id

    resp = client.get(f"/help/requests/{rid}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/xhtml+xml")

# ROUTE: /help/requests/<int:request_id>/resolve (POST) - resolve_help_request
def test_help_requests_request_id_resolve_post_exists(client):
    with app.app_context():
        req = _create_help_request_in_db(status="open", resolved_at=None)
        rid = req.id

    resp = client.post(f"/help/requests/{rid}/resolve", data={})
    assert resp.status_code != 404

def test_help_requests_request_id_resolve_post_success(client):
    with app.app_context():
        req = _create_help_request_in_db(status="open", resolved_at=None)
        rid = req.id

    resp = client.post(f"/help/requests/{rid}/resolve", data={}, follow_redirects=False)
    assert resp.status_code in (200, 302)

    with app.app_context():
        refreshed = CustomerHelpRequest.query.filter_by(id=rid).first()
        assert refreshed is not None
        assert refreshed.resolved_at is not None

def test_help_requests_request_id_resolve_post_missing_required_fields(client):
    resp = client.post("/help/requests/999999999/resolve", data={}, follow_redirects=False)
    assert resp.status_code in (404, 400)

def test_help_requests_request_id_resolve_post_invalid_data(client):
    resp = client.post("/help/requests/not-an-int/resolve", data={}, follow_redirects=False)
    assert resp.status_code in (404, 405)

def test_help_requests_request_id_resolve_post_duplicate_data(client):
    with app.app_context():
        req = _create_help_request_in_db(status="open", resolved_at=None)
        rid = req.id

    resp1 = client.post(f"/help/requests/{rid}/resolve", data={}, follow_redirects=False)
    assert resp1.status_code in (200, 302)

    resp2 = client.post(f"/help/requests/{rid}/resolve", data={}, follow_redirects=False)
    assert resp2.status_code in (200, 302, 400)

    with app.app_context():
        refreshed = CustomerHelpRequest.query.filter_by(id=rid).first()
        assert refreshed is not None
        assert refreshed.resolved_at is not None

# ROUTE: /help/call-waiter/manage-order (POST) - call_waiter_manage_order
def test_help_call_waiter_manage_order_post_exists(client):
    resp = client.post("/help/call-waiter/manage-order", data={})
    assert resp.status_code != 404

def test_help_call_waiter_manage_order_post_success(client):
    with app.app_context():
        order = _create_order_in_db(given_by_waiter=False)
        oid = order.id

    resp = client.post(
        "/help/call-waiter/manage-order",
        data={"order_id": str(oid)},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)

    with app.app_context():
        refreshed = Order.query.filter_by(id=oid).first()
        assert refreshed is not None
        assert refreshed.given_by_waiter is True

def test_help_call_waiter_manage_order_post_missing_required_fields(client):
    resp = client.post("/help/call-waiter/manage-order", data={}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)

def test_help_call_waiter_manage_order_post_invalid_data(client):
    unique_marker = uuid.uuid4().hex[:8]
    resp = client.post(
        "/help/call-waiter/manage-order",
        data={"order_id": f"bad-{unique_marker}"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)

def test_help_call_waiter_manage_order_post_duplicate_data(client):
    with app.app_context():
        order = _create_order_in_db(given_by_waiter=False)
        oid = order.id

    resp1 = client.post(
        "/help/call-waiter/manage-order",
        data={"order_id": str(oid)},
        follow_redirects=False,
    )
    assert resp1.status_code in (200, 302)

    resp2 = client.post(
        "/help/call-waiter/manage-order",
        data={"order_id": str(oid)},
        follow_redirects=False,
    )
    assert resp2.status_code in (200, 302, 400)

    with app.app_context():
        refreshed = Order.query.filter_by(id=oid).first()
        assert refreshed is not None
        assert refreshed.given_by_waiter is True

# HELPER: validate_request_type(request_type)
def test_validate_request_type_function_exists():
    assert callable(validate_request_type)

def test_validate_request_type_with_valid_input():
    assert validate_request_type("call_manager") is True
    assert validate_request_type("call_waiter_manage_order") is True

def test_validate_request_type_with_invalid_input():
    assert validate_request_type("") is False
    assert validate_request_type("invalid_type") is False
    assert validate_request_type(None) is False

# HELPER: get_order_or_404(order_id)
def test_get_order_or_404_function_exists():
    assert callable(get_order_or_404)

def test_get_order_or_404_with_valid_input(app_context):
    order = _create_order_in_db()
    found = get_order_or_404(order.id)
    assert found is not None
    assert isinstance(found, Order)
    assert found.id == order.id

def test_get_order_or_404_with_invalid_input(app_context):
    with pytest.raises(NotFound):
        get_order_or_404(999999999)

# HELPER: get_help_request_or_404(request_id)
def test_get_help_request_or_404_function_exists():
    assert callable(get_help_request_or_404)

def test_get_help_request_or_404_with_valid_input(app_context):
    req = _create_help_request_in_db()
    found = get_help_request_or_404(req.id)
    assert found is not None
    assert isinstance(found, CustomerHelpRequest)
    assert found.id == req.id

def test_get_help_request_or_404_with_invalid_input(app_context):
    with pytest.raises(NotFound):
        get_help_request_or_404(999999999)