import os
import sys
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, mail  # noqa: E402
from models.user import User  # noqa: E402
from models.contact_the_developer_message import ContactTheDeveloperMessage  # noqa: E402
from controllers.contact_the_developer_controller import (  # noqa: E402
    validate_contact_payload,
    persist_message,
    send_contact_message,
    get_configured_social_links,
)
from views.contact_the_developer_views import render_contact_page  # noqa: E402

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
    return f"test_{uuid.uuid4().hex[:10]}@example.com"

def _unique_name():
    return f"Test User {uuid.uuid4().hex[:8]}"

def _unique_message():
    return f"Hello developer {uuid.uuid4().hex}"

def _assert_route_exists(rule, methods):
    rules = list(app.url_map.iter_rules())
    matching = [r for r in rules if r.rule == rule]
    assert matching, f"Missing route: {rule}"
    allowed = set()
    for r in matching:
        allowed |= set(r.methods or [])
    for m in methods:
        assert m in allowed, f"Route {rule} does not allow method {m}. Allowed: {sorted(allowed)}"

# MODEL: ContactTheDeveloperMessage (models/contact_the_developer_message.py)
def test_contactthedevelopermessage_model_has_required_fields(app_context):
    cols = ContactTheDeveloperMessage.__table__.columns
    for field in ["id", "name", "email", "message", "created_at", "status"]:
        assert field in cols, f"Missing field '{field}' on ContactTheDeveloperMessage"

def test_contactthedevelopermessage_to_dict(app_context):
    msg = ContactTheDeveloperMessage(
        name=_unique_name(),
        email=_unique_email(),
        message=_unique_message(),
        created_at=datetime.utcnow(),
        status="new",
    )
    db.session.add(msg)
    db.session.commit()

    assert hasattr(msg, "to_dict") and callable(getattr(msg, "to_dict"))
    data = msg.to_dict()
    assert isinstance(data, dict)

    for key in ["id", "name", "email", "message", "created_at", "status"]:
        assert key in data, f"to_dict() missing key '{key}'"

    assert data["id"] == msg.id
    assert data["name"] == msg.name
    assert data["email"] == msg.email
    assert data["message"] == msg.message
    assert data["status"] == msg.status

def test_contactthedevelopermessage_unique_constraints(app_context):
    unique_constraints = list(ContactTheDeveloperMessage.__table__.constraints)
    uniques = [c for c in unique_constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert len(uniques) == 0, "Expected no unique constraints on ContactTheDeveloperMessage"

# ROUTE: /contact (GET) - contact_page
def test_contact_get_exists():
    _assert_route_exists("/contact", ["GET"])

def test_contact_get_renders_template(client):
    resp = client.get("/contact")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json", "text/plain")
    assert resp.data is not None
    assert len(resp.data) > 0

# ROUTE: /contact (POST) - submit_contact
def test_contact_post_exists():
    _assert_route_exists("/contact", ["POST"])

def test_contact_post_success(client):
    payload = {"name": _unique_name(), "email": _unique_email(), "message": _unique_message()}

    with patch("app.mail.send") as mock_send:
        resp = client.post("/contact", data=payload, follow_redirects=False)

    assert resp.status_code in (200, 201, 302, 303)

    with app.app_context():
        saved = ContactTheDeveloperMessage.query.filter_by(email=payload["email"]).first()
        assert saved is not None, "Expected message to be persisted on successful POST"
        assert saved.name == payload["name"]
        assert saved.message == payload["message"]

    assert mock_send.call_count in (0, 1)

def test_contact_post_missing_required_fields(client):
    with patch("app.mail.send") as mock_send:
        resp = client.post("/contact", data={"name": _unique_name(), "email": _unique_email()}, follow_redirects=False)

    assert resp.status_code in (200, 400, 422)
    assert mock_send.call_count == 0

    with app.app_context():
        saved = ContactTheDeveloperMessage.query.filter_by(email=None).first()
        assert saved is None

def test_contact_post_invalid_data(client):
    payload = {"name": _unique_name(), "email": "not-an-email", "message": _unique_message()}

    with patch("app.mail.send") as mock_send:
        resp = client.post("/contact", data=payload, follow_redirects=False)

    assert resp.status_code in (200, 400, 422)
    assert mock_send.call_count == 0

    with app.app_context():
        saved = ContactTheDeveloperMessage.query.filter_by(email=payload["email"]).first()
        assert saved is None, "Invalid email should not be persisted"

def test_contact_post_duplicate_data(client):
    email = _unique_email()
    payload1 = {"name": _unique_name(), "email": email, "message": _unique_message()}
    payload2 = {"name": _unique_name(), "email": email, "message": _unique_message()}

    with patch("app.mail.send"):
        resp1 = client.post("/contact", data=payload1, follow_redirects=False)
        resp2 = client.post("/contact", data=payload2, follow_redirects=False)

    assert resp1.status_code in (200, 201, 302, 303)
    assert resp2.status_code in (200, 201, 302, 303, 400, 409, 422)

    with app.app_context():
        count = ContactTheDeveloperMessage.query.filter_by(email=email).count()
        assert count in (1, 2), "Duplicates are applicable only if allowed; expected 1 or 2 records"

# ROUTE: /social-links (GET) - get_social_links
def test_social_links_get_exists():
    _assert_route_exists("/social-links", ["GET"])

def test_social_links_get_renders_template(client):
    resp = client.get("/social-links")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json", "text/plain")
    assert resp.data is not None
    assert len(resp.data) > 0

# HELPER: validate_contact_payload(payload)
def test_validate_contact_payload_function_exists():
    assert callable(validate_contact_payload)

def test_validate_contact_payload_with_valid_input():
    payload = {"name": _unique_name(), "email": _unique_email(), "message": _unique_message()}
    ok, errors = validate_contact_payload(payload)
    assert isinstance(ok, bool)
    assert isinstance(errors, dict)
    assert ok is True
    assert errors == {} or all(v in (None, "", [], {}) for v in errors.values())

def test_validate_contact_payload_with_invalid_input():
    payload = {"name": "", "email": "bad", "message": ""}
    ok, errors = validate_contact_payload(payload)
    assert isinstance(ok, bool)
    assert isinstance(errors, dict)
    assert ok is False
    assert errors, "Expected validation errors for invalid payload"

# HELPER: persist_message(name, email, message)
def test_persist_message_function_exists():
    assert callable(persist_message)

def test_persist_message_with_valid_input(app_context):
    name = _unique_name()
    email = _unique_email()
    message = _unique_message()

    saved = persist_message(name, email, message)
    assert isinstance(saved, ContactTheDeveloperMessage)
    assert saved.id is not None
    assert saved.name == name
    assert saved.email == email
    assert saved.message == message

    fetched = ContactTheDeveloperMessage.query.filter_by(id=saved.id).first()
    assert fetched is not None
    assert fetched.email == email

def test_persist_message_with_invalid_input(app_context):
    with pytest.raises(Exception):
        persist_message("", "not-an-email", "")

# HELPER: send_contact_message(contact_message)
def test_send_contact_message_function_exists():
    assert callable(send_contact_message)

def test_send_contact_message_with_valid_input(app_context):
    msg = ContactTheDeveloperMessage(
        name=_unique_name(),
        email=_unique_email(),
        message=_unique_message(),
        created_at=datetime.utcnow(),
        status="new",
    )
    db.session.add(msg)
    db.session.commit()

    with patch("app.mail.send") as mock_send:
        result = send_contact_message(msg)

    assert isinstance(result, bool)
    assert result is True
    assert mock_send.call_count in (0, 1)

def test_send_contact_message_with_invalid_input(app_context):
    with patch("app.mail.send") as mock_send:
        result = send_contact_message(None)

    assert isinstance(result, bool)
    assert result is False
    assert mock_send.call_count == 0

# HELPER: get_configured_social_links(N/A)
def test_get_configured_social_links_function_exists():
    assert callable(get_configured_social_links)

def test_get_configured_social_links_with_valid_input():
    links = get_configured_social_links()
    assert isinstance(links, list)
    for item in links:
        assert isinstance(item, dict)

def test_get_configured_social_links_with_invalid_input():
    with pytest.raises(TypeError):
        get_configured_social_links("unexpected")  # type: ignore[arg-type]