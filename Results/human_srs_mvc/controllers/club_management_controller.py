from flask import Blueprint, request, jsonify, render_template
from app import db
from models.club_management_club import Club
from models.club_management_club_event_image import ClubEventImage
from models.user import User
from views.club_management_views import render_club_list, render_club_detail, render_club_edit_form

club_management_bp = Blueprint('club_management', __name__)

def get_current_user():
    # Placeholder for actual user retrieval logic
    return User.query.first()

def require_roles(user, allowed_roles):
    if user.role not in allowed_roles:
        raise PermissionError("User does not have the required role.")

def can_edit_club(user, club):
    # Placeholder for actual permission check logic
    return True

def parse_update_club_payload(request):
    return request.get_json()

def validate_update_club_payload(payload):
    # Placeholder for actual validation logic
    return payload

def parse_add_event_image_payload(request):
    return request.get_json()

def validate_add_event_image_payload(payload):
    # Placeholder for actual validation logic
    return payload

@club_management_bp.route('/clubs', methods=['GET'])
def list_clubs():
    clubs = Club.query.all()
    return render_club_list(clubs)

@club_management_bp.route('/clubs/<int:club_id>', methods=['GET'])
def view_club(club_id):
    club = Club.query.get_or_404(club_id)
    event_images = ClubEventImage.query.filter_by(club_id=club_id).all()
    can_edit = can_edit_club(get_current_user(), club)
    return render_club_detail(club, event_images, can_edit)

@club_management_bp.route('/clubs/<int:club_id>/edit', methods=['GET'])
def edit_club_form(club_id):
    club = Club.query.get_or_404(club_id)
    require_roles(get_current_user(), ['club_coordinator', 'club_head', 'student_council_clubs_coordinator', 'admin'])
    return render_club_edit_form(club)

@club_management_bp.route('/clubs/<int:club_id>', methods=['PUT'])
def update_club(club_id):
    club = Club.query.get_or_404(club_id)
    user = get_current_user()
    if not can_edit_club(user, club):
        return jsonify({"error": "Forbidden", "message": "You do not have permission to edit this club."}), 403

    payload = parse_update_club_payload(request)
    validated_payload = validate_update_club_payload(payload)

    club.description = validated_payload['description']
    club.members_list = validated_payload['members_list']
    club.contact_name = validated_payload['contact']['name']
    club.contact_email = validated_payload['contact']['email']
    club.contact_phone = validated_payload['contact']['phone']
    club.touch_updated_at()

    db.session.commit()

    return jsonify({
        "id": club.id,
        "slug": club.slug,
        "name": club.name,
        "description": club.description,
        "members_list": club.members_list,
        "contact": {
            "name": club.contact_name,
            "email": club.contact_email,
            "phone": club.contact_phone
        },
        "updated_at": club.updated_at.isoformat()
    })

@club_management_bp.route('/clubs/<int:club_id>/event-images', methods=['POST'])
def add_event_image(club_id):
    user = get_current_user()
    club = Club.query.get_or_404(club_id)
    if not can_edit_club(user, club):
        return jsonify({"error": "Forbidden", "message": "You do not have permission to add event images to this club."}), 403

    payload = parse_add_event_image_payload(request)
    validated_payload = validate_add_event_image_payload(payload)

    event_image = ClubEventImage(
        club_id=club_id,
        title=validated_payload['title'],
        image_url=validated_payload['image_url'],
        event_date=validated_payload['event_date']
    )

    db.session.add(event_image)
    db.session.commit()

    return jsonify({
        "id": event_image.id,
        "club_id": event_image.club_id,
        "title": event_image.title,
        "image_url": event_image.image_url,
        "event_date": event_image.event_date.isoformat(),
        "created_at": event_image.created_at.isoformat()
    }), 201

@club_management_bp.route('/clubs/<int:club_id>/event-images/<int:image_id>', methods=['DELETE'])
def delete_event_image(club_id, image_id):
    user = get_current_user()
    club = Club.query.get_or_404(club_id)
    if not can_edit_club(user, club):
        return jsonify({"error": "Forbidden", "message": "You do not have permission to delete event images from this club."}), 403

    event_image = ClubEventImage.query.get_or_404(image_id)
    db.session.delete(event_image)
    db.session.commit()

    return '', 204