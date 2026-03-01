import os
import sys
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.profile_viewing_event import Event
from models.profile_viewing_event_registration import EventRegistration
from controllers.profile_viewing_controller import (
    get_current_user,
    profile_type_to_badge,
    serialize_event_registration,
)
from views.profile_viewing_views import build_profile_context

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

def _create_user(db_session, profile_type="STUDENT", password="Passw0rd!"):
    u = User(
        name=_unique("Name"),
        roll_number=_unique("ROLL"),
        email=f"{_unique('user')}@example.com",
        profile_type=profile_type,
    )
    u.set_password(password)
    db_session.add(u)
    db_session.commit()
    return u

def _create_event(db_session, title=None):
    now = datetime.utcnow()
    e = Event(
        title=title or _unique("Event"),
        description="Desc",
        start_at=now,
        end_at=now,
        location="Loc",
    )
    db_session.add(e)
    db_session.commit()
    return e

def _create_registration(db_session, user_id: int, event_id: int):
    r = EventRegistration(user_id=user_id, event_id=event_id, registered_at=datetime.utcnow())
    db_session.add(r)
    db_session.commit()
    return r

# MODEL: User (models/user.py)
def test_user_model_has_required_fields():
    required = [
        "id",
        "name",
        "roll_number",
        "email",
        "password_hash",
        "profile_type",
        "created_at",
        "updated_at",
    ]
    for field in required:
        assert hasattr(User, field), f"User model missing required field: {field}"

def test_user_set_password():
    u = User(name="X", roll_number=_unique("ROLL"), email=f"{_unique('e')}@example.com", profile_type="STUDENT")
    u.set_password("secret123")
    assert getattr(u, "password_hash", None), "User.set_password must set password_hash"
    assert u.password_hash != "secret123", "Password must not be stored in plaintext"

def test_user_check_password():
    u = User(name="X", roll_number=_unique("ROLL"), email=f"{_unique('e')}@example.com", profile_type="STUDENT")
    u.set_password("secret123")
    assert u.check_password("secret123") is True
    assert u.check_password("wrong") is False

def test_user_unique_constraints(client):
    with app.app_context():
        roll = _unique("ROLL")
        email = f"{_unique('e')}@example.com"

        u1 = User(name="A", roll_number=roll, email=email, profile_type="STUDENT")
        u1.set_password("pw1")
        db.session.add(u1)
        db.session.commit()

        u2 = User(name="B", roll_number=roll, email=f"{_unique('e2')}@example.com", profile_type="STUDENT")
        u2.set_password("pw2")
        db.session.add(u2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

        u3 = User(name="C", roll_number=_unique("ROLL2"), email=email, profile_type="STUDENT")
        u3.set_password("pw3")
        db.session.add(u3)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

# MODEL: Event (models/profile_viewing_event.py)
def test_event_model_has_required_fields():
    required = [
        "id",
        "title",
        "description",
        "start_at",
        "end_at",
        "location",
        "created_at",
        "updated_at",
    ]
    for field in required:
        assert hasattr(Event, field), f"Event model missing required field: {field}"

def test_event_unique_constraints(client):
    with app.app_context():
        now = datetime.utcnow()
        title = _unique("EventTitle")

        e1 = Event(title=title, description=None, start_at=now, end_at=None, location=None)
        e2 = Event(title=title, description=None, start_at=now, end_at=None, location=None)
        db.session.add_all([e1, e2])
        db.session.commit()

        assert Event.query.filter_by(title=title).count() == 2

# MODEL: EventRegistration (models/profile_viewing_event_registration.py)
def test_eventregistration_model_has_required_fields():
    required = ["id", "user_id", "event_id", "registered_at"]
    for field in required:
        assert hasattr(EventRegistration, field), f"EventRegistration model missing required field: {field}"

def test_eventregistration_unique_constraints(client):
    with app.app_context():
        u = _create_user(db.session)
        e = _create_event(db.session)

        r1 = EventRegistration(user_id=u.id, event_id=e.id, registered_at=datetime.utcnow())
        r2 = EventRegistration(user_id=u.id, event_id=e.id, registered_at=datetime.utcnow())
        db.session.add_all([r1, r2])
        db.session.commit()

        assert EventRegistration.query.filter_by(user_id=u.id, event_id=e.id).count() == 2

# ROUTE: /profile (GET) - view_profile
def test_profile_get_exists(client):
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/profile" in rules, "Route /profile must exist"

    resp = client.get("/profile")
    assert resp.status_code in (200, 302, 401, 403)

def test_profile_get_renders_template(client):
    resp = client.get("/profile", follow_redirects=True)
    assert resp.status_code == 200
    assert b"<" in resp.data
    assert b"html" in resp.data.lower()

# ROUTE: /api/profile (GET) - get_profile_json
def test_api_profile_get_exists(client):
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/api/profile" in rules, "Route /api/profile must exist"

    resp = client.get("/api/profile")
    assert resp.status_code in (200, 302, 401, 403)

def test_api_profile_get_renders_template(client):
    resp = client.get("/api/profile", follow_redirects=True)
    assert resp.status_code == 200
    content_type = resp.headers.get("Content-Type", "").lower()
    assert ("application/json" in content_type) or (b"{" in resp.data) or (b"[" in resp.data)

# HELPER: get_current_user(session)
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(client):
    with app.app_context():
        u = _create_user(db.session)
        with client.session_transaction() as sess:
            sess["user_id"] = u.id

        with client.session_transaction() as sess:
            got = get_current_user(sess)

        assert (got is None) or isinstance(got, User)
        if isinstance(got, User):
            assert got.id == u.id

def test_get_current_user_with_invalid_input():
    assert get_current_user(None) is None
    assert get_current_user({}) is None

# HELPER: profile_type_to_badge(profile_type: str)
def test_profile_type_to_badge_function_exists():
    assert callable(profile_type_to_badge)

def test_profile_type_to_badge_with_valid_input():
    expected = {
        "STUDENT": "Student",
        "CLUB_HEAD": "Club Head",
        "STUDENT_COUNCIL_CLUBS_COORDINATOR": "Student Council Clubs Coordinator",
        "ADMIN": "Admin",
    }
    for k, v in expected.items():
        assert profile_type_to_badge(k) == v

def test_profile_type_to_badge_with_invalid_input():
    assert profile_type_to_badge("") in ("", "Unknown", "Other", None)
    assert profile_type_to_badge("NOT_A_TYPE") in ("", "Unknown", "Other", None)
    assert profile_type_to_badge(None) in ("", "Unknown", "Other", None)

# HELPER: serialize_event_registration(registration: EventRegistration)
def test_serialize_event_registration_function_exists():
    assert callable(serialize_event_registration)

def test_serialize_event_registration_with_valid_input(client):
    with app.app_context():
        u = _create_user(db.session)
        e = _create_event(db.session)
        r = _create_registration(db.session, user_id=u.id, event_id=e.id)

        data = serialize_event_registration(r)
        assert isinstance(data, dict)
        assert "id" in data
        assert "user_id" in data
        assert "event_id" in data
        assert "registered_at" in data
        assert data["id"] == r.id
        assert data["user_id"] == u.id
        assert data["event_id"] == e.id

def test_serialize_event_registration_with_invalid_input():
    assert serialize_event_registration(None) in ({}, None)

    bogus = MagicMock()
    bogus.id = 1
    bogus.user_id = 2
    bogus.event_id = 3
    bogus.registered_at = None
    out = serialize_event_registration(bogus)
    assert isinstance(out, dict) or out is None

# VIEW: build_profile_context(user: User, registrations: list[EventRegistration]) -> dict
def test_build_profile_context_function_exists():
    assert callable(build_profile_context)

def test_build_profile_context_with_valid_input(client):
    with app.app_context():
        u = _create_user(db.session, profile_type="ADMIN")
        e = _create_event(db.session)
        r = _create_registration(db.session, user_id=u.id, event_id=e.id)

        ctx = build_profile_context(u, [r])
        assert isinstance(ctx, dict)
        for key in ("user", "registrations"):
            assert key in ctx, f"build_profile_context must include '{key}' in context"

def test_build_profile_context_with_invalid_input():
    with pytest.raises(Exception):
        build_profile_context(None, [])

    with pytest.raises(Exception):
        build_profile_context(MagicMock(), None)

# CONTROLLER/INTEGRATION: ensure /profile shows required user details + badge + registrations when logged in
def test_profile_page_displays_user_details_and_registrations(client):
    with app.app_context():
        u = _create_user(db.session, profile_type="STUDENT")
        e1 = _create_event(db.session, title=_unique("EventOne"))
        e2 = _create_event(db.session, title=_unique("EventTwo"))
        _create_registration(db.session, user_id=u.id, event_id=e1.id)
        _create_registration(db.session, user_id=u.id, event_id=e2.id)

        with client.session_transaction() as sess:
            sess["user_id"] = u.id

        resp = client.get("/profile", follow_redirects=True)
        assert resp.status_code == 200

        body = resp.data
        assert u.name.encode() in body
        assert u.roll_number.encode() in body
        assert u.email.encode() in body
        assert profile_type_to_badge("STUDENT").encode() in body
        assert e1.title.encode() in body or e2.title.encode() in body

def test_api_profile_json_includes_user_details_and_registrations(client):
    with app.app_context():
        u = _create_user(db.session, profile_type="CLUB_HEAD")
        e = _create_event(db.session, title=_unique("EventJSON"))
        _create_registration(db.session, user_id=u.id, event_id=e.id)

        with client.session_transaction() as sess:
            sess["user_id"] = u.id

        resp = client.get("/api/profile", follow_redirects=True)
        assert resp.status_code == 200

        data = resp.get_json(silent=True)
        if data is None:
            assert b"roll" in resp.data.lower() or b"email" in resp.data.lower() or b"registr" in resp.data.lower()
            return

        assert isinstance(data, dict)
        for key in ("name", "roll_number", "email", "profile_type", "badge", "registrations"):
            assert key in data, f"/api/profile JSON missing key: {key}"
        assert data["name"] == u.name
        assert data["roll_number"] == u.roll_number
        assert data["email"] == u.email
        assert data["badge"] == profile_type_to_badge("CLUB_HEAD")
        assert isinstance(data["registrations"], list)
        assert len(data["registrations"]) >= 1