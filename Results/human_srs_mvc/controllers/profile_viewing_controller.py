from functools import wraps

from flask import Blueprint
from flask import jsonify
from flask import request
from flask import session

from app import db
from models.profile_viewing_event import ProfileViewingEvent
from models.profile_viewing_event_registration import ProfileViewingEventRegistration
from models.user import User
from views.profile_viewing_views import render_profile_page

profile_viewing_bp = Blueprint("profile_viewing_bp", __name__, url_prefix="")


def login_required(view_func):
    if view_func is None or not callable(view_func):
        raise TypeError("view_func_must_be_callable")

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "authentication_required"}), 401
        return view_func(*args, **kwargs)

    return wrapper


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        session.pop("user_id", None)
        return None
    db.session.refresh(user)
    return user


def can_view_profile(viewer, target_user):
    if viewer is None or target_user is None:
        raise ValueError("viewer_and_target_required")

    viewer_role = viewer.role.value if hasattr(viewer.role, "value") else viewer.role
    allowed = {
        "COLLEGE_ADMIN",
        "CLUB_COORDINATOR",
        "STUDENT_COUNCIL_CLUB_COORDINATOR",
        "STUDENT_AFFAIRS_ADMIN",
    }
    return viewer_role in allowed


def build_profile_payload(target_user, include_registered_events):
    if target_user is None:
        raise ValueError("target_user_required")
    if not isinstance(include_registered_events, bool):
        raise TypeError("include_registered_events_must_be_bool")

    user_dict = target_user.to_public_dict(include_contact=True)
    registered_events = []

    if include_registered_events:
        registrations = (
            ProfileViewingEventRegistration.query.filter_by(user_id=target_user.id)
            .order_by(ProfileViewingEventRegistration.registered_at.desc())
            .all()
        )
        event_ids = [r.event_id for r in registrations if r.event_id is not None]
        events_by_id = {}
        if event_ids:
            events = ProfileViewingEvent.query.filter(ProfileViewingEvent.id.in_(event_ids)).all()
            events_by_id = {e.id: e for e in events}

        for reg in registrations:
            event = events_by_id.get(reg.event_id)
            if event is None:
                continue
            reg_dict = reg.to_public_dict()
            reg_dict["event"] = event.to_public_dict()
            registered_events.append(reg_dict)

    return {"user": user_dict, "registered_events": registered_events}


@profile_viewing_bp.route("/profile", methods=["GET"])
@login_required
def profile_page():
    current_user = get_current_user()
    if current_user is None:
        return jsonify({"error": "authentication_required"}), 401
    payload = build_profile_payload(current_user, include_registered_events=True)
    return render_profile_page(payload["user"], payload["registered_events"])


@profile_viewing_bp.route("/api/profile", methods=["GET"])
@login_required
def get_my_profile_api():
    current_user = get_current_user()
    if current_user is None:
        return jsonify({"error": "authentication_required"}), 401
    include_events = request.args.get("include_events", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    payload = build_profile_payload(current_user, include_registered_events=include_events)
    return jsonify(payload), 200


@profile_viewing_bp.route("/api/users/<int:user_id>/profile", methods=["GET"])
@login_required
def get_user_profile_api(user_id):
    current_user = get_current_user()
    if current_user is None:
        return jsonify({"error": "authentication_required"}), 401

    target_user = User.query.filter_by(id=user_id).first()
    if not target_user:
        return jsonify({"error": "user_not_found"}), 404

    if not can_view_profile(current_user, target_user):
        return jsonify({"error": "forbidden"}), 403

    include_events = request.args.get("include_events", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    payload = build_profile_payload(target_user, include_registered_events=include_events)
    return jsonify(payload), 200