from flask import Blueprint, request, jsonify
from app import db
from models.user import User
from models.approving_new_club_requests_club_proposal import ClubProposal

approving_new_club_requests_bp = Blueprint('approving_new_club_requests', __name__)

def get_current_user():
    # Placeholder for actual user retrieval logic
    return User.query.first()

def require_login(user):
    if not user or not user.is_active:
        raise PermissionError("User must be logged in and active")

def require_manage_access(user):
    if user.role not in ['Coordinator', 'Admin']:
        raise PermissionError("User does not have manage access")

def require_role(user, allowed_roles):
    if user.role not in allowed_roles:
        raise PermissionError("User role not allowed")

def parse_decision_payload(request_json):
    return {
        'decision': request_json.get('decision'),
        'notes': request_json.get('notes')
    }

def serialize_club_proposal(proposal):
    return {
        'id': proposal.id,
        'proposed_name': proposal.proposed_name,
        'description': proposal.description,
        'mission_statement': proposal.mission_statement,
        'status': proposal.status,
        'created_at': proposal.created_at.isoformat(),
        'updated_at': proposal.updated_at.isoformat()
    }

@approving_new_club_requests_bp.route('/manage/pending-new-club-requests', methods=['GET'])
def list_pending_new_club_requests():
    user = get_current_user()
    require_login(user)
    require_manage_access(user)
    proposals = ClubProposal.query.filter_by(status='PENDING_COORDINATOR').all()
    return jsonify([serialize_club_proposal(p) for p in proposals])

@approving_new_club_requests_bp.route('/manage/pending-new-club-requests/<int:proposal_id>', methods=['GET'])
def get_new_club_request_detail(proposal_id):
    user = get_current_user()
    require_login(user)
    require_manage_access(user)
    proposal = ClubProposal.query.get_or_404(proposal_id)
    return jsonify(serialize_club_proposal(proposal))

@approving_new_club_requests_bp.route('/manage/pending-new-club-requests/<int:proposal_id>/coordinator-decision', methods=['POST'])
def coordinator_decide_new_club_request(proposal_id):
    user = get_current_user()
    require_login(user)
    require_role(user, ['Coordinator'])
    proposal = ClubProposal.query.get_or_404(proposal_id)
    payload = parse_decision_payload(request.json)
    proposal.apply_coordinator_decision(user, payload['decision'], payload['notes'])
    return jsonify({'message': 'Coordinator decision applied successfully'})

@approving_new_club_requests_bp.route('/manage/pending-new-club-requests/admin-review', methods=['GET'])
def list_admin_review_new_club_requests():
    user = get_current_user()
    require_login(user)
    require_role(user, ['Admin'])
    proposals = ClubProposal.query.filter_by(status='APPROVED_BY_COORDINATOR').all()
    return jsonify([serialize_club_proposal(p) for p in proposals])

@approving_new_club_requests_bp.route('/manage/pending-new-club-requests/<int:proposal_id>/admin-decision', methods=['POST'])
def admin_decide_new_club_request(proposal_id):
    user = get_current_user()
    require_login(user)
    require_role(user, ['Admin'])
    proposal = ClubProposal.query.get_or_404(proposal_id)
    payload = parse_decision_payload(request.json)
    proposal.apply_admin_decision(user, payload['decision'], payload['notes'])
    return jsonify({'message': 'Admin decision applied successfully'})