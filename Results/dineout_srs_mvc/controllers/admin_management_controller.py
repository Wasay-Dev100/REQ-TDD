from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from app import db
from models.user import User
from models.product import Product
from models.admin_management_inventory_item import InventoryItem
from models.admin_management_inventory_transaction import InventoryTransaction

admin_management_bp = Blueprint("admin_management", __name__)


def require_admin(user: User):
    if not user or not isinstance(user, User) or not user.is_admin():
        raise PermissionError("Admin access required")


def get_request_json() -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValueError("Invalid or missing JSON payload")
    if not isinstance(payload, dict):
        raise TypeError("JSON payload must be an object")
    return payload


def validate_staff_payload(payload: dict, partial: bool) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")

    allowed = {"email", "username", "password", "role", "is_active"}
    unknown = set(payload.keys()) - allowed
    if unknown:
        raise ValueError("Unknown fields: " + ",".join(sorted(unknown)))

    required = [] if partial else ["email", "username", "password", "role"]
    for k in required:
        if k not in payload:
            raise ValueError(f"Missing required field: {k}")

    out = {}
    if "email" in payload:
        if not isinstance(payload["email"], str) or not payload["email"].strip():
            raise ValueError("email must be a non-empty string")
        out["email"] = payload["email"].strip()

    if "username" in payload:
        if not isinstance(payload["username"], str) or not payload["username"].strip():
            raise ValueError("username must be a non-empty string")
        out["username"] = payload["username"].strip()

    if "password" in payload:
        if not isinstance(payload["password"], str) or not payload["password"]:
            raise ValueError("password must be a non-empty string")
        out["password"] = payload["password"]

    if "role" in payload:
        if payload["role"] not in {"admin", "staff"}:
            raise ValueError("role must be one of: admin, staff")
        out["role"] = payload["role"]

    if "is_active" in payload:
        if not isinstance(payload["is_active"], bool):
            raise TypeError("is_active must be a boolean")
        out["is_active"] = payload["is_active"]

    return out


def validate_menu_item_payload(payload: dict, partial: bool) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")

    allowed = {"name", "price", "description", "is_available"}
    unknown = set(payload.keys()) - allowed
    if unknown:
        raise ValueError("Unknown fields: " + ",".join(sorted(unknown)))

    required = [] if partial else ["name", "price"]
    for k in required:
        if k not in payload:
            raise ValueError(f"Missing required field: {k}")

    out = {}
    if "name" in payload:
        if not isinstance(payload["name"], str) or not payload["name"].strip():
            raise ValueError("name must be a non-empty string")
        out["name"] = payload["name"].strip()

    if "description" in payload:
        if payload["description"] is not None and not isinstance(payload["description"], str):
            raise TypeError("description must be a string or None")
        out["description"] = payload["description"]

    if "price" in payload:
        try:
            price = Decimal(str(payload["price"]))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("price must be a valid decimal")
        if price < 0:
            raise ValueError("price must be >= 0")
        out["price"] = price

    if "is_available" in payload:
        if not isinstance(payload["is_available"], bool):
            raise TypeError("is_available must be a boolean")
        out["is_available"] = payload["is_available"]

    return out


def validate_inventory_item_payload(payload: dict, partial: bool) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")

    allowed = {"sku", "name", "unit", "stock_quantity", "reorder_level", "is_active"}
    unknown = set(payload.keys()) - allowed
    if unknown:
        raise ValueError("Unknown fields: " + ",".join(sorted(unknown)))

    required = [] if partial else ["sku", "name", "unit"]
    for k in required:
        if k not in payload:
            raise ValueError(f"Missing required field: {k}")

    out = {}
    if "sku" in payload:
        if not isinstance(payload["sku"], str) or not payload["sku"].strip():
            raise ValueError("sku must be a non-empty string")
        out["sku"] = payload["sku"].strip()

    if "name" in payload:
        if not isinstance(payload["name"], str) or not payload["name"].strip():
            raise ValueError("name must be a non-empty string")
        out["name"] = payload["name"].strip()

    if "unit" in payload:
        if not isinstance(payload["unit"], str) or not payload["unit"].strip():
            raise ValueError("unit must be a non-empty string")
        out["unit"] = payload["unit"].strip()

    if "stock_quantity" in payload:
        if not isinstance(payload["stock_quantity"], int):
            raise TypeError("stock_quantity must be an int")
        out["stock_quantity"] = payload["stock_quantity"]

    if "reorder_level" in payload:
        if not isinstance(payload["reorder_level"], int):
            raise TypeError("reorder_level must be an int")
        out["reorder_level"] = payload["reorder_level"]

    if "is_active" in payload:
        if not isinstance(payload["is_active"], bool):
            raise TypeError("is_active must be a boolean")
        out["is_active"] = payload["is_active"]

    return out


def validate_adjust_stock_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")

    allowed = {"delta", "reason"}
    unknown = set(payload.keys()) - allowed
    if unknown:
        raise ValueError("Unknown fields: " + ",".join(sorted(unknown)))

    if "delta" not in payload:
        raise ValueError("Missing required field: delta")
    if not isinstance(payload["delta"], int):
        raise TypeError("delta must be an int")

    out = {"delta": payload["delta"]}
    if "reason" in payload:
        if payload["reason"] is not None and not isinstance(payload["reason"], str):
            raise TypeError("reason must be a string or None")
        out["reason"] = payload["reason"]
    return out


def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "role": u.role,
        "is_active": bool(u.is_active),
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "updated_at": u.updated_at.isoformat() if u.updated_at else None,
    }


def _error_response(exc: Exception, status_code: int = 400):
    return jsonify({"error": exc.__class__.__name__, "message": str(exc)}), status_code


@admin_management_bp.route("/admin/staff", methods=["GET"])
def list_staff():
    try:
        staff = User.query.filter_by(role="staff").all()
        return jsonify([_user_to_dict(u) for u in staff]), 200
    except Exception as e:
        return _error_response(e, 500)


@admin_management_bp.route("/admin/staff", methods=["POST"])
def create_staff():
    try:
        payload = validate_staff_payload(get_request_json(), partial=False)

        if User.query.filter_by(email=payload["email"]).first() is not None:
            raise ValueError("email already exists")
        if User.query.filter_by(username=payload["username"]).first() is not None:
            raise ValueError("username already exists")

        u = User(
            email=payload["email"],
            username=payload["username"],
            role=payload["role"],
            is_active=payload.get("is_active", True),
        )
        u.set_password(payload["password"])
        db.session.add(u)
        db.session.commit()
        return jsonify(_user_to_dict(u)), 201
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 400)


@admin_management_bp.route("/admin/staff/<int:user_id>", methods=["GET"])
def get_staff(user_id: int):
    try:
        u = User.query.filter_by(id=user_id).first()
        if u is None:
            raise ValueError("staff not found")
        return jsonify(_user_to_dict(u)), 200
    except Exception as e:
        return _error_response(e, 404)


@admin_management_bp.route("/admin/staff/<int:user_id>", methods=["PUT"])
def update_staff(user_id: int):
    try:
        payload = validate_staff_payload(get_request_json(), partial=True)
        u = User.query.filter_by(id=user_id).first()
        if u is None:
            raise ValueError("staff not found")

        if "email" in payload and payload["email"] != u.email:
            if User.query.filter_by(email=payload["email"]).first() is not None:
                raise ValueError("email already exists")
            u.email = payload["email"]

        if "username" in payload and payload["username"] != u.username:
            if User.query.filter_by(username=payload["username"]).first() is not None:
                raise ValueError("username already exists")
            u.username = payload["username"]

        if "role" in payload:
            u.role = payload["role"]
        if "is_active" in payload:
            u.is_active = payload["is_active"]
        if "password" in payload:
            u.set_password(payload["password"])

        db.session.commit()
        return jsonify(_user_to_dict(u)), 200
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 400)


@admin_management_bp.route("/admin/staff/<int:user_id>", methods=["DELETE"])
def delete_staff(user_id: int):
    try:
        u = User.query.filter_by(id=user_id).first()
        if u is None:
            raise ValueError("staff not found")
        db.session.delete(u)
        db.session.commit()
        return jsonify({"deleted": True}), 200
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 404)


@admin_management_bp.route("/admin/menu", methods=["GET"])
def list_menu_items():
    try:
        items = Product.query.all()
        return jsonify([p.to_dict() for p in items]), 200
    except Exception as e:
        return _error_response(e, 500)


@admin_management_bp.route("/admin/menu", methods=["POST"])
def create_menu_item():
    try:
        payload = validate_menu_item_payload(get_request_json(), partial=False)

        if Product.query.filter_by(name=payload["name"]).first() is not None:
            raise ValueError("name already exists")

        p = Product(
            name=payload["name"],
            price=payload["price"],
            description=payload.get("description"),
            is_available=payload.get("is_available", True),
        )
        db.session.add(p)
        db.session.commit()
        return jsonify(p.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 400)


@admin_management_bp.route("/admin/menu/<int:product_id>", methods=["GET"])
def get_menu_item(product_id: int):
    try:
        p = Product.query.filter_by(id=product_id).first()
        if p is None:
            raise ValueError("menu item not found")
        return jsonify(p.to_dict()), 200
    except Exception as e:
        return _error_response(e, 404)


@admin_management_bp.route("/admin/menu/<int:product_id>", methods=["PUT"])
def update_menu_item(product_id: int):
    try:
        payload = validate_menu_item_payload(get_request_json(), partial=True)
        p = Product.query.filter_by(id=product_id).first()
        if p is None:
            raise ValueError("menu item not found")

        if "name" in payload and payload["name"] != p.name:
            if Product.query.filter_by(name=payload["name"]).first() is not None:
                raise ValueError("name already exists")
            p.name = payload["name"]

        if "price" in payload:
            p.price = payload["price"]
        if "description" in payload:
            p.description = payload["description"]
        if "is_available" in payload:
            p.is_available = payload["is_available"]

        db.session.commit()
        return jsonify(p.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 400)


@admin_management_bp.route("/admin/menu/<int:product_id>", methods=["DELETE"])
def delete_menu_item(product_id: int):
    try:
        p = Product.query.filter_by(id=product_id).first()
        if p is None:
            raise ValueError("menu item not found")
        db.session.delete(p)
        db.session.commit()
        return jsonify({"deleted": True}), 200
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 404)


@admin_management_bp.route("/admin/inventory", methods=["GET"])
def list_inventory_items():
    try:
        items = InventoryItem.query.all()
        return jsonify([i.to_dict() for i in items]), 200
    except Exception as e:
        return _error_response(e, 500)


@admin_management_bp.route("/admin/inventory", methods=["POST"])
def create_inventory_item():
    try:
        payload = validate_inventory_item_payload(get_request_json(), partial=False)

        if InventoryItem.query.filter_by(sku=payload["sku"]).first() is not None:
            raise ValueError("sku already exists")

        item = InventoryItem(
            sku=payload["sku"],
            name=payload["name"],
            unit=payload["unit"],
            stock_quantity=payload.get("stock_quantity", 0),
            reorder_level=payload.get("reorder_level", 0),
            is_active=payload.get("is_active", True),
        )
        db.session.add(item)
        db.session.commit()
        return jsonify(item.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 400)


@admin_management_bp.route("/admin/inventory/<int:item_id>", methods=["GET"])
def get_inventory_item(item_id: int):
    try:
        item = InventoryItem.query.filter_by(id=item_id).first()
        if item is None:
            raise ValueError("inventory item not found")
        return jsonify(item.to_dict()), 200
    except Exception as e:
        return _error_response(e, 404)


@admin_management_bp.route("/admin/inventory/<int:item_id>", methods=["PUT"])
def update_inventory_item(item_id: int):
    try:
        payload = validate_inventory_item_payload(get_request_json(), partial=True)
        item = InventoryItem.query.filter_by(id=item_id).first()
        if item is None:
            raise ValueError("inventory item not found")

        if "sku" in payload and payload["sku"] != item.sku:
            if InventoryItem.query.filter_by(sku=payload["sku"]).first() is not None:
                raise ValueError("sku already exists")
            item.sku = payload["sku"]

        for k in ["name", "unit", "stock_quantity", "reorder_level", "is_active"]:
            if k in payload:
                setattr(item, k, payload[k])

        db.session.commit()
        return jsonify(item.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 400)


@admin_management_bp.route("/admin/inventory/<int:item_id>", methods=["DELETE"])
def delete_inventory_item(item_id: int):
    try:
        item = InventoryItem.query.filter_by(id=item_id).first()
        if item is None:
            raise ValueError("inventory item not found")
        db.session.delete(item)
        db.session.commit()
        return jsonify({"deleted": True}), 200
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 404)


@admin_management_bp.route("/admin/inventory/<int:item_id>/adjust", methods=["POST"])
def adjust_inventory_stock(item_id: int):
    try:
        payload = validate_adjust_stock_payload(get_request_json())
        item = InventoryItem.query.filter_by(id=item_id).first()
        if item is None:
            raise ValueError("inventory item not found")

        item.adjust_stock(payload["delta"])

        tx = InventoryTransaction(
            inventory_item_id=item.id,
            admin_user_id=0,
            delta=payload["delta"],
            reason=payload.get("reason"),
        )
        db.session.add(tx)
        db.session.commit()
        return jsonify({"inventory_item": item.to_dict(), "transaction": tx.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return _error_response(e, 400)