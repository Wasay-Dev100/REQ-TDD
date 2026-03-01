import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, mail  # noqa: E402
from models.user import User  # noqa: E402
from controllers.register_to_the_website_controller import (  # noqa: E402
    generate_email_verification_token,
    send_verification_email,
    hash_token,
)
from views.register_to_the_website_views import (  # noqa: E402
    render_register,
    render_verification_sent,
    render_verification_result,
)

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
    suffix = uuid.uuid4().hex[:10]
    return {
        "email": f"test_{suffix}@example.com",
        "username": f"testuser_{suffix}",
        "first_name": "John",
        "last_name": "Doe",
        "password": "StrongPassw0rd!",
    }

def _create_user_in_db(*, email=None, username=None, first_name="A", last_name="B", password="Passw0rd!"):
    if email is None or username is None:
        payload = _unique_user_payload()
        email = email or payload["email"]
        username = username or payload["username"]
        first_name = first_name or payload["first_name"]
        last_name = last_name or payload["last_name"]
        password = password or payload["password"]

    user = User(email=email, username=username, first_name=first_name, last_name=last_name, password_hash="")
    if not hasattr(user, "set_password") or not callable(getattr(user, "set_password")):
        raise AssertionError("User.set_password(password) must exist and be callable")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

class TestUserModel:
    def test_user_model_has_required_fields(self, app_context):
        required_fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "password_hash",
            "is_email_verified",
            "email_verification_token_hash",
            "email_verification_sent_at",
            "created_at",
            "updated_at",
        ]
        for field in required_fields:
            assert hasattr(User, field), f"Missing required User field: {field}"

    def test_user_set_password(self, app_context):
        user = User(
            email=f"pw_{uuid.uuid4().hex[:8]}@example.com",
            username=f"pw_{uuid.uuid4().hex[:8]}",
            first_name="A",
            last_name="B",
            password_hash="",
        )
        assert hasattr(user, "set_password") and callable(user.set_password)

        raw = "MyS3cretPass!"
        user.set_password(raw)

        assert user.password_hash
        assert user.password_hash != raw

    def test_user_check_password(self, app_context):
        user = User(
            email=f"cpw_{uuid.uuid4().hex[:8]}@example.com",
            username=f"cpw_{uuid.uuid4().hex[:8]}",
            first_name="A",
            last_name="B",
            password_hash="",
        )
        assert hasattr(user, "check_password") and callable(user.check_password)

        raw = "MyS3cretPass!"
        user.set_password(raw)

        assert user.check_password(raw) is True
        assert user.check_password("wrong-password") is False

    def test_user_set_email_verification_token(self, app_context):
        user = User(
            email=f"evt_{uuid.uuid4().hex[:8]}@example.com",
            username=f"evt_{uuid.uuid4().hex[:8]}",
            first_name="A",
            last_name="B",
            password_hash="",
        )
        assert hasattr(user, "set_email_verification_token") and callable(user.set_email_verification_token)

        raw_token = f"raw_{uuid.uuid4().hex}"
        user.set_email_verification_token(raw_token)

        assert user.email_verification_token_hash is not None
        assert user.email_verification_token_hash != raw_token
        assert user.email_verification_sent_at is not None

    def test_user_check_email_verification_token(self, app_context):
        user = User(
            email=f"cevt_{uuid.uuid4().hex[:8]}@example.com",
            username=f"cevt_{uuid.uuid4().hex[:8]}",
            first_name="A",
            last_name="B",
            password_hash="",
        )
        assert hasattr(user, "check_email_verification_token") and callable(user.check_email_verification_token)

        raw_token = f"raw_{uuid.uuid4().hex}"
        user.set_email_verification_token(raw_token)

        assert user.check_email_verification_token(raw_token) is True
        assert user.check_email_verification_token(f"raw_{uuid.uuid4().hex}") is False

    def test_user_mark_email_verified(self, app_context):
        user = User(
            email=f"mev_{uuid.uuid4().hex[:8]}@example.com",
            username=f"mev_{uuid.uuid4().hex[:8]}",
            first_name="A",
            last_name="B",
            password_hash="",
        )
        assert hasattr(user, "mark_email_verified") and callable(user.mark_email_verified)

        user.is_email_verified = False
        user.set_email_verification_token(f"raw_{uuid.uuid4().hex}")
        user.mark_email_verified()

        assert user.is_email_verified is True
        assert user.email_verification_token_hash in (None, "")
        assert user.email_verification_sent_at is None

    def test_user_unique_constraints(self, app_context):
        email = f"uniq_{uuid.uuid4().hex[:8]}@example.com"
        username = f"uniq_{uuid.uuid4().hex[:8]}"

        u1 = User(email=email, username=username, first_name="A", last_name="B", password_hash="")
        u1.set_password("Passw0rd!")
        db.session.add(u1)
        db.session.commit()

        u2 = User(email=email, username=f"other_{uuid.uuid4().hex[:8]}", first_name="A", last_name="B", password_hash="")
        u2.set_password("Passw0rd!")
        db.session.add(u2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

        u3 = User(email=f"other_{uuid.uuid4().hex[:8]}@example.com", username=username, first_name="A", last_name="B", password_hash="")
        u3.set_password("Passw0rd!")
        db.session.add(u3)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

class TestRegisterRoutes:
    def test_register_get_exists(self, client):
        resp = client.get("/register")
        assert resp.status_code != 404

    def test_register_get_renders_template(self, client):
        resp = client.get("/register")
        assert resp.status_code == 200
        assert resp.mimetype in ("text/html", "application/xhtml+xml", "text/plain")

    def test_register_post_exists(self, client):
        with patch("app.mail.send"):
            resp = client.post("/register", data={})
        assert resp.status_code != 404

    def test_register_post_success(self, client):
        payload = _unique_user_payload()
        with patch("app.mail.send") as mock_send:
            resp = client.post(
                "/register",
                data={
                    "email": payload["email"],
                    "username": payload["username"],
                    "first_name": payload["first_name"],
                    "last_name": payload["last_name"],
                    "password": payload["password"],
                },
                follow_redirects=False,
            )

        assert resp.status_code in (200, 302)
        user = User.query.filter_by(email=payload["email"]).first()
        assert user is not None
        assert user.username == payload["username"]
        assert user.is_email_verified is False
        assert user.email_verification_token_hash is not None
        assert user.email_verification_sent_at is not None
        assert mock_send.call_count in (0, 1)

    def test_register_post_missing_required_fields(self, client):
        payload = _unique_user_payload()
        with patch("app.mail.send") as mock_send:
            resp = client.post(
                "/register",
                data={
                    "email": payload["email"],
                    "username": payload["username"],
                },
                follow_redirects=True,
            )

        assert resp.status_code == 200
        user = User.query.filter_by(email=payload["email"]).first()
        assert user is None
        assert mock_send.call_count == 0

    def test_register_post_invalid_data(self, client):
        suffix = uuid.uuid4().hex[:10]
        with patch("app.mail.send") as mock_send:
            resp = client.post(
                "/register",
                data={
                    "email": f"not-an-email-{suffix}",
                    "username": f"u_{suffix}",
                    "first_name": "John",
                    "last_name": "Doe",
                    "password": "StrongPassw0rd!",
                },
                follow_redirects=True,
            )

        assert resp.status_code == 200
        user = User.query.filter_by(username=f"u_{suffix}").first()
        assert user is None
        assert mock_send.call_count == 0

    def test_register_post_duplicate_data(self, client):
        existing = _unique_user_payload()
        with app.app_context():
            _create_user_in_db(email=existing["email"], username=existing["username"], password=existing["password"])

        new_payload = _unique_user_payload()
        with patch("app.mail.send") as mock_send:
            resp = client.post(
                "/register",
                data={
                    "email": existing["email"],
                    "username": new_payload["username"],
                    "first_name": "John",
                    "last_name": "Doe",
                    "password": "StrongPassw0rd!",
                },
                follow_redirects=True,
            )

        assert resp.status_code == 200
        assert User.query.filter_by(email=existing["email"]).count() == 1
        assert mock_send.call_count == 0

class TestVerifyEmailRoute:
    def test_verify_email_get_exists(self, client):
        resp = client.get("/verify-email")
        assert resp.status_code != 404

    def test_verify_email_get_renders_template(self, client):
        resp = client.get("/verify-email")
        assert resp.status_code == 200
        assert resp.mimetype in ("text/html", "application/xhtml+xml", "text/plain")

class TestHelpers:
    def test_generate_email_verification_token_function_exists(self):
        assert callable(generate_email_verification_token)

    def test_generate_email_verification_token_with_valid_input(self, app_context):
        user = User(
            email=f"tok_{uuid.uuid4().hex[:8]}@example.com",
            username=f"tok_{uuid.uuid4().hex[:8]}",
            first_name="A",
            last_name="B",
            password_hash="",
        )
        user.set_password("Passw0rd!")
        db.session.add(user)
        db.session.commit()

        raw = generate_email_verification_token(user.id)
        assert isinstance(raw, str)
        assert raw.strip() != ""

    def test_generate_email_verification_token_with_invalid_input(self, app_context):
        with pytest.raises(Exception):
            generate_email_verification_token(None)

    def test_send_verification_email_function_exists(self):
        assert callable(send_verification_email)

    def test_send_verification_email_with_valid_input(self, app_context):
        user = User(
            email=f"send_{uuid.uuid4().hex[:8]}@example.com",
            username=f"send_{uuid.uuid4().hex[:8]}",
            first_name="A",
            last_name="B",
            password_hash="",
        )
        user.set_password("Passw0rd!")
        db.session.add(user)
        db.session.commit()

        raw_token = f"raw_{uuid.uuid4().hex}"
        with patch("app.mail.send") as mock_send:
            send_verification_email(user, raw_token)
            assert mock_send.call_count == 1

    def test_send_verification_email_with_invalid_input(self, app_context):
        with patch("app.mail.send") as mock_send:
            with pytest.raises(Exception):
                send_verification_email(None, f"raw_{uuid.uuid4().hex}")
            assert mock_send.call_count == 0

    def test_hash_token_function_exists(self):
        assert callable(hash_token)

    def test_hash_token_with_valid_input(self):
        raw = f"raw_{uuid.uuid4().hex}"
        hashed = hash_token(raw)
        assert isinstance(hashed, str)
        assert hashed.strip() != ""
        assert hashed != raw

    def test_hash_token_with_invalid_input(self):
        with pytest.raises(Exception):
            hash_token(None)