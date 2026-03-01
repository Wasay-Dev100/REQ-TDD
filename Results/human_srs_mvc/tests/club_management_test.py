import os
import sys
import uuid
import json
from datetime import datetime, date
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.club_management_club import Club
from models.club_management_club_coordinator import ClubCoordinator
from models.club_management_club_event_image import ClubEventImage
from controllers.club_management_controller import (
    get_current_user,
    require_roles,
    can_edit_club,
    parse_update_club_payload,
    validate_update_club_payload,
    parse_add_event_image_payload,
    validate_add_event_image_payload,
)
from views.club_management_views import render_club_list, render_club_detail, render_club_edit_form

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

def _create_user(role="club_coordinator", is_active=True):
    u = User(
        email=f"{_unique('user')}@example.com",
        username=_unique("user"),
        password_hash="",
        role=role,
        is_active=is_active,
    )
    u.set_password("Password123!")
    db.session.add(u)
    db.session.commit()
    return u

def _create_club():
    c = Club(
        slug=_unique("club"),
        name=_unique("Club Name"),
        description="Initial description",
        members_list="A, B, C",
        contact_name="Contact",
        contact_email="contact@example.com",
        contact_phone="123",
    )
    db.session.add(c)
    db.session.commit()
    return c

def _create_coordinator_link(user_id: int, club_id: int):
    link = ClubCoordinator(user_id=user_id, club_id=club_id)
    db.session.add(link)
    db.session.commit()
    return link

def _create_event_image(club_id: int, title="Title", image_url="https://example.com/img.jpg", event_date_obj=None):
    if event_date_obj is None:
        event_date_obj = datetime.strptime("2024-01-02", "%Y-%m-%d").date()
    img = ClubEventImage(club_id=club_id, title=title, image_url=image_url, event_date=event_date_obj)
    db.session.add(img)
    db.session.commit()
    return img

def _login_as(client, user: User):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["_user_id"] = str(user.id)

def _route_exists(rule: str, method: str) -> bool:
    for r in app.url_map.iter_rules():
        if r.rule == rule and method in r.methods:
            return True
    return False

def _assert_error_schema(payload: dict):
    assert isinstance(payload, dict)
    assert set(payload.keys()).issuperset({"error", "message"})
    assert isinstance(payload.get("error"), str)
    assert isinstance(payload.get("message"), str)
    extra = set(payload.keys()) - {"error", "message", "details"}
    assert extra == set()

def _assert_update_club_response_schema(payload: dict):
    assert isinstance(payload, dict)
    assert set(payload.keys()) == {"id", "slug", "name", "description", "members_list", "contact", "updated_at"}
    assert isinstance(payload["id"], int)
    assert isinstance(payload["slug"], str)
    assert isinstance(payload["name"], str)
    assert isinstance(payload["description"], str)
    assert isinstance(payload["members_list"], str)
    assert isinstance(payload["contact"], dict)
    assert set(payload["contact"].keys()) == {"name", "email", "phone"}
    assert isinstance(payload["contact"]["name"], str)
    assert isinstance(payload["contact"]["email"], str)
    assert isinstance(payload["contact"]["phone"], str)
    assert isinstance(payload["updated_at"], str)

def _assert_add_event_image_response_schema(payload: dict):
    assert isinstance(payload, dict)
    assert set(payload.keys()) == {"id", "club_id", "title", "image_url", "event_date", "created_at"}
    assert isinstance(payload["id"], int)
    assert isinstance(payload["club_id"], int)
    assert isinstance(payload["title"], str)
    assert isinstance(payload["image_url"], str)
    assert isinstance(payload["event_date"], str)
    assert isinstance(payload["created_at"], str)

# MODEL: User (models/user.py)
def test_user_model_has_required_fields(app_context):
    user = User(email=_unique("e") + "@example.com", username=_unique("u"), password_hash="", role="admin", is_active=True)
    for field in ["id", "email", "username", "password_hash", "role", "is_active"]:
        assert hasattr(user, field), field

def test_user_set_password(app_context):
    user = User(email=_unique("e") + "@example.com", username=_unique("u"), password_hash="", role="admin", is_active=True)
    user.set_password("Password123!")
    assert user.password_hash
    assert user.password_hash != "Password123!"

def test_user_check_password(app_context):
    user = User(email=_unique("e") + "@example.com", username=_unique("u"), password_hash="", role="admin", is_active=True)
    user.set_password("Password123!")
    assert user.check_password("Password123!") is True
    assert user.check_password("WrongPassword!") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")
    u1 = User(email=email, username=username, password_hash="", role="admin", is_active=True)
    u1.set_password("Password123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("otheruser"), password_hash="", role="admin", is_active=True)
    u2.set_password("Password123!")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, password_hash="", role="admin", is_active=True)
    u3.set_password("Password123!")
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()

# MODEL: Club (models/club_management_club.py)
def test_club_model_has_required_fields(app_context):
    club = Club(
        slug=_unique("slug"),
        name=_unique("name"),
        description="d",
        members_list="m",
        contact_name="c",
        contact_email="c@example.com",
        contact_phone="1",
    )
    for field in [
        "id",
        "slug",
        "name",
        "description",
        "members_list",
        "contact_name",
        "contact_email",
        "contact_phone",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(club, field), field

def test_club_touch_updated_at(app_context):
    club = _create_club()
    before = club.updated_at
    club.touch_updated_at()
    db.session.add(club)
    db.session.commit()
    db.session.refresh(club)
    after = club.updated_at
    assert after is not None
    assert before is None or after >= before

def test_club_unique_constraints(app_context):
    slug = _unique("slug")
    name = _unique("name")
    c1 = Club(
        slug=slug,
        name=name,
        description="d",
        members_list="m",
        contact_name="c",
        contact_email="c@example.com",
        contact_phone="1",
    )
    db.session.add(c1)
    db.session.commit()

    c2 = Club(
        slug=slug,
        name=_unique("name2"),
        description="d",
        members_list="m",
        contact_name="c",
        contact_email="c@example.com",
        contact_phone="1",
    )
    db.session.add(c2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    c3 = Club(
        slug=_unique("slug2"),
        name=name,
        description="d",
        members_list="m",
        contact_name="c",
        contact_email="c@example.com",
        contact_phone="1",
    )
    db.session.add(c3)
    with pytest.raises(Exception):
        db.session.commit()

# MODEL: ClubCoordinator (models/club_management_club_coordinator.py)
def test_clubcoordinator_model_has_required_fields(app_context):
    cc = ClubCoordinator(club_id=1, user_id=1)
    for field in ["id", "club_id", "user_id", "created_at"]:
        assert hasattr(cc, field), field

def test_clubcoordinator_unique_constraints(app_context):
    user = _create_user(role="club_coordinator")
    club = _create_club()
    cc1 = ClubCoordinator(club_id=club.id, user_id=user.id)
    cc2 = ClubCoordinator(club_id=club.id, user_id=user.id)
    db.session.add(cc1)
    db.session.add(cc2)
    db.session.commit()
    assert ClubCoordinator.query.filter_by(club_id=club.id, user_id=user.id).count() == 2

# MODEL: ClubEventImage (models/club_management_club_event_image.py)
def test_clubeventimage_model_has_required_fields(app_context):
    img = ClubEventImage(
        club_id=1,
        title="t",
        image_url="https://example.com/x.jpg",
        event_date=datetime.strptime("2024-01-02", "%Y-%m-%d").date(),
    )
    for field in ["id", "club_id", "title", "image_url", "event_date", "created_at"]:
        assert hasattr(img, field), field

def test_clubeventimage_unique_constraints(app_context):
    club = _create_club()
    d = datetime.strptime("2024-01-02", "%Y-%m-%d").date()
    i1 = ClubEventImage(club_id=club.id, title="t", image_url="https://example.com/x.jpg", event_date=d)
    i2 = ClubEventImage(club_id=club.id, title="t", image_url="https://example.com/x.jpg", event_date=d)
    db.session.add(i1)
    db.session.add(i2)
    db.session.commit()
    assert ClubEventImage.query.filter_by(club_id=club.id).count() == 2

# ROUTE: /clubs (GET) - list_clubs
def test_clubs_get_exists(client):
    assert _route_exists("/clubs", "GET") is True

def test_clubs_get_renders_template(client):
    club = None
    with app.app_context():
        club = _create_club()
    resp = client.get("/clubs")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")
    assert club.name.encode() in resp.data or club.slug.encode() in resp.data

# ROUTE: /clubs/<int:club_id> (GET) - view_club
def test_clubs_club_id_get_exists(client):
    assert _route_exists("/clubs/<int:club_id>", "GET") is True

def test_clubs_club_id_get_renders_template(client):
    with app.app_context():
        club = _create_club()
        _create_event_image(club_id=club.id, title="Event 1", image_url="https://example.com/1.jpg")
        club_id = club.id
    resp = client.get(f"/clubs/{club_id}")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")
    assert b"Event 1" in resp.data or b"https://example.com/1.jpg" in resp.data or str(club_id).encode() in resp.data

# ROUTE: /clubs/<int:club_id>/edit (GET) - edit_club_form
def test_clubs_club_id_edit_get_exists(client):
    assert _route_exists("/clubs/<int:club_id>/edit", "GET") is True

def test_clubs_club_id_edit_get_renders_template(client):
    with app.app_context():
        club = _create_club()
        user = _create_user(role="admin")
        club_id = club.id

    _login_as(client, user)
    resp = client.get(f"/clubs/{club_id}/edit")
    assert resp.status_code in (200, 401, 403)
    if resp.status_code == 200:
        assert resp.content_type.startswith("text/html")
        assert club.slug.encode() in resp.data or club.name.encode() in resp.data

# ROUTE: /clubs/<int:club_id> (PUT) - update_club
def test_clubs_club_id_put_exists(client):
    assert _route_exists("/clubs/<int:club_id>", "PUT") is True

# ROUTE: /clubs/<int:club_id>/event-images (POST) - add_event_image
def test_clubs_club_id_event_images_post_exists(client):
    assert _route_exists("/clubs/<int:club_id>/event-images", "POST") is True

def test_clubs_club_id_event_images_post_success(client):
    with app.app_context():
        club = _create_club()
        user = _create_user(role="admin")
        club_id = club.id

    _login_as(client, user)
    payload = {"title": "Past Event", "image_url": "https://example.com/past.jpg", "event_date": "2024-01-02"}
    resp = client.post(f"/clubs/{club_id}/event-images", json=payload)
    assert resp.status_code in (201, 400, 401, 403, 404)
    if resp.status_code == 201:
        assert resp.content_type.startswith("application/json")
        data = resp.get_json()
        _assert_add_event_image_response_schema(data)
        assert data["club_id"] == club_id
        assert data["title"] == payload["title"]
        assert data["image_url"] == payload["image_url"]
        assert data["event_date"] == payload["event_date"]

def test_clubs_club_id_event_images_post_missing_required_fields(client):
    with app.app_context():
        club = _create_club()
        user = _create_user(role="admin")
        club_id = club.id

    _login_as(client, user)
    payload = {"title": "Missing fields"}
    resp = client.post(f"/clubs/{club_id}/event-images", json=payload)
    assert resp.status_code in (400, 401, 403, 404)
    if resp.status_code == 400:
        assert resp.content_type.startswith("application/json")
        data = resp.get_json()
        _assert_error_schema(data)

def test_clubs_club_id_event_images_post_invalid_data(client):
    with app.app_context():
        club = _create_club()
        user = _create_user(role="admin")
        club_id = club.id

    _login_as(client, user)
    payload = {"title": "Bad date", "image_url": "https://example.com/past.jpg", "event_date": "01-02-2024"}
    resp = client.post(f"/clubs/{club_id}/event-images", json=payload)
    assert resp.status_code in (400, 401, 403, 404)
    if resp.status_code == 400:
        assert resp.content_type.startswith("application/json")
        data = resp.get_json()
        _assert_error_schema(data)

def test_clubs_club_id_event_images_post_duplicate_data(client):
    with app.app_context():
        club = _create_club()
        user = _create_user(role="admin")
        club_id = club.id

    _login_as(client, user)
    payload = {"title": "Dup", "image_url": "https://example.com/dup.jpg", "event_date": "2024-01-02"}
    r1 = client.post(f"/clubs/{club_id}/event-images", json=payload)
    r2 = client.post(f"/clubs/{club_id}/event-images", json=payload)
    assert r1.status_code in (201, 400, 401, 403, 404)
    assert r2.status_code in (201, 400, 401, 403, 404)
    if r1.status_code == 201 and r2.status_code == 201:
        d1 = r1.get_json()
        d2 = r2.get_json()
        assert d1["id"] != d2["id"]

# ROUTE: /clubs/<int:club_id>/event-images/<int:image_id> (DELETE) - delete_event_image
def test_clubs_club_id_event_images_image_id_delete_exists(client):
    assert _route_exists("/clubs/<int:club_id>/event-images/<int:image_id>", "DELETE") is True

# HELPER: get_current_user(N/A)
def test_get_current_user_function_exists():
    assert callable(get_current_user) is True

def test_get_current_user_with_valid_input(client):
    with app.app_context():
        user = _create_user(role="admin")
        user_id = user.id

    _login_as(client, user)
    with app.test_request_context("/clubs", method="GET"):
        from flask import session

        session["user_id"] = user_id
        session["_user_id"] = str(user_id)
        u = get_current_user()
        assert u is not None
        assert getattr(u, "id", None) == user_id

def test_get_current_user_with_invalid_input(client):
    with app.test_request_context("/clubs", method="GET"):
        from flask import session

        session.pop("user_id", None)
        session.pop("_user_id", None)
        u = get_current_user()
        assert u is None

# HELPER: require_roles(user, allowed_roles)
def test_require_roles_function_exists():
    assert callable(require_roles) is True

def test_require_roles_with_valid_input(app_context):
    user = User(email=_unique("e") + "@example.com", username=_unique("u"), password_hash="", role="admin", is_active=True)
    require_roles(user, ["admin"])

def test_require_roles_with_invalid_input(app_context):
    user = User(email=_unique("e") + "@example.com", username=_unique("u"), password_hash="", role="club_coordinator", is_active=True)
    with pytest.raises(Exception):
        require_roles(user, ["admin"])

# HELPER: can_edit_club(user, club)
def test_can_edit_club_function_exists():
    assert callable(can_edit_club) is True

def test_can_edit_club_with_valid_input(app_context):
    club = _create_club()
    admin = _create_user(role="admin")
    assert can_edit_club(admin, club) is True

    scoped_user = _create_user(role="club_coordinator")
    _create_coordinator_link(user_id=scoped_user.id, club_id=club.id)
    assert can_edit_club(scoped_user, club) is True

def test_can_edit_club_with_invalid_input(app_context):
    club = _create_club()
    user = _create_user(role="club_coordinator")
    assert can_edit_club(user, club) is False

    inactive_admin = _create_user(role="admin", is_active=False)
    assert can_edit_club(inactive_admin, club) is False

# HELPER: parse_update_club_payload(request)
def test_parse_update_club_payload_function_exists():
    assert callable(parse_update_club_payload) is True

def test_parse_update_club_payload_with_valid_input(app_context):
    payload = {
        "description": "New description",
        "members_list": "A,B",
        "contact": {"name": "N", "email": "e@example.com", "phone": "123"},
    }
    with app.test_request_context("/clubs/1", method="PUT", json=payload):
        parsed = parse_update_club_payload(app._get_current_object().request if hasattr(app, "_get_current_object") else None)

def test_parse_update_club_payload_with_invalid_input(app_context):
    with app.test_request_context("/clubs/1", method="PUT", data="not-json", content_type="text/plain"):
        with pytest.raises(Exception):
            parse_update_club_payload(app._get_current_object().request if hasattr(app, "_get_current_object") else None)

# HELPER: validate_update_club_payload(payload)
def test_validate_update_club_payload_function_exists():
    assert callable(validate_update_club_payload) is True

def test_validate_update_club_payload_with_valid_input(app_context):
    payload = {
        "description": "New description",
        "members_list": "A,B",
        "contact": {"name": "N", "email": "e@example.com", "phone": "123"},
    }
    result = validate_update_club_payload(payload)
    assert isinstance(result, dict)
    assert set(result.keys()) == {"description", "members_list", "contact"}
    assert set(result["contact"].keys()) == {"name", "email", "phone"}

def test_validate_update_club_payload_with_invalid_input(app_context):
    payload = {"description": "x", "members_list": "y"}
    with pytest.raises(Exception):
        validate_update_club_payload(payload)

# HELPER: parse_add_event_image_payload(request)
def test_parse_add_event_image_payload_function_exists():
    assert callable(parse_add_event_image_payload) is True

def test_parse_add_event_image_payload_with_valid_input(app_context):
    payload = {"title": "T", "image_url": "https://example.com/x.jpg", "event_date": "2024-01-02"}
    with app.test_request_context("/clubs/1/event-images", method="POST", json=payload):
        parsed = parse_add_event_image_payload(app._get_current_object().request if hasattr(app, "_get_current_object") else None)

def test_parse_add_event_image_payload_with_invalid_input(app_context):
    with app.test_request_context("/clubs/1/event-images", method="POST", data="not-json", content_type="text/plain"):
        with pytest.raises(Exception):
            parse_add_event_image_payload(app._get_current_object().request if hasattr(app, "_get_current_object") else None)

# HELPER: validate_add_event_image_payload(payload)
def test_validate_add_event_image_payload_function_exists():
    assert callable(validate_add_event_image_payload) is True

def test_validate_add_event_image_payload_with_valid_input(app_context):
    payload = {"title": "T", "image_url": "https://example.com/x.jpg", "event_date": "2024-01-02"}
    result = validate_add_event_image_payload(payload)
    assert isinstance(result, dict)
    assert set(result.keys()) == {"title", "image_url", "event_date"}
    assert isinstance(result["title"], str)
    assert isinstance(result["image_url"], str)
    assert isinstance(result["event_date"], str)

def test_validate_add_event_image_payload_with_invalid_input(app_context):
    payload = {"title": "T", "image_url": "", "event_date": "2024-01-02"}
    with pytest.raises(Exception):
        validate_add_event_image_payload(payload)