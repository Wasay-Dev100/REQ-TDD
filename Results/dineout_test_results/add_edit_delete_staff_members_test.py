import os
import sys
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.staff_management_staff_member import StaffMember
from controllers.add_edit_delete_staff_members_controller import (
    validate_staff_payload,
    get_staff_or_404,
    wants_json_response,
    require_admin,
)
from views.add_edit_delete_staff_members_views import render_staff_list, render_staff_form

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
    return f"staff_{uuid.uuid4().hex[:10]}@example.com"

def _unique_phone():
    return f"+1555{uuid.uuid4().int % 10_000_000:07d}"

def _valid_staff_payload(**overrides):
    payload = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": _unique_email(),
        "phone": _unique_phone(),
        "role_title": "Nurse",
        "department": "ER",
        "is_active": True,
    }
    payload.update(overrides)
    return payload

def _create_staff_in_db(**overrides):
    payload = _valid_staff_payload(**overrides)
    staff = StaffMember(
        first_name=payload["first_name"],
        last_name=payload["last_name"],
        email=payload["email"],
        phone=payload.get("phone"),
        role_title=payload["role_title"],
        department=payload.get("department"),
        is_active=payload.get("is_active", True),
    )
    db.session.add(staff)
    db.session.commit()
    return staff

# MODEL: StaffMember (models/staff_management_staff_member.py)
def test_staffmember_model_has_required_fields(app_context):
    required_fields = [
        "id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "role_title",
        "department",
        "is_active",
        "created_at",
        "updated_at",
    ]
    for field in required_fields:
        assert hasattr(StaffMember, field), f"Missing StaffMember field: {field}"

def test_staffmember_to_dict(app_context):
    staff = StaffMember(
        first_name="A",
        last_name="B",
        email=_unique_email(),
        phone=_unique_phone(),
        role_title="Role",
        department="Dept",
        is_active=True,
    )
    db.session.add(staff)
    db.session.commit()

    assert hasattr(staff, "to_dict") and callable(staff.to_dict)
    data = staff.to_dict()
    assert isinstance(data, dict)

    for key in [
        "id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "role_title",
        "department",
        "is_active",
        "created_at",
        "updated_at",
    ]:
        assert key in data, f"to_dict() missing key: {key}"

    assert data["id"] == staff.id
    assert data["first_name"] == "A"
    assert data["last_name"] == "B"
    assert data["email"] == staff.email
    assert data["phone"] == staff.phone
    assert data["role_title"] == "Role"
    assert data["department"] == "Dept"
    assert data["is_active"] is True

def test_staffmember_update_from_dict(app_context):
    staff = StaffMember(
        first_name="Old",
        last_name="Name",
        email=_unique_email(),
        phone=_unique_phone(),
        role_title="OldRole",
        department="OldDept",
        is_active=True,
    )
    db.session.add(staff)
    db.session.commit()

    assert hasattr(staff, "update_from_dict") and callable(staff.update_from_dict)

    before_updated_at = getattr(staff, "updated_at", None)
    staff.update_from_dict(
        {
            "first_name": "New",
            "last_name": "Person",
            "role_title": "NewRole",
            "department": "NewDept",
            "is_active": False,
        }
    )
    db.session.commit()

    assert staff.first_name == "New"
    assert staff.last_name == "Person"
    assert staff.role_title == "NewRole"
    assert staff.department == "NewDept"
    assert staff.is_active is False

    after_updated_at = getattr(staff, "updated_at", None)
    if before_updated_at is not None and after_updated_at is not None:
        assert isinstance(after_updated_at, datetime)
        assert after_updated_at >= before_updated_at

def test_staffmember_unique_constraints(app_context):
    email = _unique_email()
    phone = _unique_phone()

    staff1 = StaffMember(
        first_name="A",
        last_name="B",
        email=email,
        phone=phone,
        role_title="Role",
        department=None,
        is_active=True,
    )
    db.session.add(staff1)
    db.session.commit()

    staff_dup_email = StaffMember(
        first_name="C",
        last_name="D",
        email=email,
        phone=_unique_phone(),
        role_title="Role2",
        department=None,
        is_active=True,
    )
    db.session.add(staff_dup_email)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    staff_dup_phone = StaffMember(
        first_name="E",
        last_name="F",
        email=_unique_email(),
        phone=phone,
        role_title="Role3",
        department=None,
        is_active=True,
    )
    db.session.add(staff_dup_phone)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# ROUTE: /admin/staff (GET) - list_staff
def test_admin_staff_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/admin/staff"]
    assert rules, "Route /admin/staff is missing"
    assert any("GET" in r.methods for r in rules), "Route /admin/staff does not accept GET"

    resp = client.get("/admin/staff")
    assert resp.status_code != 404

def test_admin_staff_get_renders_template(client):
    resp = client.get("/admin/staff")
    assert resp.status_code in (200, 302, 401, 403)
    if resp.status_code == 200:
        assert resp.mimetype in ("text/html", "application/json")

# ROUTE: /admin/staff/new (GET) - new_staff_form
def test_admin_staff_new_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/admin/staff/new"]
    assert rules, "Route /admin/staff/new is missing"
    assert any("GET" in r.methods for r in rules), "Route /admin/staff/new does not accept GET"

    resp = client.get("/admin/staff/new")
    assert resp.status_code != 404

def test_admin_staff_new_get_renders_template(client):
    resp = client.get("/admin/staff/new")
    assert resp.status_code in (200, 302, 401, 403)
    if resp.status_code == 200:
        assert resp.mimetype in ("text/html", "application/json")

# ROUTE: /admin/staff (POST) - create_staff
def test_admin_staff_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/admin/staff"]
    assert rules, "Route /admin/staff is missing"
    assert any("POST" in r.methods for r in rules), "Route /admin/staff does not accept POST"

    resp = client.post("/admin/staff", data=_valid_staff_payload())
    assert resp.status_code != 404

def test_admin_staff_post_success(client):
    payload = _valid_staff_payload()
    resp = client.post("/admin/staff", data=payload, follow_redirects=False)
    assert resp.status_code in (200, 201, 302)

    with app.app_context():
        created = StaffMember.query.filter_by(email=payload["email"]).first()
        assert created is not None
        assert created.first_name == payload["first_name"]
        assert created.last_name == payload["last_name"]
        assert created.role_title == payload["role_title"]
        assert created.phone == payload["phone"]
        assert created.department == payload["department"]
        assert created.is_active is True

def test_admin_staff_post_missing_required_fields(client):
    payload = _valid_staff_payload()
    payload.pop("first_name", None)
    payload.pop("email", None)

    resp = client.post("/admin/staff", data=payload, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)

    with app.app_context():
        created = StaffMember.query.filter_by(phone=payload.get("phone")).first()
        assert created is None

def test_admin_staff_post_invalid_data(client):
    payload = _valid_staff_payload(email="not-an-email", phone="not-a-phone")
    resp = client.post("/admin/staff", data=payload, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)

    with app.app_context():
        created = StaffMember.query.filter_by(email=payload["email"]).first()
        assert created is None

def test_admin_staff_post_duplicate_data(client):
    payload = _valid_staff_payload()
    resp1 = client.post("/admin/staff", data=payload, follow_redirects=False)
    assert resp1.status_code in (200, 201, 302)

    resp2 = client.post("/admin/staff", data=payload, follow_redirects=False)
    assert resp2.status_code in (200, 400, 409, 422)

    with app.app_context():
        count = StaffMember.query.filter_by(email=payload["email"]).count()
        assert count == 1

# ROUTE: /admin/staff/<int:staff_id>/edit (GET) - edit_staff_form
def test_admin_staff_staff_id_edit_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/admin/staff/<int:staff_id>/edit"]
    assert rules, "Route /admin/staff/<int:staff_id>/edit is missing"
    assert any("GET" in r.methods for r in rules), "Route /admin/staff/<int:staff_id>/edit does not accept GET"

    resp = client.get("/admin/staff/1/edit")
    assert resp.status_code != 404

def test_admin_staff_staff_id_edit_get_renders_template(client):
    with app.app_context():
        staff = _create_staff_in_db()

    resp = client.get(f"/admin/staff/{staff.id}/edit")
    assert resp.status_code in (200, 302, 401, 403)
    if resp.status_code == 200:
        assert resp.mimetype in ("text/html", "application/json")

# ROUTE: /admin/staff/<int:staff_id> (PUT) - update_staff
def test_admin_staff_staff_id_put_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/admin/staff/<int:staff_id>"]
    assert rules, "Route /admin/staff/<int:staff_id> is missing"
    assert any("PUT" in r.methods for r in rules), "Route /admin/staff/<int:staff_id> does not accept PUT"

    resp = client.put("/admin/staff/1", json={"first_name": "X"})
    assert resp.status_code != 404

# ROUTE: /admin/staff/<int:staff_id> (DELETE) - delete_staff
def test_admin_staff_staff_id_delete_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/admin/staff/<int:staff_id>"]
    assert rules, "Route /admin/staff/<int:staff_id> is missing"
    assert any("DELETE" in r.methods for r in rules), "Route /admin/staff/<int:staff_id> does not accept DELETE"

    resp = client.delete("/admin/staff/1")
    assert resp.status_code != 404

# HELPER: validate_staff_payload(payload, partial:bool)
def test_validate_staff_payload_function_exists():
    assert callable(validate_staff_payload)

def test_validate_staff_payload_with_valid_input(app_context):
    payload = _valid_staff_payload()
    ok, errors = validate_staff_payload(payload, partial=False)
    assert ok is True
    assert isinstance(errors, dict)
    assert errors == {} or all(isinstance(k, str) for k in errors.keys())

def test_validate_staff_payload_with_invalid_input(app_context):
    payload = {
        "first_name": "",
        "last_name": "",
        "email": "bad",
        "role_title": "",
        "phone": "x",
    }
    ok, errors = validate_staff_payload(payload, partial=False)
    assert ok is False
    assert isinstance(errors, dict)
    assert errors, "Expected validation errors for invalid payload"

# HELPER: get_staff_or_404(staff_id)
def test_get_staff_or_404_function_exists():
    assert callable(get_staff_or_404)

def test_get_staff_or_404_with_valid_input(app_context):
    staff = _create_staff_in_db()
    found = get_staff_or_404(staff.id)
    assert isinstance(found, StaffMember)
    assert found.id == staff.id

def test_get_staff_or_404_with_invalid_input(app_context):
    with pytest.raises(Exception):
        get_staff_or_404(999999)

# HELPER: wants_json_response(N/A)
def test_wants_json_response_function_exists():
    assert callable(wants_json_response)

def test_wants_json_response_with_valid_input(client):
    with app.test_request_context("/admin/staff", headers={"Accept": "application/json"}):
        result = wants_json_response()
        assert isinstance(result, bool)

def test_wants_json_response_with_invalid_input(client):
    with app.test_request_context("/admin/staff", headers={"Accept": ""}):
        result = wants_json_response()
        assert isinstance(result, bool)

# HELPER: require_admin(N/A)
def test_require_admin_function_exists():
    assert callable(require_admin)

def test_require_admin_with_valid_input(client):
    with app.test_request_context("/admin/staff"):
        with patch(
            "controllers.add_edit_delete_staff_members_controller.current_user",
            MagicMock(is_authenticated=True, is_admin=True),
            create=True,
        ):
            result = require_admin()
            assert result is None

def test_require_admin_with_invalid_input(client):
    with app.test_request_context("/admin/staff"):
        with patch(
            "controllers.add_edit_delete_staff_members_controller.current_user",
            MagicMock(is_authenticated=False, is_admin=False),
            create=True,
        ):
            result = require_admin()
            assert result is not None

# VIEW LAYER (contract-defined view functions exist; minimal existence checks only)
def test_render_staff_list_function_exists():
    assert callable(render_staff_list)

def test_render_staff_form_function_exists():
    assert callable(render_staff_form)