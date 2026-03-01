import os
import sys
import uuid
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.requesting_formation_new_club_club_proposal import ClubProposal
from controllers.requesting_formation_new_club_controller import (
    get_current_user,
    validate_club_proposal_payload,
)
from views.requesting_formation_new_club_views import (
    render_clubs_home,
    render_propose_new_club_form,
    render_club_proposal_detail,
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

def _create_user(email=None, username=None, password="StrongPass!123"):
    if email is None:
        email = f"{_unique('user')}@example.com"
    if username is None:
        username = _unique("user")
    u = User(email=email, username=username, password_hash="")
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u

def _valid_payload(club_name=None):
    if club_name is None:
        club_name = _unique("club")
    return {
        "club_name": club_name,
        "club_category": "Tech",
        "description": "A" * 40,
        "objectives": "B" * 20,
        "proposed_activities": "C" * 20,
        "faculty_advisor_name": "Dr. Faculty Advisor",
        "faculty_advisor_email": f"{_unique('advisor')}@iiitd.ac.in",
        "co_founders": "Co Founder One, Co Founder Two",
        "expected_members_count": 25,
    }

def _login_via_session(client, user_id: int):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

# MODEL: User (models/user.py)
def test_user_model_has_required_fields(app_context):
    for field in ["id", "email", "username", "password_hash"]:
        assert hasattr(User, field), f"Missing required User field: {field}"

def test_user_set_password(app_context):
    user = User(email=f"{_unique('e')}@example.com", username=_unique("u"), password_hash="")
    user.set_password("password123")
    assert user.password_hash
    assert user.password_hash != "password123"

def test_user_check_password(app_context):
    user = User(email=f"{_unique('e')}@example.com", username=_unique("u"), password_hash="")
    user.set_password("password123")
    assert user.check_password("password123") is True
    assert user.check_password("wrong") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")

    u1 = User(email=email, username=username, password_hash="")
    u1.set_password("pass12345")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("otheruser"), password_hash="")
    u2.set_password("pass12345")
    db.session.add(u2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, password_hash="")
    u3.set_password("pass12345")
    db.session.add(u3)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# MODEL: ClubProposal (models/requesting_formation_new_club_club_proposal.py)
def test_clubproposal_model_has_required_fields(app_context):
    required = [
        "id",
        "proposer_user_id",
        "club_name",
        "club_category",
        "description",
        "objectives",
        "proposed_activities",
        "faculty_advisor_name",
        "faculty_advisor_email",
        "co_founders",
        "expected_members_count",
        "status",
        "created_at",
        "updated_at",
    ]
    for field in required:
        assert hasattr(ClubProposal, field), f"Missing required ClubProposal field: {field}"

def test_clubproposal_to_dict(app_context):
    user = _create_user()
    proposal = ClubProposal(
        proposer_user_id=user.id,
        club_name=_unique("club"),
        club_category="Cultural",
        description="D" * 50,
        objectives="O" * 20,
        proposed_activities="P" * 20,
        faculty_advisor_name="Prof. Xyz",
        faculty_advisor_email=f"{_unique('fa')}@iiitd.ac.in",
        co_founders="A, B",
        expected_members_count=10,
        status="submitted",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(proposal)
    db.session.commit()

    d = proposal.to_dict()
    assert isinstance(d, dict)
    assert d.get("id") == proposal.id
    assert d.get("club_name") == proposal.club_name

def test_clubproposal_unique_constraints(app_context):
    user = _create_user()
    club_name = _unique("uniqueclub")

    p1 = ClubProposal(
        proposer_user_id=user.id,
        club_name=club_name,
        club_category="Tech",
        description="D" * 50,
        objectives="O" * 20,
        proposed_activities="P" * 20,
        faculty_advisor_name="Prof. A",
        faculty_advisor_email=f"{_unique('fa')}@iiitd.ac.in",
        co_founders="A, B",
        expected_members_count=10,
        status="submitted",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(p1)
    db.session.commit()

    p2 = ClubProposal(
        proposer_user_id=user.id,
        club_name=club_name,
        club_category="Tech",
        description="D" * 50,
        objectives="O" * 20,
        proposed_activities="P" * 20,
        faculty_advisor_name="Prof. B",
        faculty_advisor_email=f"{_unique('fb')}@iiitd.ac.in",
        co_founders="C, D",
        expected_members_count=20,
        status="submitted",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(p2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# ROUTE: /clubs (GET) - clubs_home
def test_clubs_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/clubs"]
    assert rules, "Route /clubs is missing"
    assert any("GET" in r.methods for r in rules), "Route /clubs does not accept GET"

def test_clubs_get_renders_template(client):
    user = None
    with patch(
        "controllers.requesting_formation_new_club_controller.get_current_user",
        return_value=user,
    ):
        resp = client.get("/clubs")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")

# ROUTE: /clubs/propose (GET) - propose_new_club_form
def test_clubs_propose_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/clubs/propose"]
    assert rules, "Route /clubs/propose is missing"
    assert any("GET" in r.methods for r in rules), "Route /clubs/propose does not accept GET"

def test_clubs_propose_get_renders_template(client):
    user = None
    with patch(
        "controllers.requesting_formation_new_club_controller.get_current_user",
        return_value=user,
    ):
        resp = client.get("/clubs/propose")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")

# ROUTE: /clubs/propose (POST) - submit_new_club_proposal
def test_clubs_propose_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/clubs/propose"]
    assert rules, "Route /clubs/propose is missing"
    assert any("POST" in r.methods for r in rules), "Route /clubs/propose does not accept POST"

def test_clubs_propose_post_success(client):
    with app.app_context():
        user = _create_user()

    payload = _valid_payload()
    with patch(
        "controllers.requesting_formation_new_club_controller.get_current_user",
        return_value=user,
    ):
        resp = client.post("/clubs/propose", json=payload)

    assert resp.status_code == 201
    assert resp.content_type.startswith("application/json")
    data = resp.get_json()
    assert set(data.keys()) == {"id", "status", "club_name", "created_at"}
    assert isinstance(data["id"], int)
    assert data["status"] in {"submitted", "under_review", "approved", "rejected"}
    assert data["club_name"] == payload["club_name"]
    assert isinstance(data["created_at"], str) and data["created_at"]

def test_clubs_propose_post_missing_required_fields(client):
    with app.app_context():
        user = _create_user()

    payload = _valid_payload()
    payload.pop("club_name")

    with patch(
        "controllers.requesting_formation_new_club_controller.get_current_user",
        return_value=user,
    ):
        resp = client.post("/clubs/propose", json=payload)

    assert resp.status_code == 400
    assert resp.content_type.startswith("application/json")
    data = resp.get_json()
    assert set(data.keys()) == {"error", "details"}
    assert isinstance(data["details"], dict)

def test_clubs_propose_post_invalid_data(client):
    with app.app_context():
        user = _create_user()

    payload = _valid_payload()
    payload["faculty_advisor_email"] = "not-an-email"
    payload["expected_members_count"] = 0
    payload["description"] = "too short"

    with patch(
        "controllers.requesting_formation_new_club_controller.get_current_user",
        return_value=user,
    ):
        resp = client.post("/clubs/propose", json=payload)

    assert resp.status_code == 400
    assert resp.content_type.startswith("application/json")
    data = resp.get_json()
    assert set(data.keys()) == {"error", "details"}
    assert isinstance(data["details"], dict)
    assert data["details"], "Expected validation error details for invalid payload"

def test_clubs_propose_post_duplicate_data(client):
    with app.app_context():
        user = _create_user()

    club_name = _unique("dupclub")
    payload1 = _valid_payload(club_name=club_name)
    payload2 = _valid_payload(club_name=club_name)

    with patch(
        "controllers.requesting_formation_new_club_controller.get_current_user",
        return_value=user,
    ):
        resp1 = client.post("/clubs/propose", json=payload1)
    assert resp1.status_code == 201

    with patch(
        "controllers.requesting_formation_new_club_controller.get_current_user",
        return_value=user,
    ):
        resp2 = client.post("/clubs/propose", json=payload2)

    assert resp2.status_code == 409
    assert resp2.content_type.startswith("application/json")
    data = resp2.get_json()
    assert set(data.keys()) == {"error"}
    assert isinstance(data["error"], str) and data["error"]

# ROUTE: /clubs/proposals/<int:proposal_id> (GET) - get_club_proposal
def test_clubs_proposals_proposal_id_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/clubs/proposals/<int:proposal_id>"]
    assert rules, "Route /clubs/proposals/<int:proposal_id> is missing"
    assert any("GET" in r.methods for r in rules), "Route /clubs/proposals/<int:proposal_id> does not accept GET"

def test_clubs_proposals_proposal_id_get_renders_template(client):
    with app.app_context():
        user = _create_user()
        proposal = ClubProposal(
            proposer_user_id=user.id,
            club_name=_unique("club"),
            club_category="Tech",
            description="D" * 50,
            objectives="O" * 20,
            proposed_activities="P" * 20,
            faculty_advisor_name="Prof. A",
            faculty_advisor_email=f"{_unique('fa')}@iiitd.ac.in",
            co_founders="A, B",
            expected_members_count=10,
            status="submitted",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(proposal)
        db.session.commit()
        proposal_id = proposal.id

    resp = client.get(f"/clubs/proposals/{proposal_id}")
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    data = resp.get_json()
    expected_keys = {
        "id",
        "proposer_user_id",
        "club_name",
        "club_category",
        "description",
        "objectives",
        "proposed_activities",
        "faculty_advisor_name",
        "faculty_advisor_email",
        "co_founders",
        "expected_members_count",
        "status",
        "created_at",
        "updated_at",
    }
    assert set(data.keys()) == expected_keys

# HELPER: get_current_user(N/A)
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(client):
    with app.app_context():
        user = _create_user()

    _login_via_session(client, user.id)

    with app.test_request_context("/clubs"):
        with client.session_transaction() as sess:
            for k, v in sess.items():
                from flask import session as flask_session

                flask_session[k] = v

        result = get_current_user()
        assert result is not None
        assert isinstance(result, User)
        assert result.id == user.id

def test_get_current_user_with_invalid_input(client):
    _login_via_session(client, 999999)

    with app.test_request_context("/clubs"):
        with client.session_transaction() as sess:
            for k, v in sess.items():
                from flask import session as flask_session

                flask_session[k] = v

        result = get_current_user()
        assert result is None

# HELPER: validate_club_proposal_payload(payload)
def test_validate_club_proposal_payload_function_exists():
    assert callable(validate_club_proposal_payload)

def test_validate_club_proposal_payload_with_valid_input():
    payload = _valid_payload()
    ok, details = validate_club_proposal_payload(payload)
    assert ok is True
    assert isinstance(details, dict)
    assert details == {}

def test_validate_club_proposal_payload_with_invalid_input():
    payload = _valid_payload()
    payload["club_name"] = "ab"
    payload["expected_members_count"] = 0
    payload["faculty_advisor_email"] = "bad"

    ok, details = validate_club_proposal_payload(payload)
    assert ok is False
    assert isinstance(details, dict)
    assert details, "Expected non-empty error details for invalid payload"