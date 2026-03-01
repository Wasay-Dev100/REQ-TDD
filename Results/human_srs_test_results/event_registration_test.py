import os
import sys
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from flask import template_rendered
from werkzeug.exceptions import NotFound

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.event_registration_event import EventRegistrationEvent
from models.event_registration_registration import EventRegistrationRegistration
from models.event_registration_comment import EventRegistrationComment
from controllers.event_registration_controller import (
    get_current_user,
    login_required,
    get_approved_event_or_404,
    is_already_registered,
    count_registrations,
)
from views.event_registration_views import serialize_event, serialize_comment

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
def captured_templates():
    recorded = []

    def record(sender, template, context, **extra):
        recorded.append((template, context))

    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app)

def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_user_in_db():
    username = _unique("user")
    email = f"{_unique('email')}@example.com"
    user = User(username=username, email=email, password_hash="")
    if hasattr(user, "set_password") and callable(getattr(user, "set_password")):
        user.set_password("Password123!")
    else:
        user.password_hash = "not-a-real-hash"
    db.session.add(user)
    db.session.commit()
    return user

def _create_event_in_db(
    *,
    is_approved: bool = True,
    capacity: int | None = 10,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
):
    now = datetime.utcnow()
    start_at = start_at or (now + timedelta(days=1))
    event = EventRegistrationEvent(
        title=_unique("Event"),
        description="Description",
        location="Location",
        start_at=start_at,
        end_at=end_at,
        capacity=capacity,
        is_approved=is_approved,
        approved_at=(now if is_approved else None),
        created_by_user_id=1,
        created_at=now,
        updated_at=now,
    )
    db.session.add(event)
    db.session.commit()
    return event

def _register_user_for_event(event_id: int, user_id: int, registered_at: datetime | None = None):
    reg = EventRegistrationRegistration(
        event_id=event_id,
        user_id=user_id,
        registered_at=registered_at or datetime.utcnow(),
    )
    db.session.add(reg)
    db.session.commit()
    return reg

def _post_comment(event_id: int, user_id: int, content: str):
    now = datetime.utcnow()
    c = EventRegistrationComment(
        event_id=event_id,
        user_id=user_id,
        content=content,
        created_at=now,
        updated_at=None,
    )
    db.session.add(c)
    db.session.commit()
    return c

def _login_session(client, user_id: int):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

# MODEL: User (models/user.py)
def test_user_model_has_required_fields():
    for field in ["id", "email", "username", "password_hash"]:
        assert hasattr(User, field), f"User missing required field: {field}"

def test_user_set_password():
    user = User(username=_unique("u"), email=f"{_unique('e')}@example.com", password_hash="")
    assert hasattr(user, "set_password") and callable(user.set_password)
    user.set_password("Password123!")
    assert user.password_hash
    assert user.password_hash != "Password123!"

def test_user_check_password():
    user = User(username=_unique("u"), email=f"{_unique('e')}@example.com", password_hash="")
    assert hasattr(user, "check_password") and callable(user.check_password)
    user.set_password("Password123!")
    assert user.check_password("Password123!") is True
    assert user.check_password("WrongPassword!") is False

def test_user_unique_constraints(app_context):
    u1 = User(username=_unique("u"), email=f"{_unique('e')}@example.com", password_hash="")
    u1.set_password("Password123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(username=u1.username, email=f"{_unique('e')}@example.com", password_hash="")
    u2.set_password("Password123!")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(username=_unique("u"), email=u1.email, password_hash="")
    u3.set_password("Password123!")
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# MODEL: EventRegistrationEvent (models/event_registration_event.py)
def test_eventregistrationevent_model_has_required_fields():
    for field in [
        "id",
        "title",
        "description",
        "location",
        "start_at",
        "end_at",
        "capacity",
        "is_approved",
        "approved_at",
        "created_by_user_id",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(EventRegistrationEvent, field), f"EventRegistrationEvent missing required field: {field}"

def test_eventregistrationevent_is_open_for_registration(app_context):
    assert hasattr(EventRegistrationEvent, "is_open_for_registration") and callable(
        getattr(EventRegistrationEvent, "is_open_for_registration")
    )

    event = _create_event_in_db(is_approved=True, capacity=2)
    assert event.is_open_for_registration() is True

    user = _create_user_in_db()
    _register_user_for_event(event.id, user.id)
    _register_user_for_event(event.id, _create_user_in_db().id)
    db.session.refresh(event)
    assert event.is_open_for_registration() is False

    unapproved = _create_event_in_db(is_approved=False, capacity=10)
    assert unapproved.is_open_for_registration() is False

def test_eventregistrationevent_remaining_capacity(app_context):
    assert hasattr(EventRegistrationEvent, "remaining_capacity") and callable(
        getattr(EventRegistrationEvent, "remaining_capacity")
    )

    event = _create_event_in_db(is_approved=True, capacity=3)
    remaining = event.remaining_capacity()
    assert isinstance(remaining, int)
    assert remaining == 3

    u1 = _create_user_in_db()
    u2 = _create_user_in_db()
    _register_user_for_event(event.id, u1.id)
    _register_user_for_event(event.id, u2.id)
    db.session.refresh(event)
    assert event.remaining_capacity() == 1

    unlimited = _create_event_in_db(is_approved=True, capacity=None)
    rem2 = unlimited.remaining_capacity()
    assert isinstance(rem2, int)
    assert rem2 >= 0

def test_eventregistrationevent_unique_constraints(app_context):
    e1 = _create_event_in_db(is_approved=True, capacity=10)
    e2 = EventRegistrationEvent(
        title=e1.title,
        description=e1.description,
        location=e1.location,
        start_at=e1.start_at,
        end_at=e1.end_at,
        capacity=e1.capacity,
        is_approved=e1.is_approved,
        approved_at=e1.approved_at,
        created_by_user_id=e1.created_by_user_id,
        created_at=e1.created_at,
        updated_at=e1.updated_at,
    )
    db.session.add(e2)
    db.session.commit()
    assert e2.id is not None

# MODEL: EventRegistrationRegistration (models/event_registration_registration.py)
def test_eventregistrationregistration_model_has_required_fields():
    for field in ["id", "event_id", "user_id", "registered_at"]:
        assert hasattr(EventRegistrationRegistration, field), f"EventRegistrationRegistration missing required field: {field}"

def test_eventregistrationregistration_unique_constraints(app_context):
    event = _create_event_in_db(is_approved=True, capacity=10)
    user = _create_user_in_db()

    r1 = _register_user_for_event(event.id, user.id)
    r2 = _register_user_for_event(event.id, user.id)
    assert r1.id is not None and r2.id is not None

# MODEL: EventRegistrationComment (models/event_registration_comment.py)
def test_eventregistrationcomment_model_has_required_fields():
    for field in ["id", "event_id", "user_id", "content", "created_at", "updated_at"]:
        assert hasattr(EventRegistrationComment, field), f"EventRegistrationComment missing required field: {field}"

def test_eventregistrationcomment_unique_constraints(app_context):
    event = _create_event_in_db(is_approved=True, capacity=10)
    user = _create_user_in_db()

    c1 = _post_comment(event.id, user.id, "Hello")
    c2 = _post_comment(event.id, user.id, "Hello")
    assert c1.id is not None and c2.id is not None

# ROUTE: /events (GET) - list_events
def test_events_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/events"]
    assert rules, "Route /events is not registered"
    assert any("GET" in r.methods for r in rules), "/events does not accept GET"

def test_events_get_renders_template(client, captured_templates, app_context):
    _create_event_in_db(is_approved=True, capacity=10)
    _create_event_in_db(is_approved=False, capacity=10)

    resp = client.get("/events")
    assert resp.status_code == 200
    assert captured_templates, "No template rendered for /events"
    template, context = captured_templates[-1]
    assert template.name == "event_registration_events.html"
    assert "events" in context

# ROUTE: /events/<int:event_id> (GET) - event_detail
def test_events_event_id_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/events/<int:event_id>"]
    assert rules, "Route /events/<int:event_id> is not registered"
    assert any("GET" in r.methods for r in rules), "/events/<int:event_id> does not accept GET"

def test_events_event_id_get_renders_template(client, captured_templates, app_context):
    event = _create_event_in_db(is_approved=True, capacity=5)
    resp = client.get(f"/events/{event.id}")
    assert resp.status_code == 200
    assert captured_templates, "No template rendered for /events/<int:event_id>"
    template, context = captured_templates[-1]
    assert template.name == "event_registration_event_detail.html"
    for key in ["event", "comments", "is_registered", "remaining_capacity"]:
        assert key in context

# ROUTE: /events/<int:event_id>/register (POST) - register_for_event
def test_events_event_id_register_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/events/<int:event_id>/register"]
    assert rules, "Route /events/<int:event_id>/register is not registered"
    assert any("POST" in r.methods for r in rules), "/events/<int:event_id>/register does not accept POST"

def test_events_event_id_register_post_success(client, app_context):
    user = _create_user_in_db()
    event = _create_event_in_db(is_approved=True, capacity=10)
    _login_session(client, user.id)

    resp = client.post(f"/events/{event.id}/register")
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/")

    reg = EventRegistrationRegistration.query.filter_by(event_id=event.id, user_id=user.id).first()
    assert reg is not None

def test_events_event_id_register_post_missing_required_fields(client, app_context):
    user = _create_user_in_db()
    _login_session(client, user.id)

    resp = client.post("/events/0/register")
    assert resp.status_code in (404, 400)

def test_events_event_id_register_post_invalid_data(client, app_context):
    user = _create_user_in_db()
    _login_session(client, user.id)

    resp = client.post("/events/not-an-int/register")
    assert resp.status_code == 404

def test_events_event_id_register_post_duplicate_data(client, app_context):
    user = _create_user_in_db()
    event = _create_event_in_db(is_approved=True, capacity=10)
    _login_session(client, user.id)

    resp1 = client.post(f"/events/{event.id}/register")
    assert resp1.status_code in (302, 200)

    resp2 = client.post(f"/events/{event.id}/register")
    assert resp2.status_code == 409

# ROUTE: /events/<int:event_id>/comments (POST) - post_comment
def test_events_event_id_comments_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/events/<int:event_id>/comments"]
    assert rules, "Route /events/<int:event_id>/comments is not registered"
    assert any("POST" in r.methods for r in rules), "/events/<int:event_id>/comments does not accept POST"

def test_events_event_id_comments_post_success(client, app_context):
    user = _create_user_in_db()
    event = _create_event_in_db(is_approved=True, capacity=10)
    _login_session(client, user.id)

    resp = client.post(f"/events/{event.id}/comments", data={"content": "Looking forward!"})
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith(f"/events/{event.id}")

    comment = EventRegistrationComment.query.filter_by(event_id=event.id, user_id=user.id).first()
    assert comment is not None
    assert comment.content.strip() == "Looking forward!"

def test_events_event_id_comments_post_missing_required_fields(client, app_context):
    user = _create_user_in_db()
    event = _create_event_in_db(is_approved=True, capacity=10)
    _login_session(client, user.id)

    resp = client.post(f"/events/{event.id}/comments", data={})
    assert resp.status_code == 400

def test_events_event_id_comments_post_invalid_data(client, app_context):
    user = _create_user_in_db()
    event = _create_event_in_db(is_approved=True, capacity=10)
    _login_session(client, user.id)

    resp = client.post(f"/events/{event.id}/comments", json={"content": 123})
    assert resp.status_code in (400, 415, 200, 302)

def test_events_event_id_comments_post_duplicate_data(client, app_context):
    user = _create_user_in_db()
    event = _create_event_in_db(is_approved=True, capacity=10)
    _login_session(client, user.id)

    resp1 = client.post(f"/events/{event.id}/comments", data={"content": "Same"})
    assert resp1.status_code == 302

    resp2 = client.post(f"/events/{event.id}/comments", data={"content": "Same"})
    assert resp2.status_code == 302

    comments = EventRegistrationComment.query.filter_by(event_id=event.id, user_id=user.id, content="Same").all()
    assert len(comments) >= 2

# HELPER: get_current_user(N/A)
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(client, app_context):
    user = _create_user_in_db()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id

    with app.test_request_context("/events"):
        with client.session_transaction() as sess:
            from flask import session

            session["user_id"] = sess["user_id"]
        cu = get_current_user()
        assert cu is not None
        assert getattr(cu, "id", None) == user.id

def test_get_current_user_with_invalid_input(client, app_context):
    with app.test_request_context("/events"):
        cu = get_current_user()
        assert cu is None

    with app.test_request_context("/events"):
        from flask import session

        session["user_id"] = "not-an-int"
        cu2 = get_current_user()
        assert cu2 is None

# HELPER: login_required(view_func)
def test_login_required_function_exists():
    assert callable(login_required)

def test_login_required_with_valid_input(client, app_context):
    @login_required
    def protected_view():
        return "ok", 200

    user = _create_user_in_db()
    with app.test_request_context("/protected"):
        from flask import session

        session["user_id"] = user.id
        resp = protected_view()
        assert resp[1] == 200

def test_login_required_with_invalid_input(app_context):
    with pytest.raises(Exception):
        login_required(None)

# HELPER: get_approved_event_or_404(event_id)
def test_get_approved_event_or_404_function_exists():
    assert callable(get_approved_event_or_404)

def test_get_approved_event_or_404_with_valid_input(app_context):
    event = _create_event_in_db(is_approved=True, capacity=10)
    found = get_approved_event_or_404(event.id)
    assert found is not None
    assert getattr(found, "id", None) == event.id

def test_get_approved_event_or_404_with_invalid_input(app_context):
    with pytest.raises(NotFound):
        get_approved_event_or_404(999999)

    unapproved = _create_event_in_db(is_approved=False, capacity=10)
    with pytest.raises(NotFound):
        get_approved_event_or_404(unapproved.id)

# HELPER: is_already_registered(event_id, user_id)
def test_is_already_registered_function_exists():
    assert callable(is_already_registered)

def test_is_already_registered_with_valid_input(app_context):
    user = _create_user_in_db()
    event = _create_event_in_db(is_approved=True, capacity=10)

    assert is_already_registered(event.id, user.id) is False
    _register_user_for_event(event.id, user.id)
    assert is_already_registered(event.id, user.id) is True

def test_is_already_registered_with_invalid_input(app_context):
    assert is_already_registered(-1, -1) is False
    assert is_already_registered(0, 0) is False

# HELPER: count_registrations(event_id)
def test_count_registrations_function_exists():
    assert callable(count_registrations)

def test_count_registrations_with_valid_input(app_context):
    event = _create_event_in_db(is_approved=True, capacity=10)
    assert count_registrations(event.id) == 0

    u1 = _create_user_in_db()
    u2 = _create_user_in_db()
    _register_user_for_event(event.id, u1.id)
    _register_user_for_event(event.id, u2.id)
    assert count_registrations(event.id) == 2

def test_count_registrations_with_invalid_input(app_context):
    assert count_registrations(-1) == 0
    assert count_registrations(0) == 0