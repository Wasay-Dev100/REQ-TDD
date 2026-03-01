import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.approving_new_club_requests_club_proposal import ClubProposal
from controllers.approving_new_club_requests_controller import (
    get_current_user,
    require_login,
    require_manage_access,
    require_role,
    parse_decision_payload,
    serialize_club_proposal,
)
from views.approving_new_club_requests_views import render_pending_list, render_proposal_detail

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

def _create_user(*, role: str = "STUDENT", is_active: bool = True) -> User:
    u = User(
        email=f"{_unique('user')}@example.com",
        username=_unique("user"),
        role=role,
        is_active=is_active,
    )
    u.set_password("Password123!")
    db.session.add(u)
    db.session.commit()
    return u

def _create_proposal(*, proposed_by_user_id: int, status: str = "PENDING_COORDINATOR") -> ClubProposal:
    p = ClubProposal(
        proposed_name=_unique("club"),
        description="A club description",
        mission_statement="A mission statement",
        proposed_by_user_id=proposed_by_user_id,
        status=status,
    )
    db.session.add(p)
    db.session.commit()
    return p

def _login_as(client, user: User):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["role"] = user.role
        sess["is_authenticated"] = True

def _route_exists(rule: str, method: str) -> bool:
    for r in app.url_map.iter_rules():
        if r.rule == rule and method in r.methods:
            return True
    return False

# =========================
# MODEL: User (models/user.py)
# =========================
def test_user_model_has_required_fields(app_context):
    required = ["id", "email", "username", "password_hash", "role", "is_active", "created_at"]
    for field in required:
        assert hasattr(User, field), f"Missing required User field: {field}"

def test_user_set_password(app_context):
    user = User(email=f"{_unique('e')}@example.com", username=_unique("u"), role="STUDENT", is_active=True)
    user.set_password("Password123!")
    assert user.password_hash
    assert user.password_hash != "Password123!"

def test_user_check_password(app_context):
    user = User(email=f"{_unique('e')}@example.com", username=_unique("u"), role="STUDENT", is_active=True)
    user.set_password("Password123!")
    assert user.check_password("Password123!") is True
    assert user.check_password("WrongPassword!") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")

    u1 = User(email=email, username=username, role="STUDENT", is_active=True)
    u1.set_password("Password123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("otheruser"), role="STUDENT", is_active=True)
    u2.set_password("Password123!")
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, role="STUDENT", is_active=True)
    u3.set_password("Password123!")
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# ==========================================
# MODEL: ClubProposal (models/..._club_proposal.py)
# ==========================================
def test_clubproposal_model_has_required_fields(app_context):
    required = [
        "id",
        "proposed_name",
        "description",
        "mission_statement",
        "proposed_by_user_id",
        "status",
        "coordinator_reviewed_by_user_id",
        "coordinator_reviewed_at",
        "coordinator_decision",
        "coordinator_notes",
        "admin_reviewed_by_user_id",
        "admin_reviewed_at",
        "admin_decision",
        "admin_notes",
        "created_at",
        "updated_at",
    ]
    for field in required:
        assert hasattr(ClubProposal, field), f"Missing required ClubProposal field: {field}"

def test_clubproposal_can_be_seen_by_admin(app_context):
    proposer = _create_user(role="STUDENT")
    proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")

    assert hasattr(proposal, "can_be_seen_by_admin")
    assert callable(proposal.can_be_seen_by_admin)

    visible_initial = proposal.can_be_seen_by_admin()
    assert visible_initial is False

    coordinator = _create_user(role="COORDINATOR")
    proposal.apply_coordinator_decision(coordinator, "APPROVE", "ok")
    db.session.commit()

    visible_after = proposal.can_be_seen_by_admin()
    assert visible_after is True

def test_clubproposal_apply_coordinator_decision(app_context):
    proposer = _create_user(role="STUDENT")
    coordinator = _create_user(role="COORDINATOR")
    proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")

    before_updated = proposal.updated_at
    proposal.apply_coordinator_decision(coordinator, "APPROVE", "Looks good")
    db.session.commit()
    db.session.refresh(proposal)

    assert proposal.coordinator_reviewed_by_user_id == coordinator.id
    assert proposal.coordinator_decision == "APPROVE"
    assert proposal.coordinator_notes == "Looks good"
    assert proposal.coordinator_reviewed_at is not None
    assert proposal.status != "PENDING_COORDINATOR"
    assert proposal.updated_at is not None
    if before_updated is not None:
        assert proposal.updated_at >= before_updated

def test_clubproposal_apply_admin_decision(app_context):
    proposer = _create_user(role="STUDENT")
    coordinator = _create_user(role="COORDINATOR")
    admin = _create_user(role="ADMIN")
    proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")

    proposal.apply_coordinator_decision(coordinator, "APPROVE", "ok")
    db.session.commit()

    before_updated = proposal.updated_at
    proposal.apply_admin_decision(admin, "APPROVE", "Approved by admin")
    db.session.commit()
    db.session.refresh(proposal)

    assert proposal.admin_reviewed_by_user_id == admin.id
    assert proposal.admin_decision == "APPROVE"
    assert proposal.admin_notes == "Approved by admin"
    assert proposal.admin_reviewed_at is not None
    assert proposal.status not in ("PENDING_COORDINATOR", "PENDING_ADMIN")
    assert proposal.updated_at is not None
    if before_updated is not None:
        assert proposal.updated_at >= before_updated

def test_clubproposal_unique_constraints(app_context):
    proposer = _create_user(role="STUDENT")
    name = _unique("uniqueclub")

    p1 = ClubProposal(
        proposed_name=name,
        description="d1",
        mission_statement="m1",
        proposed_by_user_id=proposer.id,
        status="PENDING_COORDINATOR",
    )
    db.session.add(p1)
    db.session.commit()

    p2 = ClubProposal(
        proposed_name=name,
        description="d2",
        mission_statement="m2",
        proposed_by_user_id=proposer.id,
        status="PENDING_COORDINATOR",
    )
    db.session.add(p2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# ==========================================
# ROUTE: /manage/pending-new-club-requests (GET)
# ==========================================
def test_manage_pending_new_club_requests_get_exists(app_context):
    assert _route_exists("/manage/pending-new-club-requests", "GET"), "Route GET /manage/pending-new-club-requests missing"

def test_manage_pending_new_club_requests_get_renders_template(client):
    coordinator = None
    with app.app_context():
        coordinator = _create_user(role="COORDINATOR")
    _login_as(client, coordinator)

    resp = client.get("/manage/pending-new-club-requests")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# =========================================================
# ROUTE: /manage/pending-new-club-requests/<int:proposal_id> (GET)
# =========================================================
def test_manage_pending_new_club_requests_proposal_id_get_exists(app_context):
    assert _route_exists(
        "/manage/pending-new-club-requests/<int:proposal_id>", "GET"
    ), "Route GET /manage/pending-new-club-requests/<int:proposal_id> missing"

def test_manage_pending_new_club_requests_proposal_id_get_renders_template(client):
    with app.app_context():
        coordinator = _create_user(role="COORDINATOR")
        proposer = _create_user(role="STUDENT")
        proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")
        proposal_id = proposal.id

    _login_as(client, coordinator)
    resp = client.get(f"/manage/pending-new-club-requests/{proposal_id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# ==================================================================================
# ROUTE: /manage/pending-new-club-requests/<int:proposal_id>/coordinator-decision (POST)
# ==================================================================================
def test_manage_pending_new_club_requests_proposal_id_coordinator_decision_post_exists(app_context):
    assert _route_exists(
        "/manage/pending-new-club-requests/<int:proposal_id>/coordinator-decision", "POST"
    ), "Route POST /manage/pending-new-club-requests/<int:proposal_id>/coordinator-decision missing"

def test_manage_pending_new_club_requests_proposal_id_coordinator_decision_post_success(client):
    with app.app_context():
        coordinator = _create_user(role="COORDINATOR")
        proposer = _create_user(role="STUDENT")
        proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")
        proposal_id = proposal.id

    _login_as(client, coordinator)
    resp = client.post(
        f"/manage/pending-new-club-requests/{proposal_id}/coordinator-decision",
        json={"decision": "APPROVE", "notes": "ok"},
    )
    assert resp.status_code in (200, 201, 302)

    with app.app_context():
        updated = ClubProposal.query.filter_by(id=proposal_id).first()
        assert updated is not None
        assert updated.coordinator_decision == "APPROVE"
        assert updated.coordinator_reviewed_by_user_id == coordinator.id
        assert updated.coordinator_reviewed_at is not None

def test_manage_pending_new_club_requests_proposal_id_coordinator_decision_post_missing_required_fields(client):
    with app.app_context():
        coordinator = _create_user(role="COORDINATOR")
        proposer = _create_user(role="STUDENT")
        proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")
        proposal_id = proposal.id

    _login_as(client, coordinator)
    resp = client.post(
        f"/manage/pending-new-club-requests/{proposal_id}/coordinator-decision",
        json={"notes": "missing decision"},
    )
    assert resp.status_code in (400, 422)

def test_manage_pending_new_club_requests_proposal_id_coordinator_decision_post_invalid_data(client):
    with app.app_context():
        coordinator = _create_user(role="COORDINATOR")
        proposer = _create_user(role="STUDENT")
        proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")
        proposal_id = proposal.id

    _login_as(client, coordinator)
    resp = client.post(
        f"/manage/pending-new-club-requests/{proposal_id}/coordinator-decision",
        json={"decision": "NOT_A_VALID_DECISION", "notes": "x"},
    )
    assert resp.status_code in (400, 422)

def test_manage_pending_new_club_requests_proposal_id_coordinator_decision_post_duplicate_data(client):
    with app.app_context():
        coordinator = _create_user(role="COORDINATOR")
        proposer = _create_user(role="STUDENT")
        proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")
        proposal_id = proposal.id

    _login_as(client, coordinator)
    resp1 = client.post(
        f"/manage/pending-new-club-requests/{proposal_id}/coordinator-decision",
        json={"decision": "APPROVE", "notes": "first"},
    )
    assert resp1.status_code in (200, 201, 302)

    resp2 = client.post(
        f"/manage/pending-new-club-requests/{proposal_id}/coordinator-decision",
        json={"decision": "APPROVE", "notes": "second"},
    )
    assert resp2.status_code in (200, 201, 302, 400, 409, 422)

# ==========================================================
# ROUTE: /manage/pending-new-club-requests/admin-review (GET)
# ==========================================================
def test_manage_pending_new_club_requests_admin_review_get_exists(app_context):
    assert _route_exists(
        "/manage/pending-new-club-requests/admin-review", "GET"
    ), "Route GET /manage/pending-new-club-requests/admin-review missing"

def test_manage_pending_new_club_requests_admin_review_get_renders_template(client):
    with app.app_context():
        admin = _create_user(role="ADMIN")
        coordinator = _create_user(role="COORDINATOR")
        proposer = _create_user(role="STUDENT")
        proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")
        proposal.apply_coordinator_decision(coordinator, "APPROVE", "ok")
        db.session.commit()

    _login_as(client, admin)
    resp = client.get("/manage/pending-new-club-requests/admin-review")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# =============================================================================
# ROUTE: /manage/pending-new-club-requests/<int:proposal_id>/admin-decision (POST)
# =============================================================================
def test_manage_pending_new_club_requests_proposal_id_admin_decision_post_exists(app_context):
    assert _route_exists(
        "/manage/pending-new-club-requests/<int:proposal_id>/admin-decision", "POST"
    ), "Route POST /manage/pending-new-club-requests/<int:proposal_id>/admin-decision missing"

def test_manage_pending_new_club_requests_proposal_id_admin_decision_post_success(client):
    with app.app_context():
        admin = _create_user(role="ADMIN")
        coordinator = _create_user(role="COORDINATOR")
        proposer = _create_user(role="STUDENT")
        proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")
        proposal.apply_coordinator_decision(coordinator, "APPROVE", "ok")
        db.session.commit()
        proposal_id = proposal.id

    _login_as(client, admin)
    resp = client.post(
        f"/manage/pending-new-club-requests/{proposal_id}/admin-decision",
        json={"decision": "APPROVE", "notes": "final ok"},
    )
    assert resp.status_code in (200, 201, 302)

    with app.app_context():
        updated = ClubProposal.query.filter_by(id=proposal_id).first()
        assert updated is not None
        assert updated.admin_decision == "APPROVE"
        assert updated.admin_reviewed_by_user_id == admin.id
        assert updated.admin_reviewed_at is not None

def test_manage_pending_new_club_requests_proposal_id_admin_decision_post_missing_required_fields(client):
    with app.app_context():
        admin = _create_user(role="ADMIN")
        coordinator = _create_user(role="COORDINATOR")
        proposer = _create_user(role="STUDENT")
        proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")
        proposal.apply_coordinator_decision(coordinator, "APPROVE", "ok")
        db.session.commit()
        proposal_id = proposal.id

    _login_as(client, admin)
    resp = client.post(
        f"/manage/pending-new-club-requests/{proposal_id}/admin-decision",
        json={"notes": "missing decision"},
    )
    assert resp.status_code in (400, 422)

def test_manage_pending_new_club_requests_proposal_id_admin_decision_post_invalid_data(client):
    with app.app_context():
        admin = _create_user(role="ADMIN")
        coordinator = _create_user(role="COORDINATOR")
        proposer = _create_user(role="STUDENT")
        proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")
        proposal.apply_coordinator_decision(coordinator, "APPROVE", "ok")
        db.session.commit()
        proposal_id = proposal.id

    _login_as(client, admin)
    resp = client.post(
        f"/manage/pending-new-club-requests/{proposal_id}/admin-decision",
        json={"decision": "NOT_A_VALID_DECISION", "notes": "x"},
    )
    assert resp.status_code in (400, 422)

def test_manage_pending_new_club_requests_proposal_id_admin_decision_post_duplicate_data(client):
    with app.app_context():
        admin = _create_user(role="ADMIN")
        coordinator = _create_user(role="COORDINATOR")
        proposer = _create_user(role="STUDENT")
        proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")
        proposal.apply_coordinator_decision(coordinator, "APPROVE", "ok")
        db.session.commit()
        proposal_id = proposal.id

    _login_as(client, admin)
    resp1 = client.post(
        f"/manage/pending-new-club-requests/{proposal_id}/admin-decision",
        json={"decision": "APPROVE", "notes": "first"},
    )
    assert resp1.status_code in (200, 201, 302)

    resp2 = client.post(
        f"/manage/pending-new-club-requests/{proposal_id}/admin-decision",
        json={"decision": "APPROVE", "notes": "second"},
    )
    assert resp2.status_code in (200, 201, 302, 400, 409, 422)

# =========================
# HELPER: get_current_user()
# =========================
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(client):
    with app.app_context():
        u = _create_user(role="COORDINATOR")
    _login_as(client, u)

    with app.test_request_context("/manage/pending-new-club-requests", method="GET"):
        user = get_current_user()
        assert user is not None
        assert getattr(user, "id", None) == u.id

def test_get_current_user_with_invalid_input():
    with app.test_request_context("/manage/pending-new-club-requests", method="GET"):
        user = get_current_user()
        assert user is None

# =========================
# HELPER: require_login(user)
# =========================
def test_require_login_function_exists():
    assert callable(require_login)

def test_require_login_with_valid_input(app_context):
    u = _create_user(role="COORDINATOR")
    require_login(u)

def test_require_login_with_invalid_input(app_context):
    with pytest.raises(Exception):
        require_login(None)

# =========================
# HELPER: require_manage_access(user)
# =========================
def test_require_manage_access_function_exists():
    assert callable(require_manage_access)

def test_require_manage_access_with_valid_input(app_context):
    u = _create_user(role="COORDINATOR")
    require_manage_access(u)

def test_require_manage_access_with_invalid_input(app_context):
    u = _create_user(role="STUDENT")
    with pytest.raises(Exception):
        require_manage_access(u)

# =========================
# HELPER: require_role(user, allowed_roles)
# =========================
def test_require_role_function_exists():
    assert callable(require_role)

def test_require_role_with_valid_input(app_context):
    u = _create_user(role="ADMIN")
    require_role(u, ["ADMIN", "COORDINATOR"])

def test_require_role_with_invalid_input(app_context):
    u = _create_user(role="STUDENT")
    with pytest.raises(Exception):
        require_role(u, ["ADMIN", "COORDINATOR"])

# =========================
# HELPER: parse_decision_payload(request_json)
# =========================
def test_parse_decision_payload_function_exists():
    assert callable(parse_decision_payload)

def test_parse_decision_payload_with_valid_input():
    payload = {"decision": "APPROVE", "notes": "ok"}
    parsed = parse_decision_payload(payload)
    assert isinstance(parsed, dict)
    assert parsed.get("decision") == "APPROVE"
    assert "notes" in parsed

def test_parse_decision_payload_with_invalid_input():
    with pytest.raises(Exception):
        parse_decision_payload(None)

# =========================
# HELPER: serialize_club_proposal(proposal)
# =========================
def test_serialize_club_proposal_function_exists():
    assert callable(serialize_club_proposal)

def test_serialize_club_proposal_with_valid_input(app_context):
    proposer = _create_user(role="STUDENT")
    proposal = _create_proposal(proposed_by_user_id=proposer.id, status="PENDING_COORDINATOR")
    data = serialize_club_proposal(proposal)
    assert isinstance(data, dict)
    assert data.get("id") == proposal.id
    assert data.get("proposed_name") == proposal.proposed_name
    assert data.get("status") == proposal.status

def test_serialize_club_proposal_with_invalid_input():
    with pytest.raises(Exception):
        serialize_club_proposal(None)