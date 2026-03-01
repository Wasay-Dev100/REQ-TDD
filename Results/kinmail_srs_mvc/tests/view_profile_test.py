import os
import sys
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from controllers.view_profile_controller import get_current_user, login_required
from views.view_profile_views import render_profile_page

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

def _unique_user_payload():
    token = uuid.uuid4().hex[:10]
    birthdate = datetime.strptime("1990-01-01", "%Y-%m-%d").date()
    return {
        "name": f"Test Name {token}",
        "gender": "Other",
        "username": f"testuser_{token}",
        "email": f"test_{token}@example.com",
        "contact_number": "1234567890",
        "birthdate": birthdate,
        "profile_picture_url": f"https://example.com/{token}.png",
        "password": f"Passw0rd!{token}",
    }

def _create_user_in_db(payload):
    user = User(
        name=payload["name"],
        gender=payload["gender"],
        username=payload["username"],
        email=payload["email"],
        contact_number=payload["contact_number"],
        birthdate=payload["birthdate"],
        profile_picture_url=payload["profile_picture_url"],
    )
    user.set_password(payload["password"])
    db.session.add(user)
    db.session.commit()
    return user

def test_user_model_has_required_fields(app_context):
    required_fields = [
        "id",
        "name",
        "gender",
        "username",
        "email",
        "contact_number",
        "birthdate",
        "profile_picture_url",
        "password_hash",
        "created_at",
        "updated_at",
    ]
    for field in required_fields:
        assert hasattr(User, field), f"Missing required field on User model: {field}"

def test_user_set_password(app_context):
    payload = _unique_user_payload()
    user = User(
        name=payload["name"],
        gender=payload["gender"],
        username=payload["username"],
        email=payload["email"],
        contact_number=payload["contact_number"],
        birthdate=payload["birthdate"],
        profile_picture_url=payload["profile_picture_url"],
    )
    assert getattr(user, "password_hash", None) in (None, "",), "password_hash should not be pre-populated"
    user.set_password(payload["password"])
    assert user.password_hash, "set_password must set a non-empty password_hash"
    assert user.password_hash != payload["password"], "password_hash must not store the raw password"

def test_user_check_password(app_context):
    payload = _unique_user_payload()
    user = User(
        name=payload["name"],
        gender=payload["gender"],
        username=payload["username"],
        email=payload["email"],
        contact_number=payload["contact_number"],
        birthdate=payload["birthdate"],
        profile_picture_url=payload["profile_picture_url"],
    )
    user.set_password(payload["password"])
    assert user.check_password(payload["password"]) is True
    assert user.check_password(payload["password"] + "_wrong") is False

def test_user_to_profile_dict(app_context):
    payload = _unique_user_payload()
    user = User(
        name=payload["name"],
        gender=payload["gender"],
        username=payload["username"],
        email=payload["email"],
        contact_number=payload["contact_number"],
        birthdate=payload["birthdate"],
        profile_picture_url=payload["profile_picture_url"],
    )
    user.set_password(payload["password"])

    profile = user.to_profile_dict()
    assert isinstance(profile, dict), "to_profile_dict must return a dict"

    expected_keys = {
        "name",
        "gender",
        "username",
        "email",
        "contact_number",
        "birthdate",
        "profile_picture_url",
    }
    missing = expected_keys - set(profile.keys())
    assert not missing, f"to_profile_dict missing keys: {sorted(missing)}"

    assert profile["name"] == payload["name"]
    assert profile["gender"] == payload["gender"]
    assert profile["username"] == payload["username"]
    assert profile["email"] == payload["email"]
    assert profile["contact_number"] == payload["contact_number"]
    assert profile["profile_picture_url"] == payload["profile_picture_url"]

    assert "password" not in profile
    assert "password_hash" not in profile

def test_user_unique_constraints(app_context):
    payload = _unique_user_payload()
    _create_user_in_db(payload)

    payload2 = _unique_user_payload()
    user_dup_username = User(
        name=payload2["name"],
        gender=payload2["gender"],
        username=payload["username"],
        email=payload2["email"],
        contact_number=payload2["contact_number"],
        birthdate=payload2["birthdate"],
        profile_picture_url=payload2["profile_picture_url"],
    )
    user_dup_username.set_password(payload2["password"])
    db.session.add(user_dup_username)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    payload3 = _unique_user_payload()
    user_dup_email = User(
        name=payload3["name"],
        gender=payload3["gender"],
        username=payload3["username"],
        email=payload["email"],
        contact_number=payload3["contact_number"],
        birthdate=payload3["birthdate"],
        profile_picture_url=payload3["profile_picture_url"],
    )
    user_dup_email.set_password(payload3["password"])
    db.session.add(user_dup_email)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

def test_profile_get_exists(client):
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/profile" in rules, "Route /profile must exist"

    response = client.get("/profile")
    assert response.status_code != 405, "/profile must accept GET (not return 405)"

def test_profile_get_renders_template(client):
    response = client.get("/profile")
    assert response.status_code in (200, 302, 401, 403), "Unexpected status code for /profile GET"
    if response.status_code == 200:
        assert response.mimetype in ("text/html", "application/xhtml+xml"), "Profile page should render HTML"

def test_api_profile_get_exists(client):
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/api/profile" in rules, "Route /api/profile must exist"

    response = client.get("/api/profile")
    assert response.status_code != 405, "/api/profile must accept GET (not return 405)"

def test_api_profile_get_renders_template(client):
    response = client.get("/api/profile")
    assert response.status_code in (200, 302, 401, 403), "Unexpected status code for /api/profile GET"
    if response.status_code == 200:
        assert response.mimetype in ("application/json", "text/html"), "API profile should return JSON (preferred) or HTML"

def test_get_current_user_function_exists():
    assert callable(get_current_user), "get_current_user must exist and be callable"

def test_get_current_user_with_valid_input(app_context):
    payload = _unique_user_payload()
    user = _create_user_in_db(payload)

    session = {"user_id": user.id}
    result = get_current_user(session)
    assert result is not None, "get_current_user should return a User for a valid session"
    assert isinstance(result, User), "get_current_user must return a User instance"
    assert result.id == user.id

def test_get_current_user_with_invalid_input(app_context):
    result_none = get_current_user(None)
    assert result_none is None, "get_current_user should return None for invalid session input"

    result_empty = get_current_user({})
    assert result_empty is None, "get_current_user should return None when session has no user_id"

    result_bad = get_current_user({"user_id": -999999})
    assert result_bad is None, "get_current_user should return None when user_id does not exist"

def test_login_required_function_exists():
    assert callable(login_required), "login_required must exist and be callable"

def test_login_required_with_valid_input(client):
    @login_required
    def protected_view():
        return "ok"

    payload = _unique_user_payload()
    with app.app_context():
        user = _create_user_in_db(payload)

    with client.session_transaction() as sess:
        sess["user_id"] = user.id

    with app.test_request_context("/profile"):
        result = protected_view()
        assert result == "ok", "login_required should allow access when user is authenticated"

def test_login_required_with_invalid_input(client):
    @login_required
    def protected_view():
        return "ok"

    with client.session_transaction() as sess:
        sess.pop("user_id", None)

    with app.test_request_context("/profile"):
        result = protected_view()
        assert result != "ok", "login_required should not allow access when user is not authenticated"

def test_render_profile_page_function_exists():
    assert callable(render_profile_page), "render_profile_page must exist and be callable"

def test_render_profile_page_returns_str(app_context):
    payload = _unique_user_payload()
    user = User(
        name=payload["name"],
        gender=payload["gender"],
        username=payload["username"],
        email=payload["email"],
        contact_number=payload["contact_number"],
        birthdate=payload["birthdate"],
        profile_picture_url=payload["profile_picture_url"],
    )
    html = render_profile_page(user)
    assert isinstance(html, str), "render_profile_page must return a string"