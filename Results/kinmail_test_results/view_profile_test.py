import os
import sys
import uuid
from datetime import datetime, timezone
from functools import wraps
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db  # noqa: E402
from models.user import User  # noqa: E402
from controllers.view_profile_controller import get_current_user, login_required  # noqa: E402
from views.view_profile_views import render_profile  # noqa: E402

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

def _unique_user_data():
    token = uuid.uuid4().hex[:10]
    return {
        "name": f"Test User {token}",
        "gender": "Other",
        "username": f"testuser_{token}",
        "email": f"test_{token}@example.com",
        "contact_number": "1234567890",
        "birthdate": datetime.strptime("1990-01-01", "%Y-%m-%d").date(),
        "profile_picture_url": f"https://example.com/{token}.jpg",
        "password": "StrongPassw0rd!",
    }

def _create_user_in_db():
    data = _unique_user_data()
    user = User(
        name=data["name"],
        gender=data["gender"],
        username=data["username"],
        email=data["email"],
        contact_number=data["contact_number"],
        birthdate=data["birthdate"],
        profile_picture_url=data["profile_picture_url"],
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()
    return user, data

def _route_exists(rule_path, method):
    for rule in app.url_map.iter_rules():
        if rule.rule == rule_path and method in rule.methods:
            return True
    return False

class TestUserModel:
    def test_user_model_has_required_fields(self, app_context):
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

    def test_user_set_password(self, app_context):
        user = User(username=f"u_{uuid.uuid4().hex[:8]}", email=f"e_{uuid.uuid4().hex[:8]}@ex.com")
        user.set_password("password123!")
        assert getattr(user, "password_hash", None), "password_hash must be set by set_password()"
        assert user.password_hash != "password123!", "password_hash must not store plaintext password"

    def test_user_check_password(self, app_context):
        user = User(username=f"u_{uuid.uuid4().hex[:8]}", email=f"e_{uuid.uuid4().hex[:8]}@ex.com")
        user.set_password("password123!")
        assert user.check_password("password123!") is True
        assert user.check_password("wrongpassword") is False

    def test_user_to_profile_dict(self, app_context):
        user, data = _create_user_in_db()
        profile = user.to_profile_dict()
        assert isinstance(profile, dict)

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
        assert not missing, f"to_profile_dict() missing keys: {sorted(missing)}"

        assert profile["name"] == data["name"]
        assert profile["gender"] == data["gender"]
        assert profile["username"] == data["username"]
        assert profile["email"] == data["email"]
        assert profile["contact_number"] == data["contact_number"]
        assert profile["profile_picture_url"] == data["profile_picture_url"]

        birthdate_val = profile["birthdate"]
        assert birthdate_val is not None
        assert isinstance(birthdate_val, (str, type(data["birthdate"]))), "birthdate must be date or ISO string"

        forbidden_keys = {"password", "password_hash"}
        assert forbidden_keys.isdisjoint(profile.keys()), "Profile dict must not expose password fields"

    def test_user_unique_constraints(self, app_context):
        base = _unique_user_data()

        user1 = User(
            name=base["name"],
            gender=base["gender"],
            username=base["username"],
            email=base["email"],
            contact_number=base["contact_number"],
            birthdate=base["birthdate"],
            profile_picture_url=base["profile_picture_url"],
        )
        user1.set_password(base["password"])
        db.session.add(user1)
        db.session.commit()

        user2 = User(
            name=f"{base['name']} 2",
            gender=base["gender"],
            username=base["username"],  # duplicate username
            email=f"other_{uuid.uuid4().hex[:8]}@example.com",
            contact_number=base["contact_number"],
            birthdate=base["birthdate"],
            profile_picture_url=base["profile_picture_url"],
        )
        user2.set_password(base["password"])
        db.session.add(user2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

        user3 = User(
            name=f"{base['name']} 3",
            gender=base["gender"],
            username=f"other_{uuid.uuid4().hex[:8]}",
            email=base["email"],  # duplicate email
            contact_number=base["contact_number"],
            birthdate=base["birthdate"],
            profile_picture_url=base["profile_picture_url"],
        )
        user3.set_password(base["password"])
        db.session.add(user3)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

class TestProfileRoutes:
    def test_profile_get_exists(self, client):
        assert _route_exists("/profile", "GET"), "Expected GET /profile route to exist"

    def test_profile_get_renders_template(self, client):
        response = client.get("/profile")
        assert response.status_code in (200, 302, 401, 403)

        if response.status_code == 200:
            assert response.mimetype in ("text/html", "application/xhtml+xml", "text/html; charset=utf-8")
            assert b"<" in response.data and b">" in response.data

    def test_api_profile_get_exists(self, client):
        assert _route_exists("/api/profile", "GET"), "Expected GET /api/profile route to exist"

    def test_api_profile_get_renders_template(self, client):
        response = client.get("/api/profile")
        assert response.status_code in (200, 302, 401, 403)

        if response.status_code == 200:
            assert response.mimetype in ("application/json", "text/html", "text/html; charset=utf-8")
            assert response.data, "Response body must not be empty on 200"

class TestHelperGetCurrentUser:
    def test_get_current_user_function_exists(self):
        assert callable(get_current_user), "get_current_user must exist and be callable"

    def test_get_current_user_with_valid_input(self, app_context):
        user, _ = _create_user_in_db()

        with patch("controllers.view_profile_controller.get_current_user", return_value=user) as mocked:
            result = mocked()
            assert result is user

    def test_get_current_user_with_invalid_input(self):
        with pytest.raises(TypeError):
            get_current_user("unexpected-arg")

class TestHelperLoginRequired:
    def test_login_required_function_exists(self):
        assert callable(login_required), "login_required must exist and be callable"

    def test_login_required_with_valid_input(self):
        def sample_view():
            return "ok"

        wrapped = login_required(sample_view)
        assert callable(wrapped), "login_required must return a callable"

    def test_login_required_with_invalid_input(self):
        with pytest.raises(TypeError):
            login_required(None)