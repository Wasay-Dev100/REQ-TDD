import os
import sys
import uuid
import re
from datetime import datetime, timedelta

import pytest
from unittest.mock import patch
from io import BytesIO
from werkzeug.datastructures import FileStorage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, mail
from models.user import User
from models.user_registration_email_verification_token import EmailVerificationToken
from controllers.user_registration_controller import (
    validate_registration_payload,
    create_email_verification_token,
    send_verification_email,
    save_profile_picture,
)
from views.user_registration_views import (
    render_register,
    render_verification_sent,
    render_verification_result,
)

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = "/tmp/test_uploads"

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()

@pytest.fixture
def app_context():
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = "/tmp/test_uploads"

    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()

def _unique_username(prefix="testuser"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _unique_email(prefix="test"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}@example.com"

def _valid_register_form(username=None, email=None):
    return {
        "first_name": "John",
        "middle_name": "Q",
        "last_name": "Public",
        "gender": "male",
        "contact_number": "+1 (555) 123-4567",
        "birthdate": "1990-01-01",
        "username": username or _unique_username(),
        "email": email or _unique_email(),
        "password": "Password123!",
    }

def _valid_image_filestorage():
    return FileStorage(
        stream=BytesIO(b"\x89PNG\r\n\x1a\nfakepngdata"),
        filename="avatar.png",
        content_type="image/png",
    )

def _create_user_in_db(
    *,
    username=None,
    email=None,
    password="Password123!",
    is_email_verified=False,
):
    birthdate = datetime.strptime("1990-01-01", "%Y-%m-%d").date()
    user = User(
        first_name="Jane",
        middle_name=None,
        last_name="Doe",
        gender="female",
        profile_picture=None,
        contact_number="+15551234567",
        birthdate=birthdate,
        username=username or _unique_username("existing"),
        email=email or _unique_email("existing"),
        password_hash="",
        is_email_verified=is_email_verified,
        email_verified_at=None,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

def _create_token_in_db(user, *, token=None, expires_at=None, used_at=None):
    tok = EmailVerificationToken(
        user_id=user.id,
        token=token or ("t" * 32 + uuid.uuid4().hex),
        expires_at=expires_at or (datetime.utcnow() + timedelta(days=1)),
        used_at=used_at,
    )
    db.session.add(tok)
    db.session.commit()
    return tok

# MODEL: User (models/user.py)
def test_user_model_has_required_fields():
    required = [
        "id",
        "first_name",
        "middle_name",
        "last_name",
        "gender",
        "profile_picture",
        "contact_number",
        "birthdate",
        "username",
        "email",
        "password_hash",
        "is_email_verified",
        "email_verified_at",
        "created_at",
        "updated_at",
    ]
    for field in required:
        assert hasattr(User, field), f"Missing required User field: {field}"

def test_user_set_password():
    user = User(
        first_name="A",
        middle_name=None,
        last_name="B",
        gender="other",
        profile_picture=None,
        contact_number="+15551234567",
        birthdate=datetime.strptime("1990-01-01", "%Y-%m-%d").date(),
        username=_unique_username(),
        email=_unique_email(),
        password_hash="",
        is_email_verified=False,
        email_verified_at=None,
    )
    user.set_password("Password123!")
    assert isinstance(user.password_hash, str)
    assert user.password_hash
    assert "Password123!" not in user.password_hash

def test_user_check_password():
    user = User(
        first_name="A",
        middle_name=None,
        last_name="B",
        gender="other",
        profile_picture=None,
        contact_number="+15551234567",
        birthdate=datetime.strptime("1990-01-01", "%Y-%m-%d").date(),
        username=_unique_username(),
        email=_unique_email(),
        password_hash="",
        is_email_verified=False,
        email_verified_at=None,
    )
    user.set_password("Password123!")
    assert user.check_password("Password123!") is True
    assert user.check_password("WrongPassword!") is False

def test_user_unique_constraints(app_context):
    username = _unique_username("uniq")
    email = _unique_email("uniq")

    _create_user_in_db(username=username, email=email)

    birthdate = datetime.strptime("1990-01-01", "%Y-%m-%d").date()
    user2 = User(
        first_name="X",
        middle_name=None,
        last_name="Y",
        gender="male",
        profile_picture=None,
        contact_number="+15551230000",
        birthdate=birthdate,
        username=username,
        email=_unique_email("other"),
        password_hash="",
        is_email_verified=False,
        email_verified_at=None,
    )
    user2.set_password("Password123!")
    db.session.add(user2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    user3 = User(
        first_name="X",
        middle_name=None,
        last_name="Y",
        gender="male",
        profile_picture=None,
        contact_number="+15551230001",
        birthdate=birthdate,
        username=_unique_username("other"),
        email=email,
        password_hash="",
        is_email_verified=False,
        email_verified_at=None,
    )
    user3.set_password("Password123!")
    db.session.add(user3)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# MODEL: EmailVerificationToken (models/user_registration_email_verification_token.py)
def test_emailverificationtoken_model_has_required_fields():
    required = ["id", "user_id", "token", "expires_at", "used_at", "created_at"]
    for field in required:
        assert hasattr(EmailVerificationToken, field), f"Missing required EmailVerificationToken field: {field}"

def test_emailverificationtoken_is_expired():
    tok = EmailVerificationToken(
        user_id=1,
        token="t" * 32,
        expires_at=datetime.utcnow() - timedelta(seconds=1),
        used_at=None,
    )
    assert tok.is_expired() is True

    tok2 = EmailVerificationToken(
        user_id=1,
        token="u" * 32,
        expires_at=datetime.utcnow() + timedelta(days=1),
        used_at=None,
    )
    assert tok2.is_expired() is False

def test_emailverificationtoken_is_used():
    tok = EmailVerificationToken(
        user_id=1,
        token="t" * 32,
        expires_at=datetime.utcnow() + timedelta(days=1),
        used_at=None,
    )
    assert tok.is_used() is False

    tok2 = EmailVerificationToken(
        user_id=1,
        token="u" * 32,
        expires_at=datetime.utcnow() + timedelta(days=1),
        used_at=datetime.utcnow(),
    )
    assert tok2.is_used() is True

def test_emailverificationtoken_mark_used():
    tok = EmailVerificationToken(
        user_id=1,
        token="t" * 32,
        expires_at=datetime.utcnow() + timedelta(days=1),
        used_at=None,
    )
    assert tok.used_at is None
    tok.mark_used()
    assert tok.used_at is not None
    assert isinstance(tok.used_at, datetime)

def test_emailverificationtoken_unique_constraints(app_context):
    user = _create_user_in_db()
    token_value = "tok_" + uuid.uuid4().hex + ("x" * 20)

    _create_token_in_db(user, token=token_value)

    tok2 = EmailVerificationToken(
        user_id=user.id,
        token=token_value,
        expires_at=datetime.utcnow() + timedelta(days=1),
        used_at=None,
    )
    db.session.add(tok2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# ROUTE: /register (GET) - register_get
def test_register_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/register"]
    assert rules, "Route /register is missing"
    methods = set()
    for r in rules:
        methods |= set(r.methods or [])
    assert "GET" in methods, "/register must accept GET"

def test_register_get_renders_template(client):
    resp = client.get("/register")
    assert resp.status_code == 200
    assert b"register" in resp.data.lower()

# ROUTE: /register (POST) - register_post
def test_register_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/register"]
    assert rules, "Route /register is missing"
    methods = set()
    for r in rules:
        methods |= set(r.methods or [])
    assert "POST" in methods, "/register must accept POST"

def test_register_post_success(client):
    form = _valid_register_form()
    file_storage = _valid_image_filestorage()
    data = dict(form)
    data["profile_picture"] = file_storage

    with patch("app.mail.send") as mock_send:
        resp = client.post("/register", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        assert b"verify" in resp.data.lower() or b"verification" in resp.data.lower()

        created = User.query.filter_by(username=form["username"]).first()
        assert created is not None
        assert created.email == form["email"]
        assert created.check_password(form["password"]) is True
        assert created.password_hash != form["password"]
        assert created.is_email_verified is False

        token_row = EmailVerificationToken.query.filter_by(user_id=created.id).first()
        assert token_row is not None
        assert isinstance(token_row.token, str)
        assert 20 <= len(token_row.token) <= 255
        assert token_row.used_at is None

        assert mock_send.called is True

def test_register_post_missing_required_fields(client):
    data = _valid_register_form()
    data.pop("email")
    data.pop("password")

    with patch("app.mail.send") as mock_send:
        resp = client.post("/register", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert mock_send.called is False

        created = User.query.filter_by(username=data["username"]).first()
        assert created is None

def test_register_post_invalid_data(client):
    data = _valid_register_form()
    data["gender"] = "invalid_gender"
    data["contact_number"] = "abc"
    data["birthdate"] = "01-01-1990"
    data["username"] = "bad username!"
    data["email"] = "not-an-email"
    data["password"] = "short"

    with patch("app.mail.send") as mock_send:
        resp = client.post("/register", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert mock_send.called is False

        created = User.query.filter_by(email=data["email"]).first()
        assert created is None

def test_register_post_duplicate_data(client):
    existing_username = _unique_username("dupuser")
    existing_email = _unique_email("dupemail")
    _create_user_in_db(username=existing_username, email=existing_email)

    data = _valid_register_form(username=existing_username, email=_unique_email("new"))
    with patch("app.mail.send") as mock_send:
        resp = client.post("/register", data=data, content_type="multipart/form-data")
        assert resp.status_code == 409
        assert mock_send.called is False

    data2 = _valid_register_form(username=_unique_username("new"), email=existing_email)
    with patch("app.mail.send") as mock_send2:
        resp2 = client.post("/register", data=data2, content_type="multipart/form-data")
        assert resp2.status_code == 409
        assert mock_send2.called is False

# ROUTE: /verify-email (GET) - verify_email_get
def test_verify_email_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/verify-email"]
    assert rules, "Route /verify-email is missing"
    methods = set()
    for r in rules:
        methods |= set(r.methods or [])
    assert "GET" in methods, "/verify-email must accept GET"

def test_verify_email_get_renders_template(client):
    resp = client.get("/verify-email")
    assert resp.status_code in (400, 200)
    if resp.status_code == 200:
        assert b"verify" in resp.data.lower() or b"verification" in resp.data.lower()
    else:
        assert b"verify" in resp.data.lower() or b"verification" in resp.data.lower() or resp.data != b""

# HELPER: validate_registration_payload(form: dict, files: dict)
def test_validate_registration_payload_function_exists():
    assert callable(validate_registration_payload)

def test_validate_registration_payload_with_valid_input():
    form = _valid_register_form()
    files = {"profile_picture": _valid_image_filestorage()}
    result = validate_registration_payload(form=form, files=files)
    assert isinstance(result, dict)
    assert "errors" in result
    assert "data" in result
    assert result["errors"] in (None, {}) or isinstance(result["errors"], dict)
    if isinstance(result["errors"], dict):
        assert result["errors"] == {}

def test_validate_registration_payload_with_invalid_input():
    form = _valid_register_form()
    form["email"] = "bad"
    form["username"] = "bad username"
    form["contact_number"] = "x"
    form["birthdate"] = "1990/01/01"
    form["gender"] = "unknown"
    form["password"] = "short"
    files = {"profile_picture": FileStorage(stream=BytesIO(b"x"), filename="x.txt", content_type="text/plain")}

    result = validate_registration_payload(form=form, files=files)
    assert isinstance(result, dict)
    assert "errors" in result
    assert isinstance(result["errors"], dict)
    assert result["errors"], "Expected validation errors for invalid input"

# HELPER: create_email_verification_token(user: User)
def test_create_email_verification_token_function_exists():
    assert callable(create_email_verification_token)

def test_create_email_verification_token_with_valid_input(app_context):
    user = _create_user_in_db()
    tok = create_email_verification_token(user=user)
    assert isinstance(tok, EmailVerificationToken)
    assert tok.user_id == user.id
    assert isinstance(tok.token, str)
    assert 20 <= len(tok.token) <= 255
    assert tok.expires_at is not None

def test_create_email_verification_token_with_invalid_input():
    with pytest.raises(Exception):
        create_email_verification_token(user=None)

# HELPER: send_verification_email(user: User, token: str)
def test_send_verification_email_function_exists():
    assert callable(send_verification_email)

def test_send_verification_email_with_valid_input(app_context):
    user = _create_user_in_db()
    token = "tok_" + uuid.uuid4().hex + ("x" * 20)

    with patch("app.mail.send") as mock_send:
        send_verification_email(user=user, token=token)
        assert mock_send.called is True

def test_send_verification_email_with_invalid_input(app_context):
    user = _create_user_in_db()
    with patch("app.mail.send") as mock_send:
        with pytest.raises(Exception):
            send_verification_email(user=user, token="")
        assert mock_send.called is False

# HELPER: save_profile_picture(file_storage, username: str)
def test_save_profile_picture_function_exists():
    assert callable(save_profile_picture)

def test_save_profile_picture_with_valid_input(app_context):
    username = _unique_username("picuser")
    fs = _valid_image_filestorage()

    with patch("werkzeug.datastructures.file_storage.FileStorage.save") as mock_save:
        path = save_profile_picture(file_storage=fs, username=username)
        assert isinstance(path, str)
        assert path
        assert "profile" in path.lower() or "upload" in path.lower() or "static" in path.lower()
        assert mock_save.called is True

def test_save_profile_picture_with_invalid_input(app_context):
    username = _unique_username("picuser")
    with pytest.raises(Exception):
        save_profile_picture(file_storage=None, username=username)