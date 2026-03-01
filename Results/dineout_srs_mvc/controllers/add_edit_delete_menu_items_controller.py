from decimal import Decimal
from flask import Blueprint
from flask import request
from flask import jsonify
from flask import redirect
from flask import url_for
from flask import flash
from flask import abort
from app import db
from models.add_edit_delete_menu_items_menu_item import MenuItem
from views.add_edit_delete_menu_items_views import render_menu_item_list
from views.add_edit_delete_menu_items_views import render_menu_item_form

add_edit_delete_menu_items_bp = Blueprint("add_edit_delete_menu_items", __name__)


def require_admin(user):
    if user is None:
        return False
    return bool(getattr(user, "is_admin", False))


def validate_menu_item_payload(payload: dict, partial: bool = False):
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return False, {"payload": "Invalid payload."}

    errors = {}

    def _is_blank(v):
        return v is None or (isinstance(v, str) and not v.strip())

    if not partial:
        for field in ["name", "price"]:
            if field not in payload or _is_blank(payload.get(field)):
                errors[field] = "This field is required."

    if "name" in payload:
        if _is_blank(payload.get("name")):
            if not partial:
                errors.setdefault("name", "This field is required.")
        elif not isinstance(payload.get("name"), str):
            errors["name"] = "Invalid name."
        else:
            payload["name"] = payload["name"].strip()
            if not payload["name"]:
                errors["name"] = "Invalid name."

    if "price" in payload:
        if _is_blank(payload.get("price")):
            if not partial:
                errors.setdefault("price", "This field is required.")
        else:
            price_val = payload.get("price")
            try:
                dec = price_val if isinstance(price_val, Decimal) else Decimal(str(price_val))
                if dec < 0:
                    errors["price"] = "Price must be non-negative."
                else:
                    payload["price"] = dec
            except Exception:
                errors["price"] = "Invalid price."

    if "is_available" in payload:
        val = payload.get("is_available")
        if isinstance(val, bool):
            pass
        elif isinstance(val, (int, float)) and val in (0, 1):
            payload["is_available"] = bool(val)
        elif isinstance(val, str):
            lowered = val.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                payload["is_available"] = True
            elif lowered in ("false", "0", "no", "off", ""):
                payload["is_available"] = False
            else:
                errors["is_available"] = "Invalid boolean value."
        elif val is None:
            payload["is_available"] = False
        else:
            errors["is_available"] = "Invalid boolean value."

    if "description" in payload and payload.get("description") is not None:
        if not isinstance(payload.get("description"), str):
            errors["description"] = "Invalid description."

    if "image_url" in payload and payload.get("image_url") is not None:
        if not isinstance(payload.get("image_url"), str):
            errors["image_url"] = "Invalid image_url."

    return len(errors) == 0, errors


def get_menu_item_or_404(menu_item_id: int):
    menu_item = db.session.get(MenuItem, menu_item_id)
    if not menu_item:
        abort(404)
    return menu_item


@add_edit_delete_menu_items_bp.route("/admin/menu-items", methods=["GET"])
def list_menu_items():
    menu_items = MenuItem.query.order_by(MenuItem.id.asc()).all()
    return render_menu_item_list(menu_items)


@add_edit_delete_menu_items_bp.route("/admin/menu-items/new", methods=["GET"])
def new_menu_item_form():
    return render_menu_item_form(mode="new", menu_item=None, errors=None)


@add_edit_delete_menu_items_bp.route("/admin/menu-items", methods=["POST"])
def create_menu_item():
    payload = request.form.to_dict(flat=True)

    if "is_available" not in payload:
        payload["is_available"] = False

    is_valid, errors = validate_menu_item_payload(payload, partial=False)
    if not is_valid:
        return render_menu_item_form(mode="new", menu_item=None, errors=errors), 400

    menu_item = MenuItem()
    menu_item.update_from_dict(payload)
    db.session.add(menu_item)
    db.session.commit()

    flash("Menu item created successfully!", "success")
    return redirect(url_for("add_edit_delete_menu_items.list_menu_items"))


@add_edit_delete_menu_items_bp.route("/admin/menu-items/<int:menu_item_id>/edit", methods=["GET"])
def edit_menu_item_form(menu_item_id: int):
    menu_item = get_menu_item_or_404(menu_item_id)
    return render_menu_item_form(mode="edit", menu_item=menu_item, errors=None)


@add_edit_delete_menu_items_bp.route("/admin/menu-items/<int:menu_item_id>", methods=["POST"])
def update_menu_item(menu_item_id: int):
    menu_item = get_menu_item_or_404(menu_item_id)

    payload = request.form.to_dict(flat=True)
    payload["is_available"] = "is_available" in request.form

    is_valid, errors = validate_menu_item_payload(payload, partial=True)
    if not is_valid:
        return (
            render_menu_item_form(mode="edit", menu_item=menu_item, errors=errors),
            400,
        )

    menu_item.update_from_dict(payload)
    db.session.commit()

    flash("Menu item updated successfully!", "success")
    return redirect(url_for("add_edit_delete_menu_items.list_menu_items"))


@add_edit_delete_menu_items_bp.route(
    "/admin/menu-items/<int:menu_item_id>/delete", methods=["POST"]
)
def delete_menu_item(menu_item_id: int):
    menu_item = get_menu_item_or_404(menu_item_id)
    db.session.delete(menu_item)
    db.session.commit()
    flash("Menu item deleted successfully!", "success")
    return redirect(url_for("add_edit_delete_menu_items.list_menu_items"))


@add_edit_delete_menu_items_bp.route("/api/admin/menu-items", methods=["GET"])
def api_list_menu_items():
    menu_items = MenuItem.query.order_by(MenuItem.id.asc()).all()
    return jsonify([item.to_dict() for item in menu_items]), 200


@add_edit_delete_menu_items_bp.route("/api/admin/menu-items", methods=["POST"])
def api_create_menu_item():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}

    is_valid, errors = validate_menu_item_payload(payload, partial=False)
    if not is_valid:
        return jsonify(errors), 400

    menu_item = MenuItem()
    menu_item.update_from_dict(payload)
    db.session.add(menu_item)
    db.session.commit()
    return jsonify(menu_item.to_dict()), 201


@add_edit_delete_menu_items_bp.route("/api/admin/menu-items/<int:menu_item_id>", methods=["GET"])
def api_get_menu_item(menu_item_id: int):
    menu_item = db.session.get(MenuItem, menu_item_id)
    if not menu_item:
        return jsonify({"error": "Menu item not found"}), 404
    return jsonify(menu_item.to_dict()), 200


@add_edit_delete_menu_items_bp.route("/api/admin/menu-items/<int:menu_item_id>", methods=["PUT"])
def api_update_menu_item(menu_item_id: int):
    menu_item = db.session.get(MenuItem, menu_item_id)
    if not menu_item:
        return jsonify({"error": "Menu item not found"}), 404

    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}

    is_valid, errors = validate_menu_item_payload(payload, partial=True)
    if not is_valid:
        return jsonify(errors), 400

    menu_item.update_from_dict(payload)
    db.session.commit()
    return jsonify(menu_item.to_dict()), 200


@add_edit_delete_menu_items_bp.route(
    "/api/admin/menu-items/<int:menu_item_id>", methods=["DELETE"]
)
def api_delete_menu_item(menu_item_id: int):
    menu_item = db.session.get(MenuItem, menu_item_id)
    if not menu_item:
        return jsonify({"error": "Menu item not found"}), 404

    db.session.delete(menu_item)
    db.session.commit()
    return jsonify({"message": "Menu item deleted successfully"}), 200