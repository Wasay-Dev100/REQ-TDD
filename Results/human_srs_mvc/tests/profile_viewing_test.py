import sys
import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.profile_viewing_event import ProfileViewingEvent
from models.profile_viewing_event_registration import ProfileViewingEventRegistration
from controllers.profile_viewing_controller import (
    login_required,
    get_current_user,
    can_view_profile,
    build_profile_payload,
)
from views.profile_viewing_views import render_profile_page

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

def _create_user(
    *,
    email=None,
    username=None,
    password="TestPass!123",
    full_name="Test User",
    student_id=None,
    role="STUDENT",
    profile_badge="STUDENT",
    club_name=None,
    department=None,
    phone=None,
):
    if email is None:
        email = f"{_unique('user')}@example.com"
    if username is None:
        username = _unique("user")
    user = User(
        email=email,
        username=username,
        password_hash="",
        full_name=full_name,
        student_id=student_id,
        role=role,
        profile_badge=profile_badge,
        club_name=club_name,
        department=department,
        phone=phone,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

def _login_as(client, user_id: int):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

def _create_event(*, created_by_user_id: int, status="PUBLISHED"):
    now = datetime.utcnow()
    event = ProfileViewingEvent(
        title=_unique("Event"),
        description="Desc",
        location="Loc",
        start_at=now + timedelta(days=1),
        end_at=now + timedelta(days=1, hours=2),
        status=status,
        capacity=100,
        created_by_user_id=created_by_user_id,
    )
    db.session.add(event)
    db.session.commit()
    return event

def _create_registration(*, user_id: int, event_id: int, status="REGISTERED"):
    reg = ProfileViewingEventRegistration(
        user_id=user_id,
        event_id=event_id,
        registered_at=datetime.utcnow(),
        status=status,
    )
    db.session.add(reg)
    db.session.commit()
    return reg

# MODEL: User (models/user.py)
def test_user_model_has_required_fields(app_context):
    required = [
        "id",
        "email",
        "username",
        "password_hash",
        "full_name",
        "student_id",
        "role",
        "profile_badge",
        "club_name",
        "department",
        "phone",
        "created_at",
        "updated_at",
    ]
    for field in required:
        assert hasattr(User, field), f"Missing required field on User: {field}"

def test_user_set_password(app_context):
    user = User(
        email=f"{_unique('u')}@example.com",
        username=_unique("u"),
        password_hash="",
        full_name="X",
        role="STUDENT",
        profile_badge="STUDENT",
    )
    user.set_password("MySecret!123")
    assert user.password_hash
    assert user.password_hash != "MySecret!123"

def test_user_check_password(app_context):
    user = User(
        email=f"{_unique('u')}@example.com",
        username=_unique("u"),
        password_hash="",
        full_name="X",
        role="STUDENT",
        profile_badge="STUDENT",
    )
    user.set_password("MySecret!123")
    assert user.check_password("MySecret!123") is True
    assert user.check_password("WrongPass") is False

def test_user_to_public_dict(app_context):
    user = _create_user(
        role="CLUB_COORDINATOR",
        profile_badge="CLUB_COORDINATOR",
        student_id="SID-" + _unique("s"),
        club_name="Chess Club",
        department="CS",
        phone="12345",
    )

    d_no_contact = user.to_public_dict(include_contact=False)
    assert isinstance(d_no_contact, dict)
    for k in ["id", "email", "username", "full_name", "role", "profile_badge"]:
        assert k in d_no_contact
    assert "student_id" in d_no_contact
    assert "club_name" in d_no_contact
    assert "department" in d_no_contact
    assert "phone" in d_no_contact

    d_contact = user.to_public_dict(include_contact=True)
    assert isinstance(d_contact, dict)
    for k in ["id", "email", "username", "full_name", "role", "profile_badge"]:
        assert k in d_contact

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")
    student_id = "SID-" + _unique("dupSID")

    u1 = _create_user(email=email, username=username, student_id=student_id)

    u2 = User(
        email=email,
        username=_unique("other"),
        password_hash="",
        full_name="Other",
        student_id="SID-" + _unique("otherSID"),
        role="STUDENT",
        profile_badge="STUDENT",
    )
    u2.set_password("TestPass!123")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(
        email=f"{_unique('other')}@example.com",
        username=username,
        password_hash="",
        full_name="Other2",
        student_id="SID-" + _unique("otherSID2"),
        role="STUDENT",
        profile_badge="STUDENT",
    )
    u3.set_password("TestPass!123")
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u4 = User(
        email=f"{_unique('other2')}@example.com",
        username=_unique("other3"),
        password_hash="",
        full_name="Other3",
        student_id=student_id,
        role="STUDENT",
        profile_badge="STUDENT",
    )
    u4.set_password("TestPass!123")
    db.session.add(u4)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    assert u1.id is not None

# MODEL: ProfileViewingEvent (models/profile_viewing_event.py)
def test_profileviewingevent_model_has_required_fields(app_context):
    required = [
        "id",
        "title",
        "description",
        "location",
        "start_at",
        "end_at",
        "status",
        "capacity",
        "created_by_user_id",
        "created_at",
        "updated_at",
    ]
    for field in required:
        assert hasattr(ProfileViewingEvent, field), f"Missing required field on ProfileViewingEvent: {field}"

def test_profileviewingevent_to_public_dict(app_context):
    creator = _create_user(role="STUDENT_AFFAIRS_ADMIN", profile_badge="STUDENT_AFFAIRS_ADMIN")
    event = _create_event(created_by_user_id=creator.id, status="PUBLISHED")
    d = event.to_public_dict()
    assert isinstance(d, dict)
    for k in ["id", "title", "description", "location", "start_at", "end_at", "status", "capacity"]:
        assert k in d

def test_profileviewingevent_unique_constraints(app_context):
    creator = _create_user(role="STUDENT_AFFAIRS_ADMIN", profile_badge="STUDENT_AFFAIRS_ADMIN")
    e1 = _create_event(created_by_user_id=creator.id)
    e2 = _create_event(created_by_user_id=creator.id)
    assert e1.id != e2.id

# MODEL: ProfileViewingEventRegistration (models/profile_viewing_event_registration.py)
def test_profileviewingeventregistration_model_has_required_fields(app_context):
    required = ["id", "user_id", "event_id", "registered_at", "status"]
    for field in required:
        assert hasattr(
            ProfileViewingEventRegistration, field
        ), f"Missing required field on ProfileViewingEventRegistration: {field}"

def test_profileviewingeventregistration_to_public_dict(app_context):
    user = _create_user()
    creator = _create_user(role="STUDENT_AFFAIRS_ADMIN", profile_badge="STUDENT_AFFAIRS_ADMIN")
    event = _create_event(created_by_user_id=creator.id)
    reg = _create_registration(user_id=user.id, event_id=event.id, status="REGISTERED")
    d = reg.to_public_dict()
    assert isinstance(d, dict)
    assert "registration_id" in d or "id" in d
    assert "registration_status" in d or "status" in d
    assert "registered_at" in d
    assert "event" in d or "event_id" in d

def test_profileviewingeventregistration_unique_constraints(app_context):
    user = _create_user()
    creator = _create_user(role="STUDENT_AFFAIRS_ADMIN", profile_badge="STUDENT_AFFAIRS_ADMIN")
    event = _create_event(created_by_user_id=creator.id)
    r1 = _create_registration(user_id=user.id, event_id=event.id)
    r2 = _create_registration(user_id=user.id, event_id=event.id)
    assert r1.id != r2.id

# ROUTE: /profile (GET) - profile_page
def test_profile_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/profile"]
    assert rules, "Route /profile is missing"
    assert any("GET" in r.methods for r in rules), "Route /profile does not accept GET"

def test_profile_get_renders_template(client):
    user = None
    with app.app_context():
        user = _create_user()
    _login_as(client, user.id)
    resp = client.get("/profile")
    assert resp.status_code == 200
    assert resp.data is not None
    assert len(resp.data) > 0

# ROUTE: /api/profile (GET) - get_my_profile_api
def test_api_profile_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/api/profile"]
    assert rules, "Route /api/profile is missing"
    assert any("GET" in r.methods for r in rules), "Route /api/profile does not accept GET"

def test_api_profile_get_renders_template(client):
    with app.app_context():
        user = _create_user()
        creator = _create_user(role="STUDENT_AFFAIRS_ADMIN", profile_badge="STUDENT_AFFAIRS_ADMIN")
        event = _create_event(created_by_user_id=creator.id)
        _create_registration(user_id=user.id, event_id=event.id, status="REGISTERED")
        user_id = user.id

    _login_as(client, user_id)
    resp = client.get("/api/profile")
    assert resp.status_code == 200
    assert resp.is_json is True
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "user" in data
    assert "registered_events" in data

# ROUTE: /api/users/<int:user_id>/profile (GET) - get_user_profile_api
def test_api_users_user_id_profile_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/api/users/<int:user_id>/profile"]
    assert rules, "Route /api/users/<int:user_id>/profile is missing"
    assert any("GET" in r.methods for r in rules), "Route /api/users/<int:user_id>/profile does not accept GET"

def test_api_users_user_id_profile_get_renders_template(client):
    with app.app_context():
        viewer = _create_user(role="COLLEGE_ADMIN", profile_badge="COLLEGE_ADMIN")
        target = _create_user(role="STUDENT", profile_badge="STUDENT")
        creator = _create_user(role="STUDENT_AFFAIRS_ADMIN", profile_badge="STUDENT_AFFAIRS_ADMIN")
        event = _create_event(created_by_user_id=creator.id)
        _create_registration(user_id=target.id, event_id=event.id, status="REGISTERED")
        viewer_id = viewer.id
        target_id = target.id

    _login_as(client, viewer_id)
    resp = client.get(f"/api/users/{target_id}/profile")
    assert resp.status_code in (200, 403)
    if resp.status_code == 200:
        assert resp.is_json is True
        data = resp.get_json()
        assert "user" in data
        assert "registered_events" in data
    else:
        assert resp.is_json is True
        data = resp.get_json()
        assert data.get("error") == "forbidden"

# HELPER: login_required(view_func)
def test_login_required_function_exists():
    assert callable(login_required)

def test_login_required_with_valid_input(client):
    def _view():
        return "ok"

    wrapped = login_required(_view)
    assert callable(wrapped)

    with app.app_context():
        user = _create_user()
        user_id = user.id

    _login_as(client, user_id)
    resp = client.get("/api/profile")
    assert resp.status_code == 200

def test_login_required_with_invalid_input():
    with pytest.raises(Exception):
        login_required(None)

# HELPER: get_current_user()
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(client):
    with app.app_context():
        user = _create_user()
        user_id = user.id

    with app.test_request_context("/api/profile"):
        with patch("controllers.profile_viewing_controller.session", {"user_id": user_id}):
            current = get_current_user()
            assert current is not None
            assert getattr(current, "id", None) == user_id

def test_get_current_user_with_invalid_input():
    with app.test_request_context("/api/profile"):
        with patch("controllers.profile_viewing_controller.session", {}):
            current = get_current_user()
            assert current is None

# HELPER: can_view_profile(viewer, target_user)
def test_can_view_profile_function_exists():
    assert callable(can_view_profile)

def test_can_view_profile_with_valid_input(app_context):
    viewer = _create_user(role="STUDENT_AFFAIRS_ADMIN", profile_badge="STUDENT_AFFAIRS_ADMIN")
    target = _create_user(role="STUDENT", profile_badge="STUDENT")
    result = can_view_profile(viewer, target)
    assert isinstance(result, bool)

def test_can_view_profile_with_invalid_input(app_context):
    target = _create_user(role="STUDENT", profile_badge="STUDENT")
    with pytest.raises(Exception):
        can_view_profile(None, target)
    with pytest.raises(Exception):
        can_view_profile(target, None)

# HELPER: build_profile_payload(target_user, include_registered_events)
def test_build_profile_payload_function_exists():
    assert callable(build_profile_payload)

def test_build_profile_payload_with_valid_input(app_context):
    user = _create_user(role="STUDENT", profile_badge="STUDENT")
    creator = _create_user(role="STUDENT_AFFAIRS_ADMIN", profile_badge="STUDENT_AFFAIRS_ADMIN")
    event = _create_event(created_by_user_id=creator.id)
    _create_registration(user_id=user.id, event_id=event.id, status="REGISTERED")

    payload = build_profile_payload(user, include_registered_events=True)
    assert isinstance(payload, dict)
    assert "user" in payload
    assert "registered_events" in payload
    assert isinstance(payload["registered_events"], list)

    payload2 = build_profile_payload(user, include_registered_events=False)
    assert isinstance(payload2, dict)
    assert "user" in payload2
    assert "registered_events" in payload2
    assert isinstance(payload2["registered_events"], list)

def test_build_profile_payload_with_invalid_input(app_context):
    with pytest.raises(Exception):
        build_profile_payload(None, include_registered_events=True)
    user = _create_user()
    with pytest.raises(Exception):
        build_profile_payload(user, include_registered_events=None)

# VIEW: render_profile_page(user_dict, registered_events)
def test_render_profile_page_function_exists():
    assert callable(render_profile_page)

def test_render_profile_page_with_valid_input(app_context):
    user = _create_user()
    user_dict = user.to_public_dict(include_contact=True)
    html = render_profile_page(user_dict, registered_events=[])
    assert isinstance(html, str)
    assert len(html) > 0

def test_render_profile_page_with_invalid_input(app_context):
    with pytest.raises(Exception):
        render_profile_page(None, registered_events=[])
    with pytest.raises(Exception):
        render_profile_page({}, registered_events=None)