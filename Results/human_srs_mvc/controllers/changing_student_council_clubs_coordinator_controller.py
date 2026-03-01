import re

from flask import Blueprint
from flask import redirect
from flask import request
from flask import session
from flask import url_for

from app import db
from models.changing_student_council_clubs_coordinator_profile_badge import ProfileBadge
from models.changing_student_council_clubs_coordinator_role_assignment import RoleAssignment
from models.user import User
from views.changing_student_council_clubs_coordinator_views import render_manage_page

changing_student_council_clubs_coordinator = Blueprint(
    "changing_student_council_clubs_coordinator", __name__, url_prefix=""
)

_ROLE_NAME = "student_council_clubs_coordinator"
_BADGE_KEY = "student_council_clubs_coordinator"
_PERM_MANAGE = "manage_access"
_PERM_UPDATE = "update_student_council_clubs_coordinator"


def get_current_user() -> User:
    user_id = session.get("user_id")
    if user_id is None:
        return None
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        return None
    return User.query.filter_by(id=user_id_int).first()


def require_permissions(user: User, permissions: list[str]):
    if user is None:
        raise Exception("Login required")
    if not isinstance(permissions, list) or any(
        (p is None or not isinstance(p, str) or not p.strip()) for p in permissions
    ):
        raise TypeError("permissions must be list[str]")

    user_perms = session.get("permissions")
    if user_perms is None:
        user_perms = []
    if not isinstance(user_perms, list):
        raise Exception("Forbidden")

    missing = [p for p in permissions if p not in user_perms]
    if missing:
        raise Exception("Forbidden")


def get_active_role_assignment(role_name: str) -> RoleAssignment | None:
    if role_name is None or not isinstance(role_name, str) or not role_name.strip():
        raise TypeError("role_name must be a non-empty str")
    return RoleAssignment.query.filter_by(role_name=role_name, is_active=True).first()


def assign_student_council_clubs_coordinator(admin_user: User, new_user: User) -> RoleAssignment:
    if admin_user is None or not hasattr(admin_user, "id") or admin_user.id is None:
        raise ValueError("Invalid admin_user")
    if new_user is None or not hasattr(new_user, "id") or new_user.id is None:
        raise ValueError("Invalid new_user")

    current_assignment = get_active_role_assignment(_ROLE_NAME)
    if current_assignment and int(current_assignment.user_id) != int(new_user.id):
        current_assignment.revoke(int(admin_user.id))

    if current_assignment and int(current_assignment.user_id) == int(new_user.id):
        db.session.flush()
        return current_assignment

    new_assignment = RoleAssignment(
        user_id=int(new_user.id),
        role_name=_ROLE_NAME,
        is_active=True,
        assigned_by_user_id=int(admin_user.id),
    )
    db.session.add(new_assignment)
    db.session.flush()
    return new_assignment


def sync_student_council_clubs_coordinator_badge(admin_user: User, new_user: User, old_user: User | None):
    if admin_user is None or not hasattr(admin_user, "id") or admin_user.id is None:
        raise ValueError("Invalid admin_user")
    if new_user is None or not hasattr(new_user, "id") or new_user.id is None:
        raise ValueError("Invalid new_user")

    if old_user is not None and hasattr(old_user, "id") and old_user.id is not None:
        old_badges = ProfileBadge.query.filter_by(
            user_id=int(old_user.id), badge_key=_BADGE_KEY, is_active=True
        ).all()
        for b in old_badges:
            b.revoke(int(admin_user.id))

    existing_new = ProfileBadge.query.filter_by(
        user_id=int(new_user.id), badge_key=_BADGE_KEY, is_active=True
    ).first()
    if existing_new:
        db.session.flush()
        return

    new_badge = ProfileBadge(
        user_id=int(new_user.id),
        badge_key=_BADGE_KEY,
        is_active=True,
        granted_by_user_id=int(admin_user.id),
    )
    db.session.add(new_badge)
    db.session.flush()


def _is_valid_email(email: str) -> bool:
    if email is None or not isinstance(email, str):
        return False
    email = email.strip()
    if not email:
        return False
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


@changing_student_council_clubs_coordinator.route(
    "/manage/student-council-clubs-coordinator", methods=["GET"]
)
def view_student_council_clubs_coordinator():
    current_user = get_current_user()
    try:
        require_permissions(current_user, [_PERM_MANAGE, _PERM_UPDATE])
    except Exception:
        return ("Forbidden", 403)

    current_assignment = get_active_role_assignment(_ROLE_NAME)
    current_coordinator = (
        User.query.filter_by(id=int(current_assignment.user_id)).first()
        if current_assignment
        else None
    )
    all_users = User.query.order_by(User.id.asc()).all()
    return render_manage_page(current_coordinator, all_users, None)


@changing_student_council_clubs_coordinator.route(
    "/manage/student-council-clubs-coordinator", methods=["POST"]
)
def update_student_council_clubs_coordinator():
    current_user = get_current_user()
    try:
        require_permissions(current_user, [_PERM_MANAGE, _PERM_UPDATE])
    except Exception:
        return ("Forbidden", 403)

    errors = {}

    new_coordinator_user_id = request.form.get("new_coordinator_user_id", type=int)
    new_coordinator_email = request.form.get("new_coordinator_email", type=str)
    new_coordinator_username = request.form.get("new_coordinator_username", type=str)

    if new_coordinator_user_id is None:
        errors["new_coordinator_user_id"] = "required"
    new_user = (
        User.query.filter_by(id=int(new_coordinator_user_id)).first()
        if new_coordinator_user_id is not None
        else None
    )
    if not new_user:
        errors["new_coordinator_user_id"] = "must_exist_in_users_table"

    if new_coordinator_email is not None:
        new_coordinator_email = str(new_coordinator_email).strip()
        if new_coordinator_email == "":
            new_coordinator_email = None
    if new_coordinator_username is not None:
        new_coordinator_username = str(new_coordinator_username).strip()
        if new_coordinator_username == "":
            new_coordinator_username = None

    if new_coordinator_email:
        if not _is_valid_email(new_coordinator_email):
            errors["new_coordinator_email"] = "invalid_email_format"
        else:
            existing = User.query.filter_by(email=new_coordinator_email).first()
            if existing and int(existing.id) != int(new_user.id):
                errors["new_coordinator_email"] = "email_not_unique"

    if new_coordinator_username:
        if len(new_coordinator_username) < 3 or len(new_coordinator_username) > 80:
            errors["new_coordinator_username"] = "invalid_length"
        else:
            existing = User.query.filter_by(username=new_coordinator_username).first()
            if existing and int(existing.id) != int(new_user.id):
                errors["new_coordinator_username"] = "username_not_unique"

    if errors:
        current_assignment = get_active_role_assignment(_ROLE_NAME)
        current_coordinator = (
            User.query.filter_by(id=int(current_assignment.user_id)).first()
            if current_assignment
            else None
        )
        all_users = User.query.order_by(User.id.asc()).all()
        return render_manage_page(current_coordinator, all_users, errors), 400

    if new_coordinator_email:
        new_user.email = new_coordinator_email
    if new_coordinator_username:
        new_user.username = new_coordinator_username

    old_assignment = get_active_role_assignment(_ROLE_NAME)
    old_user = (
        User.query.filter_by(id=int(old_assignment.user_id)).first()
        if old_assignment
        else None
    )

    assign_student_council_clubs_coordinator(current_user, new_user)
    sync_student_council_clubs_coordinator_badge(current_user, new_user, old_user)

    db.session.commit()
    return redirect(
        url_for("changing_student_council_clubs_coordinator.view_student_council_clubs_coordinator")
    )