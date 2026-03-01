import os
import sys
import uuid
import inspect
import re
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.changing_student_council_clubs_coordinator_role_assignment import RoleAssignment
from models.changing_student_council_clubs_coordinator_profile_badge import ProfileBadge
from controllers.changing_student_council_clubs_coordinator_controller import (
    get_current_user,
    require_permissions,
    get_active_role_assignment,
    assign_student_council_clubs_coordinator,
    sync_student_council_clubs_coordinator_badge,
)
from views.changing_student_council_clubs_coordinator_views import render_manage_page

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

@pytest.fixture
def db_session(app_context):
    return db.session

def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_user(email=None, username=None, password="Password123!"):
    if email is None:
        email = f"{_unique('user')}@example.com"
    if username is None:
        username = _unique("user")
    user = User(email=email, username=username, password_hash="")
    if hasattr(user, "set_password") and callable(getattr(user, "set_password")):
        user.set_password(password)
    return user

def _add_and_commit(obj):
    db.session.add(obj)
    db.session.commit()
    return obj

def _get_rule_methods(path: str):
    rules = []
    for r in app.url_map.iter_rules():
        if r.rule == path:
            rules.append(r)
    return rules

# =========================
# MODEL: User (models/user.py)
# =========================
def test_user_model_has_required_fields(app_context):
    required = ["id", "email", "username", "password_hash", "is_active", "created_at", "updated_at"]
    for field in required:
        assert hasattr(User, field), f"User missing required field: {field}"

def test_user_set_password(app_context):
    user = _create_user()
    user.set_password("MyS3cretPass!")
    assert user.password_hash is not None
    assert isinstance(user.password_hash, str)
    assert user.password_hash != ""
    assert user.password_hash != "MyS3cretPass!"

def test_user_check_password(app_context):
    user = _create_user()
    user.set_password("CorrectHorseBatteryStaple")
    assert user.check_password("CorrectHorseBatteryStaple") is True
    assert user.check_password("wrong-password") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")

    u1 = _create_user(email=email, username=username)
    _add_and_commit(u1)

    u2 = _create_user(email=email, username=_unique("otheruser"))
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = _create_user(email=f"{_unique('other')}@example.com", username=username)
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# =========================
# MODEL: RoleAssignment
# =========================
def test_roleassignment_model_has_required_fields(app_context):
    required = [
        "id",
        "user_id",
        "role_name",
        "is_active",
        "assigned_by_user_id",
        "assigned_at",
        "revoked_by_user_id",
        "revoked_at",
    ]
    for field in required:
        assert hasattr(RoleAssignment, field), f"RoleAssignment missing required field: {field}"

def test_roleassignment_revoke(app_context):
    ra = RoleAssignment(
        user_id=1,
        role_name="student_council_clubs_coordinator",
        is_active=True,
        assigned_by_user_id=2,
    )
    _add_and_commit(ra)

    ra.revoke(revoked_by_user_id=99)
    db.session.commit()

    assert ra.is_active is False
    assert ra.revoked_by_user_id == 99
    assert ra.revoked_at is not None

def test_roleassignment_unique_constraints(app_context):
    ra1 = RoleAssignment(
        user_id=1,
        role_name="student_council_clubs_coordinator",
        is_active=True,
        assigned_by_user_id=2,
    )
    ra2 = RoleAssignment(
        user_id=1,
        role_name="student_council_clubs_coordinator",
        is_active=True,
        assigned_by_user_id=2,
    )
    db.session.add_all([ra1, ra2])
    db.session.commit()
    assert RoleAssignment.query.count() == 2

# =========================
# MODEL: ProfileBadge
# =========================
def test_profilebadge_model_has_required_fields(app_context):
    required = [
        "id",
        "user_id",
        "badge_key",
        "is_active",
        "granted_by_user_id",
        "granted_at",
        "revoked_by_user_id",
        "revoked_at",
    ]
    for field in required:
        assert hasattr(ProfileBadge, field), f"ProfileBadge missing required field: {field}"

def test_profilebadge_revoke(app_context):
    pb = ProfileBadge(
        user_id=1,
        badge_key="student_council_clubs_coordinator",
        is_active=True,
        granted_by_user_id=2,
    )
    _add_and_commit(pb)

    pb.revoke(revoked_by_user_id=77)
    db.session.commit()

    assert pb.is_active is False
    assert pb.revoked_by_user_id == 77
    assert pb.revoked_at is not None

def test_profilebadge_unique_constraints(app_context):
    pb1 = ProfileBadge(
        user_id=1,
        badge_key="student_council_clubs_coordinator",
        is_active=True,
        granted_by_user_id=2,
    )
    pb2 = ProfileBadge(
        user_id=1,
        badge_key="student_council_clubs_coordinator",
        is_active=True,
        granted_by_user_id=2,
    )
    db.session.add_all([pb1, pb2])
    db.session.commit()
    assert ProfileBadge.query.count() == 2

# =========================
# ROUTE: GET /manage/student-council-clubs-coordinator
# =========================
def test_manage_student_council_clubs_coordinator_get_exists(app_context, client):
    rules = _get_rule_methods("/manage/student-council-clubs-coordinator")
    assert rules, "Route /manage/student-council-clubs-coordinator is missing"
    assert any("GET" in r.methods for r in rules), "Route must accept GET"

def test_manage_student_council_clubs_coordinator_get_renders_template(app_context, client):
    admin = _create_user()
    _add_and_commit(admin)

    with patch(
        "controllers.changing_student_council_clubs_coordinator_controller.get_current_user",
        return_value=admin,
    ), patch(
        "controllers.changing_student_council_clubs_coordinator_controller.require_permissions",
        return_value=None,
    ):
        resp = client.get("/manage/student-council-clubs-coordinator")
        assert resp.status_code == 200
        assert resp.data is not None
        assert len(resp.data) > 0

# =========================
# ROUTE: POST /manage/student-council-clubs-coordinator
# =========================
def test_manage_student_council_clubs_coordinator_post_exists(app_context, client):
    rules = _get_rule_methods("/manage/student-council-clubs-coordinator")
    assert rules, "Route /manage/student-council-clubs-coordinator is missing"
    assert any("POST" in r.methods for r in rules), "Route must accept POST"

def test_manage_student_council_clubs_coordinator_post_success(app_context, client):
    admin = _create_user()
    new_user = _create_user()
    old_user = _create_user()
    db.session.add_all([admin, new_user, old_user])
    db.session.commit()

    old_assignment = RoleAssignment(
        user_id=old_user.id,
        role_name="student_council_clubs_coordinator",
        is_active=True,
        assigned_by_user_id=admin.id,
    )
    old_badge = ProfileBadge(
        user_id=old_user.id,
        badge_key="student_council_clubs_coordinator",
        is_active=True,
        granted_by_user_id=admin.id,
    )
    db.session.add_all([old_assignment, old_badge])
    db.session.commit()

    with patch(
        "controllers.changing_student_council_clubs_coordinator_controller.get_current_user",
        return_value=admin,
    ):
        resp = client.post(
            "/manage/student-council-clubs-coordinator",
            data={
                "new_coordinator_user_id": str(new_user.id),
                "new_coordinator_email": f"{_unique('updated')}@example.com",
                "new_coordinator_username": _unique("updateduser"),
            },
            follow_redirects=False,
        )

    assert resp.status_code in (200, 302)

    active = RoleAssignment.query.filter_by(
        role_name="student_council_clubs_coordinator", is_active=True
    ).all()
    assert len(active) == 1
    assert active[0].user_id == new_user.id

    old_assignment_db = RoleAssignment.query.filter_by(id=old_assignment.id).first()
    assert old_assignment_db is not None
    assert old_assignment_db.is_active is False
    assert old_assignment_db.revoked_at is not None

    new_badge = ProfileBadge.query.filter_by(
        user_id=new_user.id, badge_key="student_council_clubs_coordinator", is_active=True
    ).first()
    assert new_badge is not None

    old_badge_db = ProfileBadge.query.filter_by(id=old_badge.id).first()
    assert old_badge_db is not None
    assert old_badge_db.is_active is False
    assert old_badge_db.revoked_at is not None

    updated_new_user = User.query.filter_by(id=new_user.id).first()
    assert updated_new_user.email is not None
    assert updated_new_user.username is not None

def test_manage_student_council_clubs_coordinator_post_missing_required_fields(app_context, client):
    admin = _create_user()
    _add_and_commit(admin)

    with patch(
        "controllers.changing_student_council_clubs_coordinator_controller.get_current_user",
        return_value=admin,
    ), patch(
        "controllers.changing_student_council_clubs_coordinator_controller.require_permissions",
        return_value=None,
    ):
        resp = client.post(
            "/manage/student-council-clubs-coordinator",
            data={},
            follow_redirects=False,
        )
    assert resp.status_code in (200, 400)

def test_manage_student_council_clubs_coordinator_post_invalid_data(app_context, client):
    admin = _create_user()
    _add_and_commit(admin)

    with patch(
        "controllers.changing_student_council_clubs_coordinator_controller.get_current_user",
        return_value=admin,
    ), patch(
        "controllers.changing_student_council_clubs_coordinator_controller.require_permissions",
        return_value=None,
    ):
        resp = client.post(
            "/manage/student-council-clubs-coordinator",
            data={
                "new_coordinator_user_id": "not-an-int",
                "new_coordinator_email": "not-an-email",
                "new_coordinator_username": "ab",
            },
            follow_redirects=False,
        )
    assert resp.status_code in (200, 400)

def test_manage_student_council_clubs_coordinator_post_duplicate_data(app_context, client):
    admin = _create_user()
    new_user = _create_user()
    other_user = _create_user()
    db.session.add_all([admin, new_user, other_user])
    db.session.commit()

    with patch(
        "controllers.changing_student_council_clubs_coordinator_controller.get_current_user",
        return_value=admin,
    ), patch(
        "controllers.changing_student_council_clubs_coordinator_controller.require_permissions",
        return_value=None,
    ):
        resp = client.post(
            "/manage/student-council-clubs-coordinator",
            data={
                "new_coordinator_user_id": str(new_user.id),
                "new_coordinator_email": other_user.email,
                "new_coordinator_username": other_user.username,
            },
            follow_redirects=False,
        )
    assert resp.status_code in (200, 400)

# =========================
# HELPER: get_current_user
# =========================
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(app_context):
    user = _create_user()
    _add_and_commit(user)

    with patch(
        "controllers.changing_student_council_clubs_coordinator_controller.get_current_user",
        return_value=user,
    ):
        result = get_current_user()
        assert result is not None
        assert isinstance(result, User)
        assert result.id == user.id

def test_get_current_user_with_invalid_input(app_context):
    with patch(
        "controllers.changing_student_council_clubs_coordinator_controller.get_current_user",
        return_value=None,
    ):
        result = get_current_user()
        assert result is None

# =========================
# HELPER: require_permissions(user: User, permissions: list[str])
# =========================
def test_require_permissions_function_exists():
    assert callable(require_permissions)
    sig = inspect.signature(require_permissions)
    assert "user" in sig.parameters
    assert "permissions" in sig.parameters

def test_require_permissions_with_valid_input(app_context):
    user = _create_user()
    _add_and_commit(user)

    with patch(
        "controllers.changing_student_council_clubs_coordinator_controller.require_permissions",
        return_value=None,
    ):
        require_permissions(user=user, permissions=["manage_access", "update_student_council_clubs_coordinator"])

def test_require_permissions_with_invalid_input(app_context):
    with pytest.raises(Exception):
        require_permissions(user=None, permissions=["manage_access"])

# =========================
# HELPER: get_active_role_assignment(role_name: str)
# =========================
def test_get_active_role_assignment_function_exists():
    assert callable(get_active_role_assignment)
    sig = inspect.signature(get_active_role_assignment)
    assert "role_name" in sig.parameters

def test_get_active_role_assignment_with_valid_input(app_context):
    admin = _create_user()
    u = _create_user()
    db.session.add_all([admin, u])
    db.session.commit()

    ra = RoleAssignment(
        user_id=u.id,
        role_name="student_council_clubs_coordinator",
        is_active=True,
        assigned_by_user_id=admin.id,
    )
    _add_and_commit(ra)

    result = get_active_role_assignment("student_council_clubs_coordinator")
    assert result is not None
    assert isinstance(result, RoleAssignment)
    assert result.is_active is True
    assert result.role_name == "student_council_clubs_coordinator"

def test_get_active_role_assignment_with_invalid_input(app_context):
    result = get_active_role_assignment("nonexistent_role_name")
    assert result is None

# =========================
# HELPER: assign_student_council_clubs_coordinator(admin_user: User, new_user: User)
# =========================
def test_assign_student_council_clubs_coordinator_function_exists():
    assert callable(assign_student_council_clubs_coordinator)
    sig = inspect.signature(assign_student_council_clubs_coordinator)
    assert "admin_user" in sig.parameters
    assert "new_user" in sig.parameters

def test_assign_student_council_clubs_coordinator_with_valid_input(app_context):
    admin = _create_user()
    new_user = _create_user()
    db.session.add_all([admin, new_user])
    db.session.commit()

    old_user = _create_user()
    db.session.add(old_user)
    db.session.commit()

    old_ra = RoleAssignment(
        user_id=old_user.id,
        role_name="student_council_clubs_coordinator",
        is_active=True,
        assigned_by_user_id=admin.id,
    )
    _add_and_commit(old_ra)

    new_ra = assign_student_council_clubs_coordinator(admin_user=admin, new_user=new_user)
    assert new_ra is not None
    assert isinstance(new_ra, RoleAssignment)
    assert new_ra.user_id == new_user.id
    assert new_ra.role_name == "student_council_clubs_coordinator"
    assert new_ra.is_active is True

    old_ra_db = RoleAssignment.query.filter_by(id=old_ra.id).first()
    assert old_ra_db.is_active is False
    assert old_ra_db.revoked_at is not None

def test_assign_student_council_clubs_coordinator_with_invalid_input(app_context):
    admin = _create_user()
    _add_and_commit(admin)

    with pytest.raises(Exception):
        assign_student_council_clubs_coordinator(admin_user=admin, new_user=None)

# =========================
# HELPER: sync_student_council_clubs_coordinator_badge(admin_user: User, new_user: User, old_user: User | None)
# =========================
def test_sync_student_council_clubs_coordinator_badge_function_exists():
    assert callable(sync_student_council_clubs_coordinator_badge)
    sig = inspect.signature(sync_student_council_clubs_coordinator_badge)
    assert "admin_user" in sig.parameters
    assert "new_user" in sig.parameters
    assert "old_user" in sig.parameters

def test_sync_student_council_clubs_coordinator_badge_with_valid_input(app_context):
    admin = _create_user()
    new_user = _create_user()
    old_user = _create_user()
    db.session.add_all([admin, new_user, old_user])
    db.session.commit()

    old_badge = ProfileBadge(
        user_id=old_user.id,
        badge_key="student_council_clubs_coordinator",
        is_active=True,
        granted_by_user_id=admin.id,
    )
    _add_and_commit(old_badge)

    sync_student_council_clubs_coordinator_badge(admin_user=admin, new_user=new_user, old_user=old_user)
    db.session.commit()

    new_badge = ProfileBadge.query.filter_by(
        user_id=new_user.id, badge_key="student_council_clubs_coordinator", is_active=True
    ).first()
    assert new_badge is not None

    old_badge_db = ProfileBadge.query.filter_by(id=old_badge.id).first()
    assert old_badge_db is not None
    assert old_badge_db.is_active is False
    assert old_badge_db.revoked_at is not None

def test_sync_student_council_clubs_coordinator_badge_with_invalid_input(app_context):
    admin = _create_user()
    new_user = _create_user()
    db.session.add_all([admin, new_user])
    db.session.commit()

    with pytest.raises(Exception):
        sync_student_council_clubs_coordinator_badge(admin_user=admin, new_user=None, old_user=None)