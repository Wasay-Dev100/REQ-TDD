from flask import Blueprint
from flask import request
from flask import jsonify
from flask import session
from datetime import datetime
from app import db
from models.user import User
from models.event_scheduling_and_approval_club import Club
from models.event_scheduling_and_approval_club_membership import ClubMembership
from models.event_scheduling_and_approval_event_request import EventRequest
from views.event_scheduling_and_approval_views import render_propose_event_form
from views.event_scheduling_and_approval_views import render_event_requests_list
from views.event_scheduling_and_approval_views import render_event_request_detail

event_scheduling_and_approval_bp = Blueprint('event_scheduling_and_approval', __name__)


def get_current_user():
    user_id = session.get('user_id')
    if user_id is None:
        return None
    return db.session.get(User, user_id)


def require_role(user, allowed_roles):
    if user is None:
        raise Exception("Authentication required")
    if not allowed_roles or not isinstance(allowed_roles, (list, tuple, set)):
        raise Exception("allowed_roles must be a non-empty list/tuple/set")
    if user.role not in allowed_roles:
        raise Exception("User does not have the required role.")


def require_club_coordinator(user, club_id):
    if user is None:
        raise Exception("Authentication required")
    if club_id is None:
        raise Exception("club_id is required")
    membership = ClubMembership.query.filter_by(user_id=user.id, club_id=club_id).first()
    if not membership or not membership.is_coordinator():
        raise Exception("User is not a coordinator for this club.")


def parse_event_request_payload(request):
    if request is None:
        raise Exception("request is required")
    payload = request.get_json(silent=True)
    if payload is None:
        raise Exception("JSON payload required")
    if not isinstance(payload, dict):
        raise Exception("Invalid JSON payload")
    return payload


def validate_event_request_payload(payload):
    if payload is None or not isinstance(payload, dict):
        raise Exception("payload must be a dict")
    errors = {}
    title = payload.get('title')
    if not title or not isinstance(title, str) or not title.strip():
        errors['title'] = 'Title is required.'
    if not payload.get('start_at') or not payload.get('end_at'):
        errors['time'] = 'Start and end times are required.'
    return errors


def check_time_conflicts(start_at, end_at):
    if start_at is None or end_at is None:
        raise Exception("start_at and end_at are required")
    conflicts = EventRequest.query.filter(
        EventRequest.start_at < end_at,
        EventRequest.end_at > start_at,
        EventRequest.status == 'APPROVED'
    ).all()
    return {'conflicts': len(conflicts) > 0}


def serialize_event_request(event_request):
    if event_request is None:
        raise Exception("event_request is required")

    def _dt(v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)

    return {
        'id': event_request.id,
        'club_id': event_request.club_id,
        'title': event_request.title,
        'description': event_request.description,
        'location': event_request.location,
        'start_at': _dt(event_request.start_at),
        'end_at': _dt(event_request.end_at),
        'status': event_request.status,
        'proposed_by_user_id': event_request.proposed_by_user_id,
        'reviewed_by_user_id': event_request.reviewed_by_user_id,
        'reviewed_at': _dt(event_request.reviewed_at),
        'decision_reason': event_request.decision_reason,
        'created_at': _dt(event_request.created_at),
        'updated_at': _dt(event_request.updated_at),
    }


def _parse_datetime(value):
    if value is None:
        raise Exception("datetime value is required")
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise Exception("datetime must be a string")
    v = value.strip()
    if not v:
        raise Exception("datetime must be a non-empty string")
    try:
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        return datetime.fromisoformat(v)
    except Exception as e:
        raise Exception("Invalid datetime format") from e


@event_scheduling_and_approval_bp.route('/clubs/<int:club_id>/events/propose', methods=['GET'])
def propose_event_form(club_id):
    club = Club.query.get_or_404(club_id)
    current_user = get_current_user()
    require_club_coordinator(current_user, club_id)
    return render_propose_event_form(club, current_user)


@event_scheduling_and_approval_bp.route('/clubs/<int:club_id>/events/propose', methods=['POST'])
def propose_event_submit(club_id):
    current_user = get_current_user()
    require_club_coordinator(current_user, club_id)

    payload = parse_event_request_payload(request)
    errors = validate_event_request_payload(payload)
    if errors:
        return jsonify(errors), 400

    start_at = _parse_datetime(payload['start_at'])
    end_at = _parse_datetime(payload['end_at'])
    if end_at <= start_at:
        return jsonify({'time': 'End time must be after start time.'}), 400

    time_conflicts = check_time_conflicts(start_at, end_at)
    if time_conflicts['conflicts']:
        return jsonify({'error': 'Time conflict detected.'}), 409

    event_request = EventRequest(
        club_id=club_id,
        proposed_by_user_id=current_user.id,
        title=payload['title'].strip(),
        description=payload.get('description'),
        location=payload.get('location'),
        start_at=start_at,
        end_at=end_at,
        status='PENDING',
        updated_at=datetime.utcnow(),
    )
    db.session.add(event_request)
    db.session.commit()
    return jsonify(serialize_event_request(event_request)), 201


@event_scheduling_and_approval_bp.route('/events/requests', methods=['GET'])
def list_event_requests():
    current_user = get_current_user()
    require_role(current_user, ['clubs_coordinator'])
    event_requests = EventRequest.query.order_by(EventRequest.created_at.desc()).all()
    return render_event_requests_list(event_requests, current_user, {})


@event_scheduling_and_approval_bp.route('/events/requests/<int:event_request_id>', methods=['GET'])
def get_event_request(event_request_id):
    current_user = get_current_user()
    event_request = EventRequest.query.get_or_404(event_request_id)
    return render_event_request_detail(event_request, current_user)


@event_scheduling_and_approval_bp.route('/events/requests/<int:event_request_id>/approve', methods=['POST'])
def approve_event_request(event_request_id):
    current_user = get_current_user()
    require_role(current_user, ['clubs_coordinator'])
    event_request = EventRequest.query.get_or_404(event_request_id)
    if not event_request.is_pending():
        return jsonify({'error': 'Event request is not pending.'}), 400
    payload = parse_event_request_payload(request)
    event_request.approve(current_user, payload.get('reason', 'Approved'))
    return jsonify(serialize_event_request(event_request)), 200


@event_scheduling_and_approval_bp.route('/events/requests/<int:event_request_id>/decline', methods=['POST'])
def decline_event_request(event_request_id):
    current_user = get_current_user()
    require_role(current_user, ['clubs_coordinator'])
    event_request = EventRequest.query.get_or_404(event_request_id)
    if not event_request.is_pending():
        return jsonify({'error': 'Event request is not pending.'}), 400
    payload = parse_event_request_payload(request)
    event_request.decline(current_user, payload.get('reason', 'Declined'))
    return jsonify(serialize_event_request(event_request)), 200


@event_scheduling_and_approval_bp.route('/clubs/<int:club_id>/events/requests', methods=['GET'])
def list_club_event_requests(club_id):
    current_user = get_current_user()
    require_club_coordinator(current_user, club_id)
    event_requests = EventRequest.query.filter_by(club_id=club_id).order_by(EventRequest.created_at.desc()).all()
    return render_event_requests_list(event_requests, current_user, {'club_id': club_id})