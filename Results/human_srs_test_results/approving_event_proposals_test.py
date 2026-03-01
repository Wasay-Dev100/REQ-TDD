import os
import sys
import uuid
from datetime import datetime

import pytest
from werkzeug.exceptions import NotFound

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db  # noqa: E402
from models.user import User  # noqa: E402
from models.approving_event_proposals_event_proposal import EventProposal  # noqa: E402
from controllers.approving_event_proposals_controller import (  # noqa: E402
    get_current_user,
    login_required,
    coordinator_required,
    require_manage_access,
    get_pending_proposals,
    get_proposal_or_404,
)
from views.approving_event_proposals_views import (  # noqa: E402
    render_login,
    render_manage_home,
    render_pending_list,
    render_review_page,
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

def _create_user(
    *,
    email=None,
    username=None,
    password="Password123!",
    role="COORDINATOR",
    is_active=True,
):
    email = email or f"{_unique('user')}@example.com"
    username = username or _unique("user")
    user = User(email=email, username=username, role=role, is_active=is_active)
    if hasattr(user, "set_password"):
        user.set_password(password)
    else:
        user.password_hash = password
    db.session.add(user)
    db.session.commit()
    return user

def _create_event_proposal(
    *,
    title=None,
    description="desc",
    proposed_date=None,
    location="Auditorium",
    club_name=None,
    submitted_by_user_id=None,
    status="PENDING",
):
    title = title or _unique("Event")
    club_name = club_name or _unique("Club")
    if proposed_date is None:
        proposed_date = datetime.strptime("2030-01-01", "%Y-%m-%d").date()
    proposal = EventProposal(
        title=title,
        description=description,
        proposed_date=proposed_date,
        location=location,
        club_name=club_name,
        submitted_by_user_id=submitted_by_user_id,
        status=status,
    )
    db.session.add(proposal)
    db.session.commit()
    return proposal

def _login_via_route(client, username_or_email, password):
    return client.post(
        "/login",
        data={"username_or_email": username_or_email, "password": password},
        follow_redirects=False,
    )

def _force_login_session(client, user_id: int):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

def _route_exists(rule: str, method: str) -> bool:
    method = method.upper()
    for r in app.url_map.iter_rules():
        if r.rule == rule and method in r.methods:
            return True
    return False

# -------------------------
# MODEL: User (models/user.py)
# -------------------------

def test_user_model_has_required_fields(app_context):
    user = User()
    for field in ["id", "email", "username", "password_hash", "role", "is_active", "created_at"]:
        assert hasattr(user, field), f"Missing required User field: {field}"

def test_user_set_password(app_context):
    user = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="COORDINATOR")
    user.set_password("Secret123!")
    assert user.password_hash is not None
    assert user.password_hash != "Secret123!"

def test_user_check_password(app_context):
    user = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="COORDINATOR")
    user.set_password("Secret123!")
    assert user.check_password("Secret123!") is True
    assert user.check_password("WrongPassword!") is False

def test_user_is_coordinator(app_context):
    u1 = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="COORDINATOR")
    u2 = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="STUDENT")
    assert u1.is_coordinator() is True
    assert u2.is_coordinator() is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")
    u1 = User(email=email, username=username, role="COORDINATOR")
    u1.set_password("Secret123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("other"), role="COORDINATOR")
    u2.set_password("Secret123!")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, role="COORDINATOR")
    u3.set_password("Secret123!")
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# -----------------------------------------------
# MODEL: EventProposal (models/approving_event_proposals_event_proposal.py)
# -----------------------------------------------

def test_eventproposal_model_has_required_fields(app_context):
    proposal = EventProposal()
    fields = [
        "id",
        "title",
        "description",
        "proposed_date",
        "location",
        "club_name",
        "submitted_by_user_id",
        "status",
        "reviewed_by_user_id",
        "review_decision",
        "review_comment",
        "reviewed_at",
        "created_at",
        "updated_at",
    ]
    for field in fields:
        assert hasattr(proposal, field), f"Missing required EventProposal field: {field}"

def test_eventproposal_approve(app_context):
    reviewer = _create_user(role="COORDINATOR")
    submitter = _create_user(role="STUDENT")
    proposal = _create_event_proposal(submitted_by_user_id=submitter.id, status="PENDING")

    proposal.approve(reviewer, comment="Looks good")
    db.session.commit()

    refreshed = EventProposal.query.filter_by(id=proposal.id).first()
    assert refreshed is not None
    assert refreshed.status in ("APPROVED", "APPROVE", "APPROVED".upper())
    assert refreshed.reviewed_by_user_id == reviewer.id
    assert refreshed.review_decision is not None
    assert str(refreshed.review_decision).upper() in ("APPROVED", "APPROVE")
    assert refreshed.review_comment == "Looks good"
    assert refreshed.reviewed_at is not None

def test_eventproposal_reject(app_context):
    reviewer = _create_user(role="COORDINATOR")
    submitter = _create_user(role="STUDENT")
    proposal = _create_event_proposal(submitted_by_user_id=submitter.id, status="PENDING")

    proposal.reject(reviewer, comment="Insufficient details")
    db.session.commit()

    refreshed = EventProposal.query.filter_by(id=proposal.id).first()
    assert refreshed is not None
    assert refreshed.status in ("REJECTED", "REJECT", "REJECTED".upper())
    assert refreshed.reviewed_by_user_id == reviewer.id
    assert refreshed.review_decision is not None
    assert str(refreshed.review_decision).upper() in ("REJECTED", "REJECT")
    assert refreshed.review_comment == "Insufficient details"
    assert refreshed.reviewed_at is not None

def test_eventproposal_is_pending(app_context):
    p1 = _create_event_proposal(status="PENDING")
    p2 = _create_event_proposal(status="APPROVED")
    assert p1.is_pending() is True
    assert p2.is_pending() is False

def test_eventproposal_unique_constraints(app_context):
    p1 = _create_event_proposal(title=_unique("t"), club_name=_unique("c"))
    p2 = _create_event_proposal(title=p1.title, club_name=p1.club_name)
    assert p1.id is not None
    assert p2.id is not None

# -------------------------
# ROUTE: /login (GET)
# -------------------------

def test_login_get_exists(client):
    assert _route_exists("/login", "GET"), "Expected GET /login route to exist"

def test_login_get_renders_template(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    body = (resp.data or b"").lower()
    assert b"login" in body or b"password" in body or b"username" in body

# -------------------------
# ROUTE: /login (POST)
# -------------------------

def test_login_post_exists(client):
    assert _route_exists("/login", "POST"), "Expected POST /login route to exist"

def test_login_post_success(client):
    password = "Secret123!"
    user = _create_user(password=password, role="COORDINATOR")
    resp = _login_via_route(client, user.username, password)
    assert resp.status_code in (200, 302)

    if resp.status_code == 302:
        with client.session_transaction() as sess:
            assert sess.get("user_id") == user.id or sess.get("_user_id") == str(user.id)

def test_login_post_missing_required_fields(client):
    resp = client.post("/login", data={}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)

def test_login_post_invalid_data(client):
    resp = client.post(
        "/login",
        data={"username_or_email": "not-an-email", "password": ""},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 401, 422)

def test_login_post_duplicate_data(client):
    password = "Secret123!"
    u1 = _create_user(password=password, role="COORDINATOR")
    u2 = _create_user(password=password, role="COORDINATOR")
    resp = _login_via_route(client, u1.username, password)
    assert resp.status_code in (200, 302)
    resp2 = _login_via_route(client, u2.username, password)
    assert resp2.status_code in (200, 302)

# -------------------------
# ROUTE: /logout (POST)
# -------------------------

def test_logout_post_exists(client):
    assert _route_exists("/logout", "POST"), "Expected POST /logout route to exist"

def test_logout_post_success(client):
    user = _create_user(role="COORDINATOR")
    _force_login_session(client, user.id)
    resp = client.post("/logout", data={}, follow_redirects=False)
    assert resp.status_code in (200, 302)

def test_logout_post_missing_required_fields(client):
    resp = client.post("/logout", data={}, follow_redirects=False)
    assert resp.status_code in (200, 302, 401, 403)

def test_logout_post_invalid_data(client):
    resp = client.post("/logout", data={"unexpected": "value"}, follow_redirects=False)
    assert resp.status_code in (200, 302, 400, 401, 403)

def test_logout_post_duplicate_data(client):
    user = _create_user(role="COORDINATOR")
    _force_login_session(client, user.id)
    resp1 = client.post("/logout", data={}, follow_redirects=False)
    assert resp1.status_code in (200, 302)
    resp2 = client.post("/logout", data={}, follow_redirects=False)
    assert resp2.status_code in (200, 302, 401, 403)

# -------------------------
# ROUTE: /manage (GET)
# -------------------------

def test_manage_get_exists(client):
    assert _route_exists("/manage", "GET"), "Expected GET /manage route to exist"

def test_manage_get_renders_template(client):
    user = _create_user(role="COORDINATOR")
    _force_login_session(client, user.id)
    resp = client.get("/manage")
    assert resp.status_code in (200, 302, 401, 403)
    if resp.status_code == 200:
        body = (resp.data or b"").lower()
        assert b"manage" in body or b"pending" in body or b"event" in body

# -------------------------------------------------
# ROUTE: /manage/pending-event-requests (GET)
# -------------------------------------------------

def test_manage_pending_event_requests_get_exists(client):
    assert _route_exists(
        "/manage/pending-event-requests", "GET"
    ), "Expected GET /manage/pending-event-requests route to exist"

def test_manage_pending_event_requests_get_renders_template(client):
    user = _create_user(role="COORDINATOR")
    _force_login_session(client, user.id)
    _create_event_proposal(status="PENDING")
    resp = client.get("/manage/pending-event-requests")
    assert resp.status_code in (200, 302, 401, 403)
    if resp.status_code == 200:
        body = (resp.data or b"").lower()
        assert b"pending" in body or b"event" in body or b"proposal" in body

# -------------------------------------------------------------------
# ROUTE: /manage/pending-event-requests/<int:proposal_id> (GET)
# -------------------------------------------------------------------

def test_manage_pending_event_requests_proposal_id_get_exists(client):
    assert _route_exists(
        "/manage/pending-event-requests/<int:proposal_id>", "GET"
    ), "Expected GET /manage/pending-event-requests/<int:proposal_id> route to exist"

def test_manage_pending_event_requests_proposal_id_get_renders_template(client):
    user = _create_user(role="COORDINATOR")
    _force_login_session(client, user.id)
    proposal = _create_event_proposal(status="PENDING")
    resp = client.get(f"/manage/pending-event-requests/{proposal.id}")
    assert resp.status_code in (200, 302, 401, 403, 404)
    if resp.status_code == 200:
        body = (resp.data or b"").lower()
        assert b"review" in body or b"approve" in body or b"reject" in body or b"proposal" in body

# --------------------------------------------------------------------------------
# ROUTE: /manage/pending-event-requests/<int:proposal_id>/approve (POST)
# --------------------------------------------------------------------------------

def test_manage_pending_event_requests_proposal_id_approve_post_exists(client):
    assert _route_exists(
        "/manage/pending-event-requests/<int:proposal_id>/approve", "POST"
    ), "Expected POST /manage/pending-event-requests/<int:proposal_id>/approve route to exist"

def test_manage_pending_event_requests_proposal_id_approve_post_success(client):
    reviewer = _create_user(role="COORDINATOR")
    _force_login_session(client, reviewer.id)
    proposal = _create_event_proposal(status="PENDING")
    resp = client.post(
        f"/manage/pending-event-requests/{proposal.id}/approve",
        data={"comment": "Approved"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302, 400, 401, 403)

    refreshed = EventProposal.query.filter_by(id=proposal.id).first()
    assert refreshed is not None
    if resp.status_code in (200, 302):
        assert str(refreshed.status).upper() != "PENDING"

def test_manage_pending_event_requests_proposal_id_approve_post_missing_required_fields(client):
    reviewer = _create_user(role="COORDINATOR")
    _force_login_session(client, reviewer.id)
    proposal = _create_event_proposal(status="PENDING")
    resp = client.post(
        f"/manage/pending-event-requests/{proposal.id}/approve",
        data={},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302, 400, 422)

def test_manage_pending_event_requests_proposal_id_approve_post_invalid_data(client):
    reviewer = _create_user(role="COORDINATOR")
    _force_login_session(client, reviewer.id)
    proposal = _create_event_proposal(status="PENDING")
    resp = client.post(
        f"/manage/pending-event-requests/{proposal.id}/approve",
        data={"comment": 12345},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302, 400, 422)

def test_manage_pending_event_requests_proposal_id_approve_post_duplicate_data(client):
    reviewer = _create_user(role="COORDINATOR")
    _force_login_session(client, reviewer.id)
    proposal = _create_event_proposal(status="PENDING")
    resp1 = client.post(
        f"/manage/pending-event-requests/{proposal.id}/approve",
        data={"comment": "Approved once"},
        follow_redirects=False,
    )
    assert resp1.status_code in (200, 302, 400, 401, 403)

    resp2 = client.post(
        f"/manage/pending-event-requests/{proposal.id}/approve",
        data={"comment": "Approved twice"},
        follow_redirects=False,
    )
    assert resp2.status_code in (200, 302, 400, 401, 403)

# --------------------------------------------------------------------------------
# ROUTE: /manage/pending-event-requests/<int:proposal_id>/reject (POST)
# --------------------------------------------------------------------------------

def test_manage_pending_event_requests_proposal_id_reject_post_exists(client):
    assert _route_exists(
        "/manage/pending-event-requests/<int:proposal_id>/reject", "POST"
    ), "Expected POST /manage/pending-event-requests/<int:proposal_id>/reject route to exist"

def test_manage_pending_event_requests_proposal_id_reject_post_success(client):
    reviewer = _create_user(role="COORDINATOR")
    _force_login_session(client, reviewer.id)
    proposal = _create_event_proposal(status="PENDING")
    resp = client.post(
        f"/manage/pending-event-requests/{proposal.id}/reject",
        data={"comment": "Rejected"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302, 400, 401, 403)

    refreshed = EventProposal.query.filter_by(id=proposal.id).first()
    assert refreshed is not None
    if resp.status_code in (200, 302):
        assert str(refreshed.status).upper() != "PENDING"

def test_manage_pending_event_requests_proposal_id_reject_post_missing_required_fields(client):
    reviewer = _create_user(role="COORDINATOR")
    _force_login_session(client, reviewer.id)
    proposal = _create_event_proposal(status="PENDING")
    resp = client.post(
        f"/manage/pending-event-requests/{proposal.id}/reject",
        data={},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302, 400, 422)

def test_manage_pending_event_requests_proposal_id_reject_post_invalid_data(client):
    reviewer = _create_user(role="COORDINATOR")
    _force_login_session(client, reviewer.id)
    proposal = _create_event_proposal(status="PENDING")
    resp = client.post(
        f"/manage/pending-event-requests/{proposal.id}/reject",
        data={"comment": 12345},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302, 400, 422)

def test_manage_pending_event_requests_proposal_id_reject_post_duplicate_data(client):
    reviewer = _create_user(role="COORDINATOR")
    _force_login_session(client, reviewer.id)
    proposal = _create_event_proposal(status="PENDING")
    resp1 = client.post(
        f"/manage/pending-event-requests/{proposal.id}/reject",
        data={"comment": "Rejected once"},
        follow_redirects=False,
    )
    assert resp1.status_code in (200, 302, 400, 401, 403)

    resp2 = client.post(
        f"/manage/pending-event-requests/{proposal.id}/reject",
        data={"comment": "Rejected twice"},
        follow_redirects=False,
    )
    assert resp2.status_code in (200, 302, 400, 401, 403)

# -------------------------
# HELPER: get_current_user()
# -------------------------

def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(client):
    user = _create_user(role="COORDINATOR")
    _force_login_session(client, user.id)
    with app.test_request_context("/manage", method="GET"):
        with client.session_transaction() as sess:
            for k, v in sess.items():
                from flask import session as flask_session

                flask_session[k] = v
        current = get_current_user()
        assert current is None or isinstance(current, User)

def test_get_current_user_with_invalid_input(client):
    _force_login_session(client, 999999)
    with app.test_request_context("/manage", method="GET"):
        with client.session_transaction() as sess:
            for k, v in sess.items():
                from flask import session as flask_session

                flask_session[k] = v
        current = get_current_user()
        assert current is None or isinstance(current, User)

# -------------------------
# HELPER: login_required(view_func)
# -------------------------

def test_login_required_function_exists():
    assert callable(login_required)

def test_login_required_with_valid_input():
    def dummy():
        return "ok"

    wrapped = login_required(dummy)
    assert callable(wrapped)

def test_login_required_with_invalid_input():
    with pytest.raises(Exception):
        login_required(None)

# -------------------------
# HELPER: coordinator_required(view_func)
# -------------------------

def test_coordinator_required_function_exists():
    assert callable(coordinator_required)

def test_coordinator_required_with_valid_input():
    def dummy():
        return "ok"

    wrapped = coordinator_required(dummy)
    assert callable(wrapped)

def test_coordinator_required_with_invalid_input():
    with pytest.raises(Exception):
        coordinator_required(None)

# -------------------------
# HELPER: require_manage_access(user)
# -------------------------

def test_require_manage_access_function_exists():
    assert callable(require_manage_access)

def test_require_manage_access_with_valid_input(app_context):
    coordinator = _create_user(role="COORDINATOR")
    result = require_manage_access(coordinator)
    assert isinstance(result, bool)

def test_require_manage_access_with_invalid_input():
    result = require_manage_access(None)
    assert isinstance(result, bool)
    assert result is False

# -------------------------
# HELPER: get_pending_proposals()
# -------------------------

def test_get_pending_proposals_function_exists():
    assert callable(get_pending_proposals)

def test_get_pending_proposals_with_valid_input(app_context):
    _create_event_proposal(status="PENDING")
    _create_event_proposal(status="APPROVED")
    proposals = get_pending_proposals()
    assert isinstance(proposals, list)
    for p in proposals:
        assert isinstance(p, EventProposal)
        assert str(p.status).upper() == "PENDING"

def test_get_pending_proposals_with_invalid_input(app_context):
    proposals = get_pending_proposals()
    assert isinstance(proposals, list)

# -------------------------
# HELPER: get_proposal_or_404(proposal_id)
# -------------------------

def test_get_proposal_or_404_function_exists():
    assert callable(get_proposal_or_404)

def test_get_proposal_or_404_with_valid_input(app_context):
    proposal = _create_event_proposal(status="PENDING")
    found = get_proposal_or_404(proposal.id)
    assert isinstance(found, EventProposal)
    assert found.id == proposal.id

def test_get_proposal_or_404_with_invalid_input(app_context):
    with pytest.raises((NotFound, Exception)):
        get_proposal_or_404(999999)

# -------------------------
# VIEW LAYER: render_* functions exist and return str
# -------------------------

def test_render_login_returns_str():
    out = render_login(error=None)
    assert isinstance(out, str)

def test_render_manage_home_returns_str(app_context):
    user = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="COORDINATOR")
    out = render_manage_home(user)
    assert isinstance(out, str)

def test_render_pending_list_returns_str(app_context):
    user = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="COORDINATOR")
    proposals = []
    out = render_pending_list(user, proposals)
    assert isinstance(out, str)

def test_render_review_page_returns_str(app_context):
    user = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="COORDINATOR")
    proposal = EventProposal()
    out = render_review_page(user, proposal, error=None)
    assert isinstance(out, str)