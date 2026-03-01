import os
import sys
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, mail
from models.user import User
from models.user_login_otp import UserLoginOtp
from controllers.user_login_controller import (
    build_google_oauth_flow,
    exchange_code_for_tokens,
    fetch_google_userinfo,
    is_allowed_domain,
    get_or_create_user_from_google,
    generate_otp_code,
    hash_otp_code,
    verify_otp_code,
    create_login_otp,
    send_otp_email,
    login_user_session,
    logout_user_session,
)
from views.user_login_views import render_landing

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

def _unique_email(domain="iiitd.ac.in"):
    return f"test_{uuid.uuid4().hex[:10]}@{domain}"

def _unique_sub():
    return f"sub_{uuid.uuid4().hex}"

def _create_user_in_db(email=None, google_sub=None, name="Test User", is_2fa_enabled=True):
    if email is None:
        email = _unique_email()
    if google_sub is None:
        google_sub = _unique_sub()
    user = User(email=email, google_sub=google_sub, name=name, is_2fa_enabled=is_2fa_enabled)
    db.session.add(user)
    db.session.commit()
    return user

def _create_otp_in_db(user, otp_code="123456", expires_delta_minutes=10, consumed=False):
    otp_hash = hash_otp_code(otp_code)
    expires_at = datetime.utcnow() + timedelta(minutes=expires_delta_minutes)
    otp = UserLoginOtp(
        user_id=user.id,
        otp_code_hash=otp_hash,
        purpose="login_2fa",
        expires_at=expires_at,
        consumed_at=(datetime.utcnow() if consumed else None),
    )
    db.session.add(otp)
    db.session.commit()
    return otp, otp_code

def _allowed_userinfo(email=None, sub=None, name="Allowed User"):
    if email is None:
        email = _unique_email("iiitd.ac.in")
    if sub is None:
        sub = _unique_sub()
    return {"email": email, "sub": sub, "name": name}

def _disallowed_userinfo(email=None, sub=None, name="Disallowed User"):
    if email is None:
        email = _unique_email("gmail.com")
    if sub is None:
        sub = _unique_sub()
    return {"email": email, "sub": sub, "name": name}

def _route_exists(path, method):
    method = method.upper()
    for rule in app.url_map.iter_rules():
        if rule.rule == path and method in rule.methods:
            return True
    return False

# MODEL: User (models/user.py)
def test_user_model_has_required_fields(app_context):
    for field in ["id", "email", "name", "google_sub", "is_2fa_enabled", "created_at", "last_login_at"]:
        assert hasattr(User, field), f"Missing required field on User: {field}"

def test_user_to_dict(app_context):
    email = _unique_email()
    sub = _unique_sub()
    user = User(email=email, google_sub=sub, name="Alice", is_2fa_enabled=True)
    d = user.to_dict()
    assert isinstance(d, dict)
    assert d.get("email") == email
    assert d.get("google_sub") == sub
    assert d.get("name") == "Alice"
    assert "id" in d
    assert "created_at" in d
    assert "last_login_at" in d
    assert "is_2fa_enabled" in d

def test_user_unique_constraints(app_context):
    email = _unique_email()
    sub1 = _unique_sub()
    sub2 = _unique_sub()

    u1 = User(email=email, google_sub=sub1, name="U1")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, google_sub=sub2, name="U2")
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    email2 = _unique_email()
    u3 = User(email=email2, google_sub=sub1, name="U3")
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: UserLoginOtp (models/user_login_otp.py)
def test_userloginotp_model_has_required_fields(app_context):
    for field in ["id", "user_id", "otp_code_hash", "purpose", "expires_at", "consumed_at", "created_at"]:
        assert hasattr(UserLoginOtp, field), f"Missing required field on UserLoginOtp: {field}"

def test_userloginotp_is_expired(app_context):
    user = _create_user_in_db()
    otp_hash = hash_otp_code("111111")
    otp = UserLoginOtp(
        user_id=user.id,
        otp_code_hash=otp_hash,
        purpose="login_2fa",
        expires_at=datetime.utcnow() - timedelta(seconds=1),
        consumed_at=None,
    )
    db.session.add(otp)
    db.session.commit()
    assert otp.is_expired() is True

def test_userloginotp_is_consumed(app_context):
    user = _create_user_in_db()
    otp_hash = hash_otp_code("222222")
    otp = UserLoginOtp(
        user_id=user.id,
        otp_code_hash=otp_hash,
        purpose="login_2fa",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        consumed_at=datetime.utcnow(),
    )
    db.session.add(otp)
    db.session.commit()
    assert otp.is_consumed() is True

def test_userloginotp_unique_constraints(app_context):
    user = _create_user_in_db()
    otp1 = UserLoginOtp(
        user_id=user.id,
        otp_code_hash=hash_otp_code("333333"),
        purpose="login_2fa",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        consumed_at=None,
    )
    otp2 = UserLoginOtp(
        user_id=user.id,
        otp_code_hash=hash_otp_code("444444"),
        purpose="login_2fa",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        consumed_at=None,
    )
    db.session.add_all([otp1, otp2])
    db.session.commit()
    assert otp1.id is not None
    assert otp2.id is not None
    assert otp1.id != otp2.id

# ROUTE: /auth/google/login (GET) - google_login
def test_auth_google_login_get_exists():
    assert _route_exists("/auth/google/login", "GET"), "Route /auth/google/login (GET) not registered"

def test_auth_google_login_get_renders_template(client):
    with patch("controllers.user_login_controller.build_google_oauth_flow") as mock_build, patch(
        "controllers.user_login_controller.redirect"
    ) as mock_redirect:
        flow = MagicMock()
        flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth", "state123")
        mock_build.return_value = flow
        mock_redirect.side_effect = lambda url: (url, 302)

        resp = client.get("/auth/google/login")
        assert resp.status_code in (200, 302)

# ROUTE: /auth/google/callback (GET) - google_callback
def test_auth_google_callback_get_exists():
    assert _route_exists("/auth/google/callback", "GET"), "Route /auth/google/callback (GET) not registered"

def test_auth_google_callback_get_renders_template(client):
    userinfo = _allowed_userinfo()
    with patch("controllers.user_login_controller.build_google_oauth_flow") as mock_build, patch(
        "controllers.user_login_controller.exchange_code_for_tokens"
    ) as mock_exchange, patch(
        "controllers.user_login_controller.fetch_google_userinfo"
    ) as mock_userinfo, patch(
        "controllers.user_login_controller.is_allowed_domain"
    ) as mock_allowed, patch(
        "controllers.user_login_controller.get_or_create_user_from_google"
    ) as mock_get_or_create, patch(
        "controllers.user_login_controller.create_login_otp"
    ) as mock_create_otp, patch(
        "controllers.user_login_controller.send_otp_email"
    ) as mock_send_email, patch(
        "controllers.user_login_controller.render_template"
    ) as mock_render, patch(
        "controllers.user_login_controller.redirect"
    ) as mock_redirect:
        mock_build.return_value = MagicMock()
        mock_exchange.return_value = {"access_token": "token"}
        mock_userinfo.return_value = userinfo
        mock_allowed.return_value = True

        created_user = MagicMock(spec=User)
        created_user.email = userinfo["email"]
        created_user.is_2fa_enabled = True
        created_user.id = 1
        mock_get_or_create.return_value = created_user

        otp_obj = MagicMock(spec=UserLoginOtp)
        otp_obj.id = 1
        mock_create_otp.return_value = otp_obj

        mock_render.return_value = "2fa-page"
        mock_redirect.side_effect = lambda url: (url, 302)

        resp = client.get("/auth/google/callback?code=fakecode&state=fakestate")
        assert resp.status_code in (200, 302)

# ROUTE: /auth/2fa/verify (POST) - verify_2fa
def test_auth_2fa_verify_post_exists():
    assert _route_exists("/auth/2fa/verify", "POST"), "Route /auth/2fa/verify (POST) not registered"

def test_auth_2fa_verify_post_success(client):
    with app.app_context():
        user = _create_user_in_db(is_2fa_enabled=True)
        otp, otp_code = _create_otp_in_db(user, otp_code="654321", expires_delta_minutes=10, consumed=False)

    with patch("controllers.user_login_controller.verify_otp_code") as mock_verify, patch(
        "controllers.user_login_controller.login_user_session"
    ) as mock_login_session:
        mock_verify.return_value = True
        resp = client.post("/auth/2fa/verify", data={"email": user.email, "otp_code": otp_code})
        assert resp.status_code in (200, 302)
        assert mock_login_session.called is True

def test_auth_2fa_verify_post_missing_required_fields(client):
    resp = client.post("/auth/2fa/verify", data={})
    assert resp.status_code in (200, 400, 422)

def test_auth_2fa_verify_post_invalid_data(client):
    resp = client.post("/auth/2fa/verify", data={"email": "not-an-email", "otp_code": "abc"})
    assert resp.status_code in (200, 400, 422)

def test_auth_2fa_verify_post_duplicate_data(client):
    with app.app_context():
        user = _create_user_in_db(is_2fa_enabled=True)
        otp, otp_code = _create_otp_in_db(user, otp_code="777777", expires_delta_minutes=10, consumed=False)

    with patch("controllers.user_login_controller.verify_otp_code") as mock_verify, patch(
        "controllers.user_login_controller.login_user_session"
    ) as mock_login_session:
        mock_verify.return_value = True
        resp1 = client.post("/auth/2fa/verify", data={"email": user.email, "otp_code": otp_code})
        assert resp1.status_code in (200, 302)

        resp2 = client.post("/auth/2fa/verify", data={"email": user.email, "otp_code": otp_code})
        assert resp2.status_code in (200, 400, 409, 422, 302)
        assert mock_login_session.called is True

# ROUTE: /logout (POST) - logout
def test_logout_post_exists():
    assert _route_exists("/logout", "POST"), "Route /logout (POST) not registered"

def test_logout_post_success(client):
    with patch("controllers.user_login_controller.logout_user_session") as mock_logout:
        resp = client.post("/logout", data={})
        assert resp.status_code in (200, 302)
        assert mock_logout.called is True

def test_logout_post_missing_required_fields(client):
    resp = client.post("/logout", data={})
    assert resp.status_code in (200, 302, 400, 422)

def test_logout_post_invalid_data(client):
    resp = client.post("/logout", data={"unexpected": "value"})
    assert resp.status_code in (200, 302, 400, 422)

def test_logout_post_duplicate_data(client):
    with patch("controllers.user_login_controller.logout_user_session") as mock_logout:
        resp1 = client.post("/logout", data={})
        resp2 = client.post("/logout", data={})
        assert resp1.status_code in (200, 302)
        assert resp2.status_code in (200, 302, 400, 409, 422)
        assert mock_logout.called is True

# ROUTE: /session (GET) - get_session
def test_session_get_exists():
    assert _route_exists("/session", "GET"), "Route /session (GET) not registered"

def test_session_get_renders_template(client):
    resp = client.get("/session")
    assert resp.status_code in (200, 302)

# HELPER: build_google_oauth_flow(redirect_uri)
def test_build_google_oauth_flow_function_exists():
    assert callable(build_google_oauth_flow)

def test_build_google_oauth_flow_with_valid_input():
    with patch("controllers.user_login_controller.Flow") as mock_flow_cls:
        mock_flow = MagicMock()
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow
        flow = build_google_oauth_flow("http://localhost/auth/google/callback")
        assert flow is not None

def test_build_google_oauth_flow_with_invalid_input():
    with pytest.raises(Exception):
        build_google_oauth_flow(None)

# HELPER: exchange_code_for_tokens(flow, authorization_response_url)
def test_exchange_code_for_tokens_function_exists():
    assert callable(exchange_code_for_tokens)

def test_exchange_code_for_tokens_with_valid_input():
    flow = MagicMock()
    flow.credentials = MagicMock()
    flow.credentials.token = "access-token"
    flow.fetch_token.return_value = None
    tokens = exchange_code_for_tokens(flow, "http://localhost/auth/google/callback?code=abc")
    assert isinstance(tokens, dict)

def test_exchange_code_for_tokens_with_invalid_input():
    with pytest.raises(Exception):
        exchange_code_for_tokens(None, None)

# HELPER: fetch_google_userinfo(access_token)
def test_fetch_google_userinfo_function_exists():
    assert callable(fetch_google_userinfo)

def test_fetch_google_userinfo_with_valid_input():
    with patch("controllers.user_login_controller.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _allowed_userinfo()
        mock_get.return_value = mock_resp
        userinfo = fetch_google_userinfo("access-token")
        assert isinstance(userinfo, dict)
        assert "email" in userinfo

def test_fetch_google_userinfo_with_invalid_input():
    with pytest.raises(Exception):
        fetch_google_userinfo(None)

# HELPER: is_allowed_domain(email)
def test_is_allowed_domain_function_exists():
    assert callable(is_allowed_domain)

def test_is_allowed_domain_with_valid_input():
    assert is_allowed_domain(_unique_email("iiitd.ac.in")) is True

def test_is_allowed_domain_with_invalid_input():
    assert is_allowed_domain(_unique_email("gmail.com")) is False

# HELPER: get_or_create_user_from_google(userinfo)
def test_get_or_create_user_from_google_function_exists():
    assert callable(get_or_create_user_from_google)

def test_get_or_create_user_from_google_with_valid_input(app_context):
    userinfo = _allowed_userinfo()
    user = get_or_create_user_from_google(userinfo)
    assert isinstance(user, User)
    assert user.email == userinfo["email"]
    assert user.google_sub == userinfo["sub"]

def test_get_or_create_user_from_google_with_invalid_input(app_context):
    with pytest.raises(Exception):
        get_or_create_user_from_google(None)

# HELPER: generate_otp_code(N/A)
def test_generate_otp_code_function_exists():
    assert callable(generate_otp_code)

def test_generate_otp_code_with_valid_input():
    code = generate_otp_code()
    assert isinstance(code, str)
    assert code.strip() != ""

def test_generate_otp_code_with_invalid_input():
    with pytest.raises(TypeError):
        generate_otp_code("unexpected")

# HELPER: hash_otp_code(otp_code)
def test_hash_otp_code_function_exists():
    assert callable(hash_otp_code)

def test_hash_otp_code_with_valid_input():
    otp_code = "123456"
    h = hash_otp_code(otp_code)
    assert isinstance(h, str)
    assert h != otp_code
    assert len(h) > 10

def test_hash_otp_code_with_invalid_input():
    with pytest.raises(Exception):
        hash_otp_code(None)

# HELPER: verify_otp_code(otp_code, otp_code_hash)
def test_verify_otp_code_function_exists():
    assert callable(verify_otp_code)

def test_verify_otp_code_with_valid_input():
    otp_code = "999999"
    h = hash_otp_code(otp_code)
    assert verify_otp_code(otp_code, h) is True
    assert verify_otp_code("000000", h) is False

def test_verify_otp_code_with_invalid_input():
    with pytest.raises(Exception):
        verify_otp_code(None, None)

# HELPER: create_login_otp(user)
def test_create_login_otp_function_exists():
    assert callable(create_login_otp)

def test_create_login_otp_with_valid_input(app_context):
    user = _create_user_in_db(is_2fa_enabled=True)
    otp = create_login_otp(user)
    assert isinstance(otp, UserLoginOtp)
    assert otp.user_id == user.id
    assert isinstance(otp.otp_code_hash, str)
    assert otp.otp_code_hash != ""
    assert otp.expires_at is not None

def test_create_login_otp_with_invalid_input(app_context):
    with pytest.raises(Exception):
        create_login_otp(None)

# HELPER: send_otp_email(to_email, otp_code)
def test_send_otp_email_function_exists():
    assert callable(send_otp_email)

def test_send_otp_email_with_valid_input(app_context):
    with patch("app.mail.send") as mock_send:
        send_otp_email(_unique_email("iiitd.ac.in"), "123456")
        assert mock_send.called is True

def test_send_otp_email_with_invalid_input(app_context):
    with patch("app.mail.send"):
        with pytest.raises(Exception):
            send_otp_email(None, None)

# HELPER: login_user_session(user)
def test_login_user_session_function_exists():
    assert callable(login_user_session)

def test_login_user_session_with_valid_input(app_context):
    user = _create_user_in_db(is_2fa_enabled=False)
    with app.test_request_context("/"):
        login_user_session(user)

def test_login_user_session_with_invalid_input(app_context):
    with app.test_request_context("/"):
        with pytest.raises(Exception):
            login_user_session(None)

# HELPER: logout_user_session(N/A)
def test_logout_user_session_function_exists():
    assert callable(logout_user_session)

def test_logout_user_session_with_valid_input(app_context):
    with app.test_request_context("/"):
        logout_user_session()

def test_logout_user_session_with_invalid_input(app_context):
    with pytest.raises(TypeError):
        logout_user_session("unexpected")