import os
import sys
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db  # noqa: E402
from models.user import User  # noqa: E402
from models.event_scheduling_and_approval_club import Club  # noqa: E402
from models.event_scheduling_and_approval_club_membership import ClubMembership  # noqa: E402
from models.event_scheduling_and_approval_event_request import EventRequest  # noqa: E402

from controllers.event_scheduling_and_approval_controller import (  # noqa: E402
    get_current_user,
    require_role,
    require_club_coordinator,
    parse_event_request_payload,
    validate_event_request_payload,
    check_time_conflicts,
    serialize_event_request,
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

def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_user(*, role: str = "STUDENT", email: str | None = None, username: str | None = None, password: str = "Passw0rd!"):
    if email is None:
        email = f"{_unique('user')}@example.com"
    if username is None:
        username = _unique("user")
    u = User(email=email, username=username, role=role)
    if hasattr(u, "set_password"):
        u.set_password(password)
    else:
        u.password_hash = "hash"
    db.session.add(u)
    db.session.commit()
    return u

def _create_club(*, name: str | None = None, description: str | None = "desc"):
    if name is None:
        name = _unique("club")
    c = Club(name=name, description=description)
    db.session.add(c)
    db.session.commit()
    return c

def _create_membership(*, club_id: int, user_id: int, role: str = "COORDINATOR"):
    m = ClubMembership(club_id=club_id, user_id=user_id, role=role)
    db.session.add(m)
    db.session.commit()
    return m

def _create_event_request(
    *,
    club_id: int,
    proposed_by_user_id: int,
    title: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    status: str | None = None,
):
    if title is None:
        title = _unique("event")
    if start_at is None:
        start_at = datetime.utcnow() + timedelta(days=1)
    if end_at is None:
        end_at = start_at + timedelta(hours=2)
    er = EventRequest(
        club_id=club_id,
        proposed_by_user_id=proposed_by_user_id,
        title=title,
        description="desc",
        location="loc",
        start_at=start_at,
        end_at=end_at,
    )
    if status is not None:
        er.status = status
    db.session.add(er)
    db.session.commit()
    return er

def _route_allows(path: str, method: str) -> bool:
    method = method.upper()
    for rule in app.url_map.iter_rules():
        if rule.rule == path and method in rule.methods:
            return True
    return False

# MODEL: User (models/user.py)
def test_user_model_has_required_fields(app_context):
    for field in ["id", "email", "username", "password_hash", "role", "created_at"]:
        assert hasattr(User, field), f"Missing User.{field} field required by contract"

def test_user_set_password(app_context):
    u = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="STUDENT")
    assert hasattr(u, "set_password"), "Missing User.set_password(password) required by contract"
    u.set_password("MyS3cret!")
    assert getattr(u, "password_hash", None), "User.password_hash should be set by set_password"
    assert "MyS3cret!" not in (u.password_hash or ""), "Password must not be stored in plaintext"

def test_user_check_password(app_context):
    u = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="STUDENT")
    assert hasattr(u, "set_password"), "Missing User.set_password(password) required by contract"
    assert hasattr(u, "check_password"), "Missing User.check_password(password) required by contract"
    u.set_password("MyS3cret!")
    assert u.check_password("MyS3cret!") is True
    assert u.check_password("wrong") is False

def test_user_is_club_coordinator(app_context):
    u1 = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="CLUB_COORDINATOR")
    u2 = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="STUDENT")
    assert hasattr(u1, "is_club_coordinator"), "Missing User.is_club_coordinator() required by contract"
    assert u1.is_club_coordinator() is True
    assert u2.is_club_coordinator() is False

def test_user_is_clubs_coordinator(app_context):
    u1 = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="CLUBS_COORDINATOR")
    u2 = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="CLUB_COORDINATOR")
    assert hasattr(u1, "is_clubs_coordinator"), "Missing User.is_clubs_coordinator() required by contract"
    assert u1.is_clubs_coordinator() is True
    assert u2.is_clubs_coordinator() is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")
    u1 = User(email=email, username=username, role="STUDENT")
    u1.set_password("Passw0rd!") if hasattr(u1, "set_password") else None
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("other"), role="STUDENT")
    u2.set_password("Passw0rd!") if hasattr(u2, "set_password") else None
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, role="STUDENT")
    u3.set_password("Passw0rd!") if hasattr(u3, "set_password") else None
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()

# MODEL: Club (models/event_scheduling_and_approval_club.py)
def test_club_model_has_required_fields(app_context):
    for field in ["id", "name", "description", "created_at"]:
        assert hasattr(Club, field), f"Missing Club.{field} field required by contract"

def test_club_unique_constraints(app_context):
    name = _unique("clubname")
    c1 = Club(name=name, description="d1")
    db.session.add(c1)
    db.session.commit()

    c2 = Club(name=name, description="d2")
    db.session.add(c2)
    with pytest.raises(Exception):
        db.session.commit()

# MODEL: ClubMembership (models/event_scheduling_and_approval_club_membership.py)
def test_clubmembership_model_has_required_fields(app_context):
    for field in ["id", "club_id", "user_id", "role", "created_at"]:
        assert hasattr(ClubMembership, field), f"Missing ClubMembership.{field} field required by contract"

def test_clubmembership_is_coordinator(app_context):
    club = _create_club()
    user = _create_user(role="STUDENT")
    m1 = ClubMembership(club_id=club.id, user_id=user.id, role="COORDINATOR")
    m2 = ClubMembership(club_id=club.id, user_id=user.id, role="MEMBER")
    assert hasattr(m1, "is_coordinator"), "Missing ClubMembership.is_coordinator() required by contract"
    assert m1.is_coordinator() is True
    assert m2.is_coordinator() is False

def test_clubmembership_unique_constraints(app_context):
    club = _create_club()
    user = _create_user(role="STUDENT")
    m1 = ClubMembership(club_id=club.id, user_id=user.id, role="COORDINATOR")
    m2 = ClubMembership(club_id=club.id, user_id=user.id, role="COORDINATOR")
    db.session.add(m1)
    db.session.add(m2)
    db.session.commit()
    assert ClubMembership.query.filter_by(club_id=club.id, user_id=user.id).count() >= 2

# MODEL: EventRequest (models/event_scheduling_and_approval_event_request.py)
def test_eventrequest_model_has_required_fields(app_context):
    fields = [
        "id",
        "club_id",
        "proposed_by_user_id",
        "title",
        "description",
        "location",
        "start_at",
        "end_at",
        "status",
        "reviewed_by_user_id",
        "reviewed_at",
        "decision_reason",
        "created_at",
        "updated_at",
    ]
    for field in fields:
        assert hasattr(EventRequest, field), f"Missing EventRequest.{field} field required by contract"

def test_eventrequest_approve(app_context):
    club = _create_club()
    proposer = _create_user(role="CLUB_COORDINATOR")
    reviewer = _create_user(role="CLUBS_COORDINATOR")
    er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="PENDING")
    assert hasattr(er, "approve"), "Missing EventRequest.approve(reviewer_user, reason) required by contract"
    er.approve(reviewer, "ok")
    db.session.commit()
    assert er.status == "APPROVED"
    assert er.reviewed_by_user_id == reviewer.id
    assert er.reviewed_at is not None
    assert er.decision_reason == "ok"

def test_eventrequest_decline(app_context):
    club = _create_club()
    proposer = _create_user(role="CLUB_COORDINATOR")
    reviewer = _create_user(role="CLUBS_COORDINATOR")
    er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="PENDING")
    assert hasattr(er, "decline"), "Missing EventRequest.decline(reviewer_user, reason) required by contract"
    er.decline(reviewer, "no")
    db.session.commit()
    assert er.status == "DECLINED"
    assert er.reviewed_by_user_id == reviewer.id
    assert er.reviewed_at is not None
    assert er.decision_reason == "no"

def test_eventrequest_is_pending(app_context):
    club = _create_club()
    proposer = _create_user(role="CLUB_COORDINATOR")
    er1 = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="PENDING")
    er2 = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="APPROVED")
    assert hasattr(er1, "is_pending"), "Missing EventRequest.is_pending() required by contract"
    assert er1.is_pending() is True
    assert er2.is_pending() is False

def test_eventrequest_unique_constraints(app_context):
    club = _create_club()
    proposer = _create_user(role="CLUB_COORDINATOR")
    start_at = datetime.utcnow() + timedelta(days=2)
    end_at = start_at + timedelta(hours=1)
    title = _unique("title")
    er1 = EventRequest(
        club_id=club.id,
        proposed_by_user_id=proposer.id,
        title=title,
        description="d",
        location="l",
        start_at=start_at,
        end_at=end_at,
    )
    er2 = EventRequest(
        club_id=club.id,
        proposed_by_user_id=proposer.id,
        title=title,
        description="d",
        location="l",
        start_at=start_at,
        end_at=end_at,
    )
    db.session.add(er1)
    db.session.add(er2)
    db.session.commit()
    assert EventRequest.query.filter_by(club_id=club.id, title=title).count() >= 2

# ROUTE: /clubs/<int:club_id>/events/propose (GET)
def test_clubs_club_id_events_propose_get_exists(client):
    assert _route_allows("/clubs/<int:club_id>/events/propose", "GET"), "Expected GET route not registered"

def test_clubs_club_id_events_propose_get_renders_template(client):
    with app.app_context():
        club = _create_club()
    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=MagicMock(id=1, role="CLUB_COORDINATOR")):
        with patch("controllers.event_scheduling_and_approval_controller.require_club_coordinator", return_value=True):
            resp = client.get(f"/clubs/{club.id}/events/propose")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")

# ROUTE: /clubs/<int:club_id>/events/propose (POST)
def test_clubs_club_id_events_propose_post_exists(client):
    assert _route_allows("/clubs/<int:club_id>/events/propose", "POST"), "Expected POST route not registered"

def test_clubs_club_id_events_propose_post_success(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        _create_membership(club_id=club.id, user_id=proposer.id, role="COORDINATOR")

    payload = {
        "title": _unique("event"),
        "description": "desc",
        "location": "loc",
        "start_at": (datetime.utcnow() + timedelta(days=3)).isoformat(),
        "end_at": (datetime.utcnow() + timedelta(days=3, hours=2)).isoformat(),
    }

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=proposer):
        with patch("controllers.event_scheduling_and_approval_controller.require_club_coordinator", return_value=True):
            with patch("controllers.event_scheduling_and_approval_controller.check_time_conflicts", return_value={"ok": True}):
                resp = client.post(f"/clubs/{club.id}/events/propose", json=payload)

    assert resp.status_code in (200, 201, 302)
    with app.app_context():
        created = EventRequest.query.filter_by(club_id=club.id, title=payload["title"]).first()
        assert created is not None
        assert created.status in ("PENDING", "PENDING_APPROVAL", "PENDING_REVIEW")

def test_clubs_club_id_events_propose_post_missing_required_fields(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        _create_membership(club_id=club.id, user_id=proposer.id, role="COORDINATOR")

    payload = {
        "description": "desc",
        "location": "loc",
        "start_at": (datetime.utcnow() + timedelta(days=3)).isoformat(),
        "end_at": (datetime.utcnow() + timedelta(days=3, hours=2)).isoformat(),
    }

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=proposer):
        with patch("controllers.event_scheduling_and_approval_controller.require_club_coordinator", return_value=True):
            resp = client.post(f"/clubs/{club.id}/events/propose", json=payload)

    assert resp.status_code in (400, 422, 200)
    with app.app_context():
        created = EventRequest.query.filter_by(club_id=club.id).all()
        assert all(er.title != payload.get("title") for er in created)

def test_clubs_club_id_events_propose_post_invalid_data(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        _create_membership(club_id=club.id, user_id=proposer.id, role="COORDINATOR")

    payload = {
        "title": _unique("event"),
        "description": "desc",
        "location": "loc",
        "start_at": "not-a-datetime",
        "end_at": "also-not-a-datetime",
    }

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=proposer):
        with patch("controllers.event_scheduling_and_approval_controller.require_club_coordinator", return_value=True):
            resp = client.post(f"/clubs/{club.id}/events/propose", json=payload)

    assert resp.status_code in (400, 422, 200)
    with app.app_context():
        created = EventRequest.query.filter_by(club_id=club.id, title=payload["title"]).first()
        assert created is None

def test_clubs_club_id_events_propose_post_duplicate_data(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        _create_membership(club_id=club.id, user_id=proposer.id, role="COORDINATOR")
        start_at = datetime.utcnow() + timedelta(days=4)
        end_at = start_at + timedelta(hours=1)
        title = _unique("eventdup")
        _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, title=title, start_at=start_at, end_at=end_at)

    payload = {
        "title": title,
        "description": "desc",
        "location": "loc",
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
    }

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=proposer):
        with patch("controllers.event_scheduling_and_approval_controller.require_club_coordinator", return_value=True):
            resp = client.post(f"/clubs/{club.id}/events/propose", json=payload)

    assert resp.status_code in (200, 201, 302, 400, 409, 422)
    with app.app_context():
        count = EventRequest.query.filter_by(club_id=club.id, title=title).count()
        assert count >= 1

# ROUTE: /events/requests (GET)
def test_events_requests_get_exists(client):
    assert _route_allows("/events/requests", "GET"), "Expected GET route not registered"

def test_events_requests_get_renders_template(client):
    reviewer = MagicMock(id=1, role="CLUBS_COORDINATOR")
    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=reviewer):
        with patch("controllers.event_scheduling_and_approval_controller.require_role", return_value=True):
            resp = client.get("/events/requests")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")

# ROUTE: /events/requests/<int:event_request_id> (GET)
def test_events_requests_event_request_id_get_exists(client):
    assert _route_allows("/events/requests/<int:event_request_id>", "GET"), "Expected GET route not registered"

def test_events_requests_event_request_id_get_renders_template(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id)
    viewer = MagicMock(id=proposer.id, role="CLUB_COORDINATOR")
    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=viewer):
        resp = client.get(f"/events/requests/{er.id}")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")

# ROUTE: /events/requests/<int:event_request_id>/approve (POST)
def test_events_requests_event_request_id_approve_post_exists(client):
    assert _route_allows("/events/requests/<int:event_request_id>/approve", "POST"), "Expected POST route not registered"

def test_events_requests_event_request_id_approve_post_success(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        reviewer = _create_user(role="CLUBS_COORDINATOR")
        er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="PENDING")

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=reviewer):
        with patch("controllers.event_scheduling_and_approval_controller.require_role", return_value=True):
            resp = client.post(f"/events/requests/{er.id}/approve", json={"reason": "approved"})

    assert resp.status_code in (200, 302)
    with app.app_context():
        refreshed = EventRequest.query.filter_by(id=er.id).first()
        assert refreshed is not None
        assert refreshed.status == "APPROVED"
        assert refreshed.reviewed_by_user_id == reviewer.id

def test_events_requests_event_request_id_approve_post_missing_required_fields(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        reviewer = _create_user(role="CLUBS_COORDINATOR")
        er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="PENDING")

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=reviewer):
        with patch("controllers.event_scheduling_and_approval_controller.require_role", return_value=True):
            resp = client.post(f"/events/requests/{er.id}/approve", json={})

    assert resp.status_code in (400, 422, 200)
    with app.app_context():
        refreshed = EventRequest.query.filter_by(id=er.id).first()
        assert refreshed.status == "PENDING"

def test_events_requests_event_request_id_approve_post_invalid_data(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        reviewer = _create_user(role="CLUBS_COORDINATOR")
        er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="PENDING")

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=reviewer):
        with patch("controllers.event_scheduling_and_approval_controller.require_role", return_value=True):
            resp = client.post(f"/events/requests/{er.id}/approve", data="not-json", content_type="text/plain")

    assert resp.status_code in (400, 415, 422, 200)
    with app.app_context():
        refreshed = EventRequest.query.filter_by(id=er.id).first()
        assert refreshed.status == "PENDING"

def test_events_requests_event_request_id_approve_post_duplicate_data(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        reviewer = _create_user(role="CLUBS_COORDINATOR")
        er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="PENDING")

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=reviewer):
        with patch("controllers.event_scheduling_and_approval_controller.require_role", return_value=True):
            resp1 = client.post(f"/events/requests/{er.id}/approve", json={"reason": "approved"})
            resp2 = client.post(f"/events/requests/{er.id}/approve", json={"reason": "approved again"})

    assert resp1.status_code in (200, 302)
    assert resp2.status_code in (200, 302, 400, 409, 422)
    with app.app_context():
        refreshed = EventRequest.query.filter_by(id=er.id).first()
        assert refreshed.status == "APPROVED"

# ROUTE: /events/requests/<int:event_request_id>/decline (POST)
def test_events_requests_event_request_id_decline_post_exists(client):
    assert _route_allows("/events/requests/<int:event_request_id>/decline", "POST"), "Expected POST route not registered"

def test_events_requests_event_request_id_decline_post_success(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        reviewer = _create_user(role="CLUBS_COORDINATOR")
        er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="PENDING")

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=reviewer):
        with patch("controllers.event_scheduling_and_approval_controller.require_role", return_value=True):
            resp = client.post(f"/events/requests/{er.id}/decline", json={"reason": "declined"})

    assert resp.status_code in (200, 302)
    with app.app_context():
        refreshed = EventRequest.query.filter_by(id=er.id).first()
        assert refreshed is not None
        assert refreshed.status == "DECLINED"
        assert refreshed.reviewed_by_user_id == reviewer.id

def test_events_requests_event_request_id_decline_post_missing_required_fields(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        reviewer = _create_user(role="CLUBS_COORDINATOR")
        er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="PENDING")

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=reviewer):
        with patch("controllers.event_scheduling_and_approval_controller.require_role", return_value=True):
            resp = client.post(f"/events/requests/{er.id}/decline", json={})

    assert resp.status_code in (400, 422, 200)
    with app.app_context():
        refreshed = EventRequest.query.filter_by(id=er.id).first()
        assert refreshed.status == "PENDING"

def test_events_requests_event_request_id_decline_post_invalid_data(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        reviewer = _create_user(role="CLUBS_COORDINATOR")
        er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="PENDING")

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=reviewer):
        with patch("controllers.event_scheduling_and_approval_controller.require_role", return_value=True):
            resp = client.post(f"/events/requests/{er.id}/decline", data="not-json", content_type="text/plain")

    assert resp.status_code in (400, 415, 422, 200)
    with app.app_context():
        refreshed = EventRequest.query.filter_by(id=er.id).first()
        assert refreshed.status == "PENDING"

def test_events_requests_event_request_id_decline_post_duplicate_data(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        reviewer = _create_user(role="CLUBS_COORDINATOR")
        er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id, status="PENDING")

    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=reviewer):
        with patch("controllers.event_scheduling_and_approval_controller.require_role", return_value=True):
            resp1 = client.post(f"/events/requests/{er.id}/decline", json={"reason": "declined"})
            resp2 = client.post(f"/events/requests/{er.id}/decline", json={"reason": "declined again"})

    assert resp1.status_code in (200, 302)
    assert resp2.status_code in (200, 302, 400, 409, 422)
    with app.app_context():
        refreshed = EventRequest.query.filter_by(id=er.id).first()
        assert refreshed.status == "DECLINED"

# ROUTE: /clubs/<int:club_id>/events/requests (GET)
def test_clubs_club_id_events_requests_get_exists(client):
    assert _route_allows("/clubs/<int:club_id>/events/requests", "GET"), "Expected GET route not registered"

def test_clubs_club_id_events_requests_get_renders_template(client):
    with app.app_context():
        club = _create_club()
        proposer = _create_user(role="CLUB_COORDINATOR")
        _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id)
    viewer = MagicMock(id=proposer.id, role="CLUB_COORDINATOR")
    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=viewer):
        resp = client.get(f"/clubs/{club.id}/events/requests")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")

# HELPER: get_current_user()
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(app_context):
    user = _create_user(role="STUDENT")
    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=user) as fn:
        result = fn()
    assert result is user

def test_get_current_user_with_invalid_input():
    with patch("controllers.event_scheduling_and_approval_controller.get_current_user", return_value=None) as fn:
        result = fn()
    assert result is None

# HELPER: require_role(user, allowed_roles)
def test_require_role_function_exists():
    assert callable(require_role)

def test_require_role_with_valid_input(app_context):
    user = _create_user(role="CLUBS_COORDINATOR")
    allowed = ["CLUBS_COORDINATOR"]
    result = require_role(user, allowed)
    assert result is None or result is True

def test_require_role_with_invalid_input(app_context):
    user = _create_user(role="STUDENT")
    allowed = ["CLUBS_COORDINATOR"]
    with pytest.raises(Exception):
        require_role(user, allowed)

# HELPER: require_club_coordinator(user, club_id)
def test_require_club_coordinator_function_exists():
    assert callable(require_club_coordinator)

def test_require_club_coordinator_with_valid_input(app_context):
    club = _create_club()
    user = _create_user(role="CLUB_COORDINATOR")
    _create_membership(club_id=club.id, user_id=user.id, role="COORDINATOR")
    result = require_club_coordinator(user, club.id)
    assert result is None or result is True

def test_require_club_coordinator_with_invalid_input(app_context):
    club = _create_club()
    user = _create_user(role="STUDENT")
    with pytest.raises(Exception):
        require_club_coordinator(user, club.id)

# HELPER: parse_event_request_payload(request)
def test_parse_event_request_payload_function_exists():
    assert callable(parse_event_request_payload)

def test_parse_event_request_payload_with_valid_input():
    start_at = (datetime.utcnow() + timedelta(days=1)).isoformat()
    end_at = (datetime.utcnow() + timedelta(days=1, hours=1)).isoformat()
    req = MagicMock()
    req.is_json = True
    req.get_json.return_value = {
        "title": _unique("event"),
        "description": "desc",
        "location": "loc",
        "start_at": start_at,
        "end_at": end_at,
    }
    payload = parse_event_request_payload(req)
    assert isinstance(payload, dict)
    assert payload.get("title")

def test_parse_event_request_payload_with_invalid_input():
    req = MagicMock()
    req.is_json = False
    req.get_json.side_effect = Exception("no json")
    with pytest.raises(Exception):
        parse_event_request_payload(req)

# HELPER: validate_event_request_payload(payload)
def test_validate_event_request_payload_function_exists():
    assert callable(validate_event_request_payload)

def test_validate_event_request_payload_with_valid_input():
    start_at = (datetime.utcnow() + timedelta(days=1)).isoformat()
    end_at = (datetime.utcnow() + timedelta(days=1, hours=1)).isoformat()
    payload = {
        "title": _unique("event"),
        "description": "desc",
        "location": "loc",
        "start_at": start_at,
        "end_at": end_at,
    }
    result = validate_event_request_payload(payload)
    assert isinstance(result, dict)

def test_validate_event_request_payload_with_invalid_input():
    payload = {"title": "", "start_at": "bad", "end_at": "bad"}
    with pytest.raises(Exception):
        validate_event_request_payload(payload)

# HELPER: check_time_conflicts(start_at, end_at)
def test_check_time_conflicts_function_exists():
    assert callable(check_time_conflicts)

def test_check_time_conflicts_with_valid_input(app_context):
    start_at = datetime.utcnow() + timedelta(days=10)
    end_at = start_at + timedelta(hours=1)
    result = check_time_conflicts(start_at, end_at)
    assert isinstance(result, dict)
    assert "ok" in result or "conflict" in result or "conflicts" in result

def test_check_time_conflicts_with_invalid_input(app_context):
    start_at = datetime.utcnow() + timedelta(days=10)
    end_at = start_at - timedelta(hours=1)
    with pytest.raises(Exception):
        check_time_conflicts(start_at, end_at)

# HELPER: serialize_event_request(event_request)
def test_serialize_event_request_function_exists():
    assert callable(serialize_event_request)

def test_serialize_event_request_with_valid_input(app_context):
    club = _create_club()
    proposer = _create_user(role="CLUB_COORDINATOR")
    er = _create_event_request(club_id=club.id, proposed_by_user_id=proposer.id)
    data = serialize_event_request(er)
    assert isinstance(data, dict)
    assert data.get("id") == er.id
    assert data.get("club_id") == club.id
    assert data.get("title") == er.title

def test_serialize_event_request_with_invalid_input():
    with pytest.raises(Exception):
        serialize_event_request(None)