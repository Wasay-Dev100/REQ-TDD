import os
import sys
import uuid
import inspect

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from controllers.user_login_controller import find_user_by_identifier, validate_login_credentials
from views.user_login_views import render_login_page

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

def _unique_identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_user_in_db(*, email: str, username: str, password: str, is_active: bool = True) -> User:
    user = User(email=email, username=username, password_hash="", is_active=is_active)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

def _route_methods_for_rule(rule_str: str):
    for r in app.url_map.iter_rules():
        if r.rule == rule_str:
            return set(r.methods or [])
    return set()

class TestUserModel:
    def test_user_model_has_required_fields(self):
        for field_name in ["id", "email", "username", "password_hash", "is_active"]:
            assert hasattr(User, field_name), f"Missing required field on User model: {field_name}"

    def test_user_set_password(self):
        user = User(email="a@example.com", username="a", password_hash="")
        user.set_password("password123")
        assert user.password_hash is not None
        assert isinstance(user.password_hash, str)
        assert user.password_hash != ""
        assert user.password_hash != "password123"

    def test_user_check_password(self):
        user = User(email="b@example.com", username="b", password_hash="")
        user.set_password("password123")
        assert user.check_password("password123") is True
        assert user.check_password("wrong") is False

    def test_user_unique_constraints(self, app_context):
        email = f"{_unique_identifier('email')}@example.com"
        username = _unique_identifier("user")
        _create_user_in_db(email=email, username=username, password="pw1")

        dup_email_user = User(email=email, username=_unique_identifier("user2"), password_hash="")
        dup_email_user.set_password("pw2")
        db.session.add(dup_email_user)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        dup_username_user = User(email=f"{_unique_identifier('email2')}@example.com", username=username, password_hash="")
        dup_username_user.set_password("pw3")
        db.session.add(dup_username_user)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

class TestLoginGetRoute:
    def test_login_get_exists(self):
        methods = _route_methods_for_rule("/login")
        assert "GET" in methods, "Expected /login route to accept GET"

    def test_login_get_renders_template(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"<html" in resp.data.lower() or b"login" in resp.data.lower()

class TestLoginPostRoute:
    def test_login_post_exists(self):
        methods = _route_methods_for_rule("/login")
        assert "POST" in methods, "Expected /login route to accept POST"

    def test_login_post_success(self, client, app_context):
        identifier = _unique_identifier("user")
        email = f"{_unique_identifier('email')}@example.com"
        password = "password123"
        user = _create_user_in_db(email=email, username=identifier, password=password)

        resp = client.post("/login", data={"identifier": identifier, "password": password})
        assert resp.status_code == 302
        assert resp.headers.get("Location", "").endswith("/")

        with client.session_transaction() as sess:
            assert sess.get("user_id") == user.id

    def test_login_post_missing_required_fields(self, client, app_context):
        resp1 = client.post("/login", data={"password": "x"})
        assert resp1.status_code == 200
        assert b"invalid" in resp1.data.lower()

        resp2 = client.post("/login", data={"identifier": "someone"})
        assert resp2.status_code == 200
        assert b"invalid" in resp2.data.lower()

        resp3 = client.post("/login", data={})
        assert resp3.status_code == 200
        assert b"invalid" in resp3.data.lower()

    def test_login_post_invalid_data(self, client, app_context):
        username = _unique_identifier("user")
        email = f"{_unique_identifier('email')}@example.com"
        _create_user_in_db(email=email, username=username, password="password123")

        too_long_identifier = "a" * 121
        resp1 = client.post("/login", data={"identifier": too_long_identifier, "password": "password123"})
        assert resp1.status_code == 200
        assert b"invalid" in resp1.data.lower()

        too_long_password = "p" * 257
        resp2 = client.post("/login", data={"identifier": username, "password": too_long_password})
        assert resp2.status_code == 200
        assert b"invalid" in resp2.data.lower()

        resp3 = client.post("/login", data={"identifier": "   ", "password": "password123"})
        assert resp3.status_code == 200
        assert b"invalid" in resp3.data.lower()

    def test_login_post_duplicate_data(self, client, app_context):
        username = _unique_identifier("user")
        email = f"{_unique_identifier('email')}@example.com"
        password = "password123"
        user = _create_user_in_db(email=email, username=username, password=password)

        resp = client.post("/login", data={"identifier": username, "password": password})
        assert resp.status_code == 302
        assert resp.headers.get("Location", "").endswith("/")

        with client.session_transaction() as sess:
            assert sess.get("user_id") == user.id

class TestLogoutPostRoute:
    def test_logout_post_exists(self):
        methods = _route_methods_for_rule("/logout")
        assert "POST" in methods, "Expected /logout route to accept POST"

    def test_logout_post_success(self, client, app_context):
        username = _unique_identifier("user")
        email = f"{_unique_identifier('email')}@example.com"
        password = "password123"
        _create_user_in_db(email=email, username=username, password=password)

        login_resp = client.post("/login", data={"identifier": username, "password": password})
        assert login_resp.status_code == 302

        with client.session_transaction() as sess:
            assert sess.get("user_id") is not None

        logout_resp = client.post("/logout", data={})
        assert logout_resp.status_code == 302
        assert logout_resp.headers.get("Location", "").endswith("/login")

        with client.session_transaction() as sess:
            assert sess.get("user_id") is None

    def test_logout_post_missing_required_fields(self, client, app_context):
        resp = client.post("/logout")
        assert resp.status_code == 302
        assert resp.headers.get("Location", "").endswith("/login")

    def test_logout_post_invalid_data(self, client, app_context):
        resp = client.post("/logout", data={"unexpected": "value"})
        assert resp.status_code == 302
        assert resp.headers.get("Location", "").endswith("/login")

    def test_logout_post_duplicate_data(self, client, app_context):
        resp = client.post("/logout", data={})
        assert resp.status_code == 302
        assert resp.headers.get("Location", "").endswith("/login")

class TestFindUserByIdentifierHelper:
    def test_find_user_by_identifier_function_exists(self):
        assert callable(find_user_by_identifier)
        sig = inspect.signature(find_user_by_identifier)
        assert list(sig.parameters.keys()) == ["identifier"]

    def test_find_user_by_identifier_with_valid_input(self, app_context):
        username = _unique_identifier("user")
        email = f"{_unique_identifier('email')}@example.com"
        password = "password123"
        user = _create_user_in_db(email=email, username=username, password=password)

        found_by_username = find_user_by_identifier(username)
        assert found_by_username is not None
        assert isinstance(found_by_username, User)
        assert found_by_username.id == user.id

        found_by_email = find_user_by_identifier(email)
        assert found_by_email is not None
        assert isinstance(found_by_email, User)
        assert found_by_email.id == user.id

    def test_find_user_by_identifier_with_invalid_input(self, app_context):
        assert find_user_by_identifier("") is None
        assert find_user_by_identifier("   ") is None
        assert find_user_by_identifier("a" * 121) is None
        assert find_user_by_identifier(_unique_identifier("missing")) is None

class TestValidateLoginCredentialsHelper:
    def test_validate_login_credentials_function_exists(self):
        assert callable(validate_login_credentials)
        sig = inspect.signature(validate_login_credentials)
        assert list(sig.parameters.keys()) == ["identifier", "password"]

    def test_validate_login_credentials_with_valid_input(self, app_context):
        username = _unique_identifier("user")
        email = f"{_unique_identifier('email')}@example.com"
        password = "password123"
        user = _create_user_in_db(email=email, username=username, password=password)

        ok1, msg1, u1 = validate_login_credentials(username, password)
        assert ok1 is True
        assert msg1 == ""
        assert isinstance(u1, User)
        assert u1.id == user.id

        ok2, msg2, u2 = validate_login_credentials(email, password)
        assert ok2 is True
        assert msg2 == ""
        assert isinstance(u2, User)
        assert u2.id == user.id

    def test_validate_login_credentials_with_invalid_input(self, app_context):
        username = _unique_identifier("user")
        email = f"{_unique_identifier('email')}@example.com"
        password = "password123"
        _create_user_in_db(email=email, username=username, password=password)

        ok1, msg1, u1 = validate_login_credentials(username, "wrong")
        assert ok1 is False
        assert msg1 == "Invalid username/email or password."
        assert u1 is None

        ok2, msg2, u2 = validate_login_credentials(_unique_identifier("missing"), "whatever")
        assert ok2 is False
        assert msg2 == "Invalid username/email or password."
        assert u2 is None

        ok3, msg3, u3 = validate_login_credentials("   ", "password123")
        assert ok3 is False
        assert msg3 == "Invalid username/email or password."
        assert u3 is None

        ok4, msg4, u4 = validate_login_credentials("a" * 121, "password123")
        assert ok4 is False
        assert msg4 == "Invalid username/email or password."
        assert u4 is None

        ok5, msg5, u5 = validate_login_credentials(username, "p" * 257)
        assert ok5 is False
        assert msg5 == "Invalid username/email or password."
        assert u5 is None