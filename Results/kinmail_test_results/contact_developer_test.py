import os
import sys
import uuid
from datetime import datetime
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.contact_developer_message import ContactDeveloperMessage
from controllers.contact_developer_controller import (
    get_contact_developer_social_links,
    validate_contact_developer_payload,
    create_contact_developer_message,
)
from views.contact_developer_views import render_contact_developer_page

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

def _valid_payload():
    return {
        "name": f"Test User {uuid.uuid4().hex[:6]}",
        "email": _unique_email(),
        "message": "Hello developer, I need help with the app.",
    }

def _assert_route_exists(path: str, method: str):
    rules = list(app.url_map.iter_rules())
    matching = [r for r in rules if r.rule == path]
    assert matching, f"Route {path} is missing from app.url_map"
    assert any(method in r.methods for r in matching), f"Route {path} does not accept {method}"

class TestContactDeveloperMessageModel:
    def test_contactdevelopermessage_model_has_required_fields(self):
        cols = ContactDeveloperMessage.__table__.columns
        for field in ["id", "name", "email", "message", "created_at"]:
            assert field in cols, f"Missing required field '{field}' on ContactDeveloperMessage"

    def test_contactdevelopermessage_to_dict(self, app_context):
        msg = ContactDeveloperMessage(
            name="Alice",
            email=_unique_email(),
            message="Test message",
            created_at=datetime.utcnow(),
        )
        db.session.add(msg)
        db.session.commit()

        assert hasattr(msg, "to_dict") and callable(msg.to_dict)
        data = msg.to_dict()
        assert isinstance(data, dict)

        for key in ["id", "name", "email", "message", "created_at"]:
            assert key in data, f"to_dict() missing key '{key}'"

        assert data["id"] == msg.id
        assert data["name"] == msg.name
        assert data["email"] == msg.email
        assert data["message"] == msg.message

    def test_contactdevelopermessage_unique_constraints(self):
        constraints = list(ContactDeveloperMessage.__table__.constraints)
        unique_constraints = [c for c in constraints if c.__class__.__name__ == "UniqueConstraint"]
        assert unique_constraints == [], "No unique constraints should exist for ContactDeveloperMessage"

class TestContactDeveloperRoutes:
    def test_contact_developer_get_exists(self, client):
        _assert_route_exists("/contact-developer", "GET")
        resp = client.get("/contact-developer")
        assert resp.status_code != 404

    def test_contact_developer_get_renders_template(self, client):
        resp = client.get("/contact-developer")
        assert resp.status_code == 200
        assert b"<html" in resp.data.lower() or b"<!doctype html" in resp.data.lower()

    def test_contact_developer_post_exists(self, client):
        _assert_route_exists("/contact-developer", "POST")
        resp = client.post("/contact-developer", data={})
        assert resp.status_code != 404

    def test_contact_developer_post_success(self, client, app_context):
        payload = _valid_payload()
        resp = client.post("/contact-developer", data=payload, follow_redirects=False)

        assert resp.status_code in (200, 201, 302)

        created = ContactDeveloperMessage.query.filter_by(email=payload["email"]).first()
        assert created is not None, "Valid POST must persist a ContactDeveloperMessage"
        assert created.name == payload["name"]
        assert created.message == payload["message"]
        assert created.created_at is not None, "created_at must be set when message is created"

    def test_contact_developer_post_missing_required_fields(self, client, app_context):
        payload = _valid_payload()
        payload.pop("message")

        before = ContactDeveloperMessage.query.count()
        resp = client.post("/contact-developer", data=payload, follow_redirects=False)

        assert resp.status_code in (200, 400, 422)
        after = ContactDeveloperMessage.query.count()
        assert after == before, "Missing required fields must not create a message"

    def test_contact_developer_post_invalid_data(self, client, app_context):
        payload = _valid_payload()
        payload["email"] = "not-an-email"

        before = ContactDeveloperMessage.query.count()
        resp = client.post("/contact-developer", data=payload, follow_redirects=False)

        assert resp.status_code in (200, 400, 422)
        after = ContactDeveloperMessage.query.count()
        assert after == before, "Invalid payload must not create a message"

    def test_contact_developer_post_duplicate_data(self, client, app_context):
        payload = _valid_payload()

        first = client.post("/contact-developer", data=payload, follow_redirects=False)
        assert first.status_code in (200, 201, 302)

        second = client.post("/contact-developer", data=payload, follow_redirects=False)
        assert second.status_code in (200, 201, 302, 400, 409, 422)

        matches = ContactDeveloperMessage.query.filter_by(email=payload["email"], message=payload["message"]).all()
        assert len(matches) >= 1, "Duplicate submissions should not break persistence"

    def test_contact_developer_social_links_get_exists(self, client):
        _assert_route_exists("/contact-developer/social-links", "GET")
        resp = client.get("/contact-developer/social-links")
        assert resp.status_code != 404

    def test_contact_developer_social_links_get_renders_template(self, client):
        resp = client.get("/contact-developer/social-links")
        assert resp.status_code == 200
        content_type = (resp.headers.get("Content-Type") or "").lower()
        assert ("application/json" in content_type) or ("text/html" in content_type) or ("text/plain" in content_type)

class TestContactDeveloperHelpers:
    def test_get_contact_developer_social_links_function_exists(self):
        assert callable(get_contact_developer_social_links)

    def test_get_contact_developer_social_links_with_valid_input(self):
        links = get_contact_developer_social_links()
        assert isinstance(links, dict), "Social links must be returned as a dict"
        assert len(links) > 0, "Social media links must be available (non-empty dict)"
        for k, v in links.items():
            assert isinstance(k, str) and k.strip(), "Social link keys must be non-empty strings"
            assert isinstance(v, str) and v.strip(), "Social link values must be non-empty strings"

    def test_get_contact_developer_social_links_with_invalid_input(self):
        try:
            result = get_contact_developer_social_links(None)  # type: ignore[arg-type]
            assert isinstance(result, dict), "If invalid input is accepted, function must still return a dict"
        except TypeError:
            assert True

    def test_validate_contact_developer_payload_function_exists(self):
        assert callable(validate_contact_developer_payload)

    def test_validate_contact_developer_payload_with_valid_input(self):
        payload = _valid_payload()
        result = validate_contact_developer_payload(payload)
        assert isinstance(result, dict), "validate_contact_developer_payload must return a dict"
        assert result.get("is_valid") is True, "Valid payload must be marked is_valid=True"
        assert result.get("errors") in (None, [], {}), "Valid payload must have no errors"

    def test_validate_contact_developer_payload_with_invalid_input(self):
        payload = {"name": "", "email": "bad", "message": ""}
        result = validate_contact_developer_payload(payload)
        assert isinstance(result, dict), "validate_contact_developer_payload must return a dict"
        assert result.get("is_valid") is False, "Invalid payload must be marked is_valid=False"
        assert result.get("errors"), "Invalid payload must include errors"

    def test_create_contact_developer_message_function_exists(self):
        assert callable(create_contact_developer_message)

    def test_create_contact_developer_message_with_valid_input(self, app_context):
        name = "Bob"
        email = _unique_email()
        message = "Need assistance"

        msg = create_contact_developer_message(name, email, message)
        assert isinstance(msg, ContactDeveloperMessage), "Must return a ContactDeveloperMessage instance"
        assert msg.name == name
        assert msg.email == email
        assert msg.message == message
        assert msg.created_at is not None, "created_at must be set on creation"

        db.session.add(msg)
        db.session.commit()
        assert msg.id is not None, "Message must be persistable"

    def test_create_contact_developer_message_with_invalid_input(self, app_context):
        with pytest.raises((ValueError, TypeError, AssertionError)):
            create_contact_developer_message("", "bad-email", "")  # type: ignore[arg-type]

class TestContactDeveloperViews:
    def test_render_contact_developer_page_returns_str(self):
        links = {"github": "https://github.com/example"}
        html = render_contact_developer_page(links)
        assert isinstance(html, str)
        assert html.strip() != ""