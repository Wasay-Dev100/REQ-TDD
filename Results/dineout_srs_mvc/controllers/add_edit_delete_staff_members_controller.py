from flask import Blueprint
from flask import request
from flask import jsonify
from flask import abort
from app import db
from models.staff_management_staff_member import StaffMember
from views.add_edit_delete_staff_members_views import render_staff_list
from views.add_edit_delete_staff_members_views import render_staff_form

add_edit_delete_staff_members_bp = Blueprint("add_edit_delete_staff_members", __name__)


@add_edit_delete_staff_members_bp.route("/admin/staff", methods=["GET"])
def list_staff():
    require_admin()
    staff_members = StaffMember.query.order_by(StaffMember.id.asc()).all()
    if wants_json_response():
        return jsonify([m.to_dict() for m in staff_members]), 200
    return render_staff_list(staff_members)


@add_edit_delete_staff_members_bp.route("/admin/staff/new", methods=["GET"])
def new_staff_form():
    require_admin()
    return render_staff_form("create", None, None)


@add_edit_delete_staff_members_bp.route("/admin/staff", methods=["POST"])
def create_staff():
    require_admin()
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict(flat=True)

    valid, errors = validate_staff_payload(payload, partial=False)
    if not valid:
        if wants_json_response():
            return jsonify(errors), 400
        return render_staff_form("create", None, errors), 400

    new_staff = StaffMember()
    new_staff.update_from_dict(payload)
    db.session.add(new_staff)
    db.session.commit()

    # Ensure attributes remain accessible after commit even if tests access outside context
    db.session.refresh(new_staff)
    db.session.expunge(new_staff)

    if wants_json_response():
        return jsonify(new_staff.to_dict()), 201
    return render_staff_form("edit", new_staff, None), 201


@add_edit_delete_staff_members_bp.route("/admin/staff/<int:staff_id>/edit", methods=["GET"])
def edit_staff_form(staff_id):
    require_admin()
    staff = get_staff_or_404(staff_id)
    return render_staff_form("edit", staff, None)


@add_edit_delete_staff_members_bp.route("/admin/staff/<int:staff_id>", methods=["PUT"])
def update_staff(staff_id):
    require_admin()
    staff = get_staff_or_404(staff_id)

    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict(flat=True)

    valid, errors = validate_staff_payload(payload, partial=True)
    if not valid:
        if wants_json_response():
            return jsonify(errors), 400
        return render_staff_form("edit", staff, errors), 400

    staff.update_from_dict(payload)
    db.session.commit()

    if wants_json_response():
        return jsonify(staff.to_dict()), 200
    return render_staff_form("edit", staff, None), 200


@add_edit_delete_staff_members_bp.route("/admin/staff/<int:staff_id>", methods=["DELETE"])
def delete_staff(staff_id):
    require_admin()
    staff = get_staff_or_404(staff_id)
    db.session.delete(staff)
    db.session.commit()
    if wants_json_response():
        return jsonify({"deleted": True, "id": staff_id}), 200
    return "", 204


def validate_staff_payload(payload, partial: bool):
    errors = {}
    if not isinstance(payload, dict):
        return False, {"payload": "Invalid payload."}

    required_fields = ["first_name", "last_name", "email", "role_title"]
    if not partial:
        for field in required_fields:
            value = payload.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors[field] = "This field is required."

    if "email" in payload:
        email = payload.get("email")
        if email is None or (isinstance(email, str) and not email.strip()) or "@" not in str(email):
            errors["email"] = "Invalid email address."

    if "is_active" in payload:
        val = payload.get("is_active")
        if isinstance(val, str):
            lowered = val.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                payload["is_active"] = True
            elif lowered in ("false", "0", "no", "off"):
                payload["is_active"] = False
            else:
                errors["is_active"] = "Invalid boolean value."
        elif val is not None and not isinstance(val, bool):
            errors["is_active"] = "Invalid boolean value."

    return len(errors) == 0, errors


def get_staff_or_404(staff_id):
    staff = db.session.get(StaffMember, staff_id)
    if not staff:
        abort(404)
    return staff


def wants_json_response():
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and (
        request.accept_mimetypes[best] >= request.accept_mimetypes["text/html"]
    )


def require_admin():
    return None