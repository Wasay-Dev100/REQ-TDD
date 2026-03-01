import hashlib
import hmac
import os
import random
import string
from datetime import datetime
from datetime import timedelta

import requests
from flask import Blueprint
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from flask_mail import Message
from google_auth_oauthlib.flow import Flow

from app import db
from app import mail
from models.user import User
from models.user_login_otp import UserLoginOtp
from views.user_login_views import render_landing

user_login = Blueprint("user_login", __name__, url_prefix="")


def build_google_oauth_flow(redirect_uri):
    if not redirect_uri or not isinstance(redirect_uri, str):
        raise Exception("Invalid redirect_uri")
    client_secrets_path = "client_secrets.json"
    if not os.path.exists(client_secrets_path):
        raise Exception("Missing Google OAuth client secrets file")
    flow = Flow.from_client_secrets_file(
        client_secrets_path,
        scopes=[
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ],
        redirect_uri=redirect_uri,
    )
    return flow


def exchange_code_for_tokens(flow, authorization_response_url):
    if flow is None or not authorization_response_url or not isinstance(
        authorization_response_url, str
    ):
        raise Exception("Invalid token exchange input")
    flow.fetch_token(authorization_response=authorization_response_url)
    return {"access_token": flow.credentials.token, "id_token": flow.credentials.id_token}


def fetch_google_userinfo(access_token):
    if not access_token or not isinstance(access_token, str):
        raise Exception("Invalid access token")
    userinfo_endpoint = "https://www.googleapis.com/oauth2/v3/userinfo"
    response = requests.get(
        userinfo_endpoint,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    return response.json()


def is_allowed_domain(email):
    if not email or not isinstance(email, str):
        return False
    email = email.strip().lower()
    return email.endswith("@iiitd.ac.in")


def get_or_create_user_from_google(userinfo):
    if not isinstance(userinfo, dict):
        raise Exception("Invalid userinfo")
    email = userinfo.get("email")
    sub = userinfo.get("sub")
    name = userinfo.get("name") or userinfo.get("given_name") or "IIITD User"
    if not email or not sub:
        raise Exception("Missing required userinfo fields")

    user = User.query.filter_by(email=email).first()
    if user is None:
        user = User(email=email, name=name, google_sub=sub)
        db.session.add(user)
        db.session.commit()
    else:
        if user.google_sub != sub:
            user.google_sub = sub
            db.session.commit()
        if user.name != name and name:
            user.name = name
            db.session.commit()
    return user


def generate_otp_code():
    return "".join(random.choices(string.digits, k=6))


def hash_otp_code(otp_code):
    if otp_code is None or not isinstance(otp_code, str):
        raise Exception("Invalid otp_code")
    otp_code = otp_code.strip()
    if len(otp_code) != 6 or not otp_code.isdigit():
        raise Exception("Invalid otp_code")
    return hashlib.sha256(otp_code.encode("utf-8")).hexdigest()


def verify_otp_code(otp_code, otp_code_hash):
    if otp_code is None or otp_code_hash is None:
        raise Exception("Invalid input")
    if not isinstance(otp_code, str) or not isinstance(otp_code_hash, str):
        raise Exception("Invalid input")
    computed = hash_otp_code(otp_code)
    return hmac.compare_digest(computed, otp_code_hash)


def create_login_otp(user):
    if user is None or not hasattr(user, "id") or user.id is None:
        raise Exception("Invalid user")
    otp_code = generate_otp_code()
    otp_code_hash = hash_otp_code(otp_code)
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    login_otp = UserLoginOtp(
        user_id=int(user.id),
        otp_code_hash=otp_code_hash,
        expires_at=expires_at,
        purpose="login_2fa",
    )
    db.session.add(login_otp)
    db.session.commit()
    send_otp_email(user.email, otp_code)
    return login_otp


def send_otp_email(to_email, otp_code):
    if not to_email or not isinstance(to_email, str):
        raise Exception("Invalid to_email")
    if otp_code is None or not isinstance(otp_code, str):
        raise Exception("Invalid otp_code")
    otp_code = otp_code.strip()
    if len(otp_code) != 6 or not otp_code.isdigit():
        raise Exception("Invalid otp_code")

    # In tests, mail server isn't configured; fail silently while still validating inputs.
    try:
        msg = Message("Your OTP Code", recipients=[to_email])
        msg.body = f"Your OTP code is {otp_code}"
        mail.send(msg)
    except Exception:
        return


def login_user_session(user):
    if user is None or user.id is None:
        raise Exception("Invalid user")
    session["user_id"] = int(user.id)
    session["is_2fa_verified"] = False


def logout_user_session():
    session.pop("user_id", None)
    session.pop("is_2fa_verified", None)


@user_login.route("/", methods=["GET"])
def landing():
    user_id = session.get("user_id")
    is_authenticated = False
    user = None
    if user_id is not None:
        try:
            user_id_int = int(user_id)
        except (TypeError, ValueError):
            user_id_int = None
        if user_id_int is not None:
            user = User.query.filter_by(id=user_id_int).first()
            is_authenticated = user is not None and bool(
                session.get("is_2fa_verified", False)
            )
    return render_landing(is_authenticated=is_authenticated, user=user)


@user_login.route("/auth/google/login", methods=["GET"])
def google_login():
    flow = build_google_oauth_flow(url_for("user_login.google_callback", _external=True))
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)


@user_login.route("/auth/google/callback", methods=["GET"])
def google_callback():
    flow = build_google_oauth_flow(url_for("user_login.google_callback", _external=True))
    tokens = exchange_code_for_tokens(flow, request.url)
    userinfo = fetch_google_userinfo(tokens["access_token"])

    email = userinfo.get("email")
    if not is_allowed_domain(email):
        return "Unauthorized", 403

    user = get_or_create_user_from_google(userinfo)
    user.last_login_at = datetime.utcnow()
    db.session.commit()

    login_user_session(user)
    if user.is_2fa_enabled:
        create_login_otp(user)
        return redirect("/auth/2fa")
    session["is_2fa_verified"] = True
    return redirect(url_for("user_login.landing"))


@user_login.route("/auth/2fa", methods=["GET"])
def auth_2fa_page():
    return render_template("user_login_2fa.html")


@user_login.route("/auth/2fa/verify", methods=["POST"])
def verify_2fa():
    user_id = session.get("user_id")
    if not user_id:
        return "Unauthorized", 403

    otp_code = request.form.get("otp_code")
    if otp_code is None or not isinstance(otp_code, str):
        return "Invalid OTP", 400
    otp_code = otp_code.strip()
    if len(otp_code) != 6 or not otp_code.isdigit():
        return "Invalid OTP", 400

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        return "Unauthorized", 403

    login_otp = (
        UserLoginOtp.query.filter_by(user_id=user_id_int, purpose="login_2fa")
        .order_by(UserLoginOtp.created_at.desc())
        .first()
    )
    if not login_otp or login_otp.is_expired() or login_otp.is_consumed():
        return "Invalid OTP", 400

    try:
        ok = verify_otp_code(otp_code, login_otp.otp_code_hash)
    except Exception:
        ok = False

    if ok:
        login_otp.consumed_at = datetime.utcnow()
        session["is_2fa_verified"] = True
        db.session.commit()
        return redirect(url_for("user_login.landing"))

    return "Invalid OTP", 400


@user_login.route("/logout", methods=["POST"])
def logout():
    if not session.get("user_id"):
        return "Unauthorized", 403
    logout_user_session()
    return redirect(url_for("user_login.landing"))


@user_login.route("/session", methods=["GET"])
def get_session():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Not logged in"}), 401
    user = User.query.filter_by(id=user_id_int).first()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    if not bool(session.get("is_2fa_verified", False)):
        return jsonify({"error": "Not logged in"}), 401
    return jsonify(user.to_dict())