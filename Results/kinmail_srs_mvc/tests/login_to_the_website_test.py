import os
import sys
import uuid
import inspect
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from controllers.login_controller import (
    authenticate_user,
    login_user_session,
    logout_user_session,
)
from views.login_views import render_login

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

def _create_user_in_db(*, username=None, email=None, password="Password123!", is_active=True):
    if username is None:
        username = _unique("user")
    if email is None:
        email = f"{_unique('email')}@example.com"
    user = User(username=username, email=email, is_active=is_active)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

# -------------------------
# MODEL: User (models/user.py)
# -------------------------

def test_user_model_has_required_fields(app_context):
    required_fields = ["id", "email", "username", "password_hash", "is_active", "created_at"]
    for field in required_fields:
        assert hasattr(User, field), f"Missing required field on User model: {field}"

def test_user_set_password(app_context):
    user = User(username=_unique("u"), email=f"{_unique('e')}@example.com")
    user.set_password("MySecretPass123!")
    assert user.password_hash is not None
    assert isinstance(user.password_hash, str)
    assert user.password_hash != ""
    assert user.password_hash != "MySecretPass123!"

def test_user_check_password(app_context):
    user = User(username=_unique("u"), email=f"{_unique('e')}@example.com")
    user.set_password("CorrectHorseBatteryStaple1!")
    assert user.check_password("CorrectHorseBatteryStaple1!") is True
    assert user.check_password("wrong-password") is False

def test_user_unique_constraints(app_context):
    username = _unique("dupuser")
    email = f"{_unique('dupemail')}@example.com"

    u1 = User(username=username, email=email)
    u1.set_password("Password123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(username=username, email=f"{_unique('other')}@example.com")
    u2.set_password("Password123!")
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = User(username=_unique("otheruser"), email=email)
    u3.set_password("Password123!")
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# -------------------------
# VIEW: render_login (views/login_views.py)
# -------------------------

def test_render_login_function_exists():
    assert callable(render_login), "render_login must exist and be callable"
    sig = inspect.signature(render_login)
    assert "error" in sig.parameters
    assert "identifier" in sig.parameters

def test_render_login_renders_string():
    html = render_login(error=None, identifier=None)
    assert isinstance(html, str)
    assert len(html) > 0

# -------------------------
# ROUTE: /login (GET) - login_get
# -------------------------

def test_login_get_exists(client):
    response = client.get("/login")
    assert response.status_code != 404

def test_login_get_renders_template(client):
    response = client.get("/login")
    assert response.status_code == 200
    content_type = response.headers.get("Content-Type", "")
    assert "text/html" in content_type or "charset" in content_type or content_type != ""

# -------------------------
# ROUTE: /login (POST) - login_post
# -------------------------

def test_login_post_exists(client):
    response = client.post("/login", data={})
    assert response.status_code != 404

def test_login_post_success(client):
    with app.app_context():
        password = "ValidPass123!"
        user = _create_user_in_db(password=password, is_active=True)

    response = client.post(
        "/login",
        data={"identifier": user.username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code in (200, 302)

    with client.session_transaction() as sess:
        flashes = sess.get("_flashes", [])
        assert not any("invalid" in str(msg).lower() for _, msg in flashes)

def test_login_post_missing_required_fields(client):
    response = client.post("/login", data={"identifier": ""}, follow_redirects=True)
    assert response.status_code == 200
    body = response.data.lower()
    assert b"error" in body or b"invalid" in body or b"required" in body

def test_login_post_invalid_data(client):
    response = client.post(
        "/login",
        data={"identifier": "not_a_user@example.com", "password": "wrong"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = response.data.lower()
    assert b"invalid" in body or b"error" in body

def test_login_post_duplicate_data(client):
    with app.app_context():
        password = "ValidPass123!"
        user = _create_user_in_db(password=password, is_active=True)

    response = client.post(
        "/login",
        data={"identifier": user.username, "password": password, "identifier_duplicate": user.username},
        follow_redirects=False,
    )
    assert response.status_code != 404

# -------------------------
# ROUTE: /logout (POST) - logout_post
# -------------------------

def test_logout_post_exists(client):
    response = client.post("/logout", data={})
    assert response.status_code != 404

def test_logout_post_success(client):
    with app.app_context():
        password = "ValidPass123!"
        user = _create_user_in_db(password=password, is_active=True)

    client.post("/login", data={"identifier": user.username, "password": password}, follow_redirects=False)
    response = client.post("/logout", data={}, follow_redirects=False)
    assert response.status_code in (200, 302)

def test_logout_post_missing_required_fields(client):
    response = client.post("/logout", data={}, follow_redirects=False)
    assert response.status_code in (200, 302)

def test_logout_post_invalid_data(client):
    response = client.post("/logout", data={"unexpected": "field"}, follow_redirects=False)
    assert response.status_code in (200, 302)

def test_logout_post_duplicate_data(client):
    response = client.post("/logout", data={"logout": "1", "logout": "1"}, follow_redirects=False)
    assert response.status_code in (200, 302)

# -------------------------
# HELPER: authenticate_user(identifier: str, password: str)
# -------------------------

def test_authenticate_user_function_exists():
    assert callable(authenticate_user), "authenticate_user must exist and be callable"
    sig = inspect.signature(authenticate_user)
    assert list(sig.parameters.keys()) == ["identifier", "password"]

def test_authenticate_user_with_valid_input(app_context):
    password = "ValidPass123!"
    user = _create_user_in_db(password=password, is_active=True)

    authed = authenticate_user(user.username, password)
    assert authed is not None
    assert isinstance(authed, User)
    assert authed.id == user.id

def test_authenticate_user_with_invalid_input(app_context):
    password = "ValidPass123!"
    user = _create_user_in_db(password=password, is_active=True)

    assert authenticate_user(user.username, "wrong") is None
    assert authenticate_user("nonexistent_user", "whatever") is None
    assert authenticate_user("", "") is None
    assert authenticate_user("   ", "   ") is None

# -------------------------
# HELPER: login_user_session(user: User)
# -------------------------

def test_login_user_session_function_exists():
    assert callable(login_user_session), "login_user_session must exist and be callable"
    sig = inspect.signature(login_user_session)
    assert list(sig.parameters.keys()) == ["user"]

def test_login_user_session_with_valid_input(app_context):
    user = _create_user_in_db(password="ValidPass123!", is_active=True)

    with app.test_request_context("/login", method="POST"):
        login_user_session(user)

def test_login_user_session_with_invalid_input(app_context):
    with app.test_request_context("/login", method="POST"):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            login_user_session(None)

# -------------------------
# HELPER: logout_user_session()
# -------------------------

def test_logout_user_session_function_exists():
    assert callable(logout_user_session), "logout_user_session must exist and be callable"
    sig = inspect.signature(logout_user_session)
    assert len(sig.parameters) == 0

def test_logout_user_session_with_valid_input(app_context):
    with app.test_request_context("/logout", method="POST"):
        logout_user_session()

def test_logout_user_session_with_invalid_input(app_context):
    with app.test_request_context("/logout", method="POST"):
        with pytest.raises(TypeError):
            logout_user_session("unexpected")