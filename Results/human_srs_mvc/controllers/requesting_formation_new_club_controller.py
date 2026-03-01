from flask import Blueprint, request, jsonify, render_template
from app import db
from models.user import User
from models.requesting_formation_new_club_club_proposal import ClubProposal
from views.requesting_formation_new_club_views import render_clubs_home, render_propose_new_club_form, render_club_proposal_detail

requesting_formation_new_club = Blueprint('requesting_formation_new_club', __name__)

@requesting_formation_new_club.route('/clubs', methods=['GET'])
def clubs_home():
    current_user = get_current_user()
    return render_clubs_home(current_user)

@requesting_formation_new_club.route('/clubs/propose', methods=['GET'])
def propose_new_club_form():
    current_user = get_current_user()
    return render_propose_new_club_form(current_user, errors=None, form_data=None)

@requesting_formation_new_club.route('/clubs/propose', methods=['POST'])
def submit_new_club_proposal():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'authentication_required'}), 401

    payload = request.json
    is_valid, errors = validate_club_proposal_payload(payload)
    if not is_valid:
        return jsonify({'error': 'invalid_payload', 'details': errors}), 400

    if ClubProposal.query.filter_by(club_name=payload['club_name']).first():
        return jsonify({'error': 'club_name_already_exists'}), 409

    new_proposal = ClubProposal(
        proposer_user_id=current_user.id,
        club_name=payload['club_name'],
        club_category=payload['club_category'],
        description=payload['description'],
        objectives=payload['objectives'],
        proposed_activities=payload['proposed_activities'],
        faculty_advisor_name=payload['faculty_advisor_name'],
        faculty_advisor_email=payload['faculty_advisor_email'],
        co_founders=payload['co_founders'],
        expected_members_count=payload['expected_members_count']
    )
    db.session.add(new_proposal)
    db.session.commit()

    return jsonify(new_proposal.to_dict()), 201

@requesting_formation_new_club.route('/clubs/proposals/<int:proposal_id>', methods=['GET'])
def get_club_proposal(proposal_id):
    proposal = ClubProposal.query.get(proposal_id)
    if not proposal:
        return jsonify({'error': 'proposal_not_found'}), 404
    return jsonify(proposal.to_dict()), 200

def get_current_user():
    # This function should return the current logged-in user
    # Placeholder implementation
    return User.query.first()

def validate_club_proposal_payload(payload):
    # Placeholder validation logic
    errors = {}
    required_fields = [
        'club_name', 'club_category', 'description', 'objectives',
        'proposed_activities', 'faculty_advisor_name', 'faculty_advisor_email',
        'co_founders', 'expected_members_count'
    ]
    for field in required_fields:
        if field not in payload:
            errors[field] = 'This field is required.'
    return (len(errors) == 0, errors)