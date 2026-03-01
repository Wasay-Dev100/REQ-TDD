from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request

from app import db
from models.hall_manager_operations_bill import HallManagerOperationsBill
from models.hall_manager_operations_notification import HallManagerOperationsNotification
from models.hall_manager_operations_order import HallManagerOperationsOrder
from models.hall_manager_operations_table import HallManagerOperationsTable
from models.user import User

hall_manager_operations_bp = Blueprint("hall_manager_operations_bp", __name__, url_prefix="")


def require_hall_manager(user: User):
    if user is None:
        return jsonify({"error": "Unauthorized"}), 401
    if user.role != "hall_manager":
        return jsonify({"error": "Forbidden"}), 403
    return None


def get_current_user() -> User:
    return User.query.first()


def parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    try:
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        return datetime.fromisoformat(v)
    except Exception:
        return None


def _error_400(message: str, details: dict | None = None):
    return jsonify({"error": message, "details": details}), 400


def _error_404(message: str):
    return jsonify({"error": message}), 404


def _error_409(message: str):
    return jsonify({"error": message}), 409


def _require_json_object():
    payload = request.get_json(silent=True)
    if payload is None or not isinstance(payload, dict):
        return None
    return payload


@hall_manager_operations_bp.route("/hall-manager/tables", methods=["GET"])
def list_tables():
    user = get_current_user()
    auth = require_hall_manager(user)
    if auth is not None:
        return auth

    tables = HallManagerOperationsTable.query.order_by(HallManagerOperationsTable.table_number.asc()).all()
    return jsonify({"tables": [t.to_dict() for t in tables]}), 200


@hall_manager_operations_bp.route("/hall-manager/tables/<int:table_id>", methods=["GET"])
def get_table(table_id: int):
    user = get_current_user()
    auth = require_hall_manager(user)
    if auth is not None:
        return auth

    table = HallManagerOperationsTable.query.filter_by(id=table_id).first()
    if table is None:
        return _error_404("Not found")
    return jsonify({"table": table.to_dict()}), 200


@hall_manager_operations_bp.route("/hall-manager/tables/<int:table_id>/status", methods=["PATCH"])
def update_table_status(table_id: int):
    user = get_current_user()
    auth = require_hall_manager(user)
    if auth is not None:
        return auth

    payload = _require_json_object()
    if payload is None:
        return _error_400("Invalid JSON", None)

    if "status" not in payload:
        return _error_400("Missing required field", {"status": "required"})

    status = payload.get("status")
    allowed = {"available", "reserved", "occupied", "out_of_service"}
    if status not in allowed:
        return _error_400("Invalid status", {"allowed_values": sorted(allowed)})

    table = HallManagerOperationsTable.query.filter_by(id=table_id).first()
    if table is None:
        return _error_404("Not found")

    table.status = status
    if "reserved_by_name" in payload:
        table.reserved_by_name = payload.get("reserved_by_name")
    if "reserved_by_phone" in payload:
        table.reserved_by_phone = payload.get("reserved_by_phone")
    if "reservation_time" in payload:
        table.reservation_time = parse_iso_datetime(payload.get("reservation_time"))
    if "notes" in payload:
        table.notes = payload.get("notes")

    table.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"table": table.to_dict()}), 200


@hall_manager_operations_bp.route("/hall-manager/reservations", methods=["POST"])
def create_or_update_reservation():
    user = get_current_user()
    auth = require_hall_manager(user)
    if auth is not None:
        return auth

    payload = _require_json_object()
    if payload is None:
        return _error_400("Invalid JSON", None)

    if "table_id" not in payload or "status" not in payload:
        return _error_400("Missing required fields", {"required_fields": ["table_id", "status"]})

    table_id = payload.get("table_id")
    if not isinstance(table_id, int):
        return _error_400("Invalid table_id", {"table_id": "must be int"})

    status = payload.get("status")
    allowed = {"reserved", "available"}
    if status not in allowed:
        return _error_400("Invalid status", {"allowed_values": sorted(allowed)})

    table = HallManagerOperationsTable.query.filter_by(id=table_id).first()
    if table is None:
        return _error_404("Not found")

    table.status = status
    if status == "available":
        table.reserved_by_name = None
        table.reserved_by_phone = None
        table.reservation_time = None
        table.notes = None
    else:
        if "reserved_by_name" in payload:
            table.reserved_by_name = payload.get("reserved_by_name")
        if "reserved_by_phone" in payload:
            table.reserved_by_phone = payload.get("reserved_by_phone")
        if "reservation_time" in payload:
            table.reservation_time = parse_iso_datetime(payload.get("reservation_time"))
        if "notes" in payload:
            table.notes = payload.get("notes")

    table.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"table": table.to_dict()}), 200


@hall_manager_operations_bp.route("/hall-manager/reservations/<int:table_id>", methods=["DELETE"])
def clear_reservation(table_id: int):
    user = get_current_user()
    auth = require_hall_manager(user)
    if auth is not None:
        return auth

    table = HallManagerOperationsTable.query.filter_by(id=table_id).first()
    if table is None:
        return _error_404("Not found")

    table.status = "available"
    table.reserved_by_name = None
    table.reserved_by_phone = None
    table.reservation_time = None
    table.notes = None
    table.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"table": table.to_dict()}), 200


@hall_manager_operations_bp.route("/hall-manager/bills/<int:bill_id>/pay", methods=["POST"])
def mark_bill_paid(bill_id: int):
    user = get_current_user()
    auth = require_hall_manager(user)
    if auth is not None:
        return auth

    payload = _require_json_object()
    if payload is None:
        return _error_400("Invalid JSON", None)

    if "payment_method" not in payload:
        return _error_400("Missing required field", {"payment_method": "required"})

    payment_method = payload.get("payment_method")
    allowed_methods = {"cash", "card", "other"}
    if payment_method not in allowed_methods:
        return _error_400("Invalid payment_method", {"allowed_values": sorted(allowed_methods)})

    bill = HallManagerOperationsBill.query.filter_by(id=bill_id).first()
    if bill is None:
        return _error_404("Not found")

    if bill.status == "paid":
        return _error_409("Bill already paid")

    amount_paid = payload.get("amount_paid", None)
    if amount_paid is not None:
        try:
            amount_paid = float(amount_paid)
        except (TypeError, ValueError):
            return _error_400("Invalid amount_paid", {"amount_paid": "must be float"})
    else:
        amount_paid = None

    bill.mark_paid(paid_by_user_id=user.id if user else None, payment_method=payment_method, amount_paid=amount_paid)
    db.session.commit()
    return jsonify({"bill": bill.to_dict()}), 200


@hall_manager_operations_bp.route("/hall-manager/notifications", methods=["GET"])
def list_notifications():
    user = get_current_user()
    auth = require_hall_manager(user)
    if auth is not None:
        return auth

    is_read_raw = request.args.get("is_read", default=None, type=str)
    limit = request.args.get("limit", default=None, type=int)
    offset = request.args.get("offset", default=None, type=int)

    query = HallManagerOperationsNotification.query.order_by(HallManagerOperationsNotification.created_at.desc())

    if is_read_raw is not None:
        v = is_read_raw.strip().lower()
        if v in {"true", "1", "yes"}:
            query = query.filter_by(is_read=True)
        elif v in {"false", "0", "no"}:
            query = query.filter_by(is_read=False)
        else:
            return _error_400("Invalid is_read", {"is_read": "must be bool"})

    if offset is not None:
        if offset < 0:
            return _error_400("Invalid offset", {"offset": "must be >= 0"})
        query = query.offset(offset)

    if limit is not None:
        if limit < 0:
            return _error_400("Invalid limit", {"limit": "must be >= 0"})
        query = query.limit(limit)

    notifications = query.all()
    return jsonify({"notifications": [n.to_dict() for n in notifications]}), 200


@hall_manager_operations_bp.route("/hall-manager/notifications/<int:notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id: int):
    user = get_current_user()
    auth = require_hall_manager(user)
    if auth is not None:
        return auth

    payload = _require_json_object()
    is_read = True
    if payload is not None and "is_read" in payload:
        if not isinstance(payload["is_read"], bool):
            return _error_400("Invalid is_read", {"is_read": "must be bool"})
        is_read = payload["is_read"]

    notification = HallManagerOperationsNotification.query.filter_by(id=notification_id).first()
    if notification is None:
        return _error_404("Not found")

    notification.is_read = is_read
    db.session.commit()
    return jsonify({"notification": notification.to_dict()}), 200


@hall_manager_operations_bp.route("/hall-manager/firebase/sync", methods=["POST"])
def sync_from_firebase():
    user = get_current_user()
    auth = require_hall_manager(user)
    if auth is not None:
        return auth

    payload = _require_json_object()
    if payload is None:
        return _error_400("Invalid JSON", None)

    for key in ("tables", "orders", "events"):
        if key not in payload:
            return _error_400("Missing required field", {"missing": key})
        if not isinstance(payload[key], list):
            return _error_400("Invalid field type", {key: "must be list[dict]"})

    synced_tables = 0
    synced_orders = 0
    synced_events = 0

    firebase_table_id_to_local_id: dict[str, int] = {}

    for t in payload["tables"]:
        if not isinstance(t, dict):
            continue
        firebase_table_id = t.get("firebase_table_id")
        if not isinstance(firebase_table_id, str) or not firebase_table_id:
            continue

        table = HallManagerOperationsTable.query.filter_by(firebase_table_id=firebase_table_id).first()
        if table is None:
            table = HallManagerOperationsTable(firebase_table_id=firebase_table_id)
            db.session.add(table)

        if "table_number" in t:
            table.table_number = t.get("table_number")
        if "capacity" in t:
            table.capacity = t.get("capacity")
        if "status" in t:
            table.status = t.get("status")
        table.reserved_by_name = t.get("reserved_by_name")
        table.reserved_by_phone = t.get("reserved_by_phone")
        table.reservation_time = parse_iso_datetime(t.get("reservation_time"))
        table.notes = t.get("notes")

        parsed_updated_at = parse_iso_datetime(t.get("updated_at"))
        table.updated_at = parsed_updated_at or datetime.utcnow()

        db.session.flush()
        if table.id is not None:
            firebase_table_id_to_local_id[firebase_table_id] = int(table.id)
        synced_tables += 1

    for o in payload["orders"]:
        if not isinstance(o, dict):
            continue
        firebase_order_id = o.get("firebase_order_id")
        if not isinstance(firebase_order_id, str) or not firebase_order_id:
            continue

        firebase_table_id = o.get("firebase_table_id")
        table_id = None
        if isinstance(firebase_table_id, str) and firebase_table_id in firebase_table_id_to_local_id:
            table_id = firebase_table_id_to_local_id[firebase_table_id]
        elif isinstance(firebase_table_id, str) and firebase_table_id:
            table = HallManagerOperationsTable.query.filter_by(firebase_table_id=firebase_table_id).first()
            if table is not None:
                table_id = table.id

        if table_id is None:
            continue

        order = HallManagerOperationsOrder.query.filter_by(firebase_order_id=firebase_order_id).first()
        if order is None:
            order = HallManagerOperationsOrder(firebase_order_id=firebase_order_id)
            db.session.add(order)

        order.table_id = int(table_id)
        if "status" in o:
            order.status = o.get("status")
        if "total_amount" in o:
            try:
                order.total_amount = Decimal(str(o.get("total_amount")))
            except (InvalidOperation, TypeError, ValueError):
                order.total_amount = Decimal("0.00")
        if "currency" in o:
            order.currency = o.get("currency")
        order.completed_at = parse_iso_datetime(o.get("completed_at"))

        parsed_updated_at = parse_iso_datetime(o.get("updated_at"))
        order.updated_at = parsed_updated_at or datetime.utcnow()

        db.session.flush()
        synced_orders += 1

    for e in payload["events"]:
        if not isinstance(e, dict):
            continue
        firebase_event_id = e.get("firebase_event_id")
        if not isinstance(firebase_event_id, str) or not firebase_event_id:
            continue

        event = HallManagerOperationsNotification.query.filter_by(firebase_event_id=firebase_event_id).first()
        if event is None:
            event = HallManagerOperationsNotification(firebase_event_id=firebase_event_id)
            db.session.add(event)

        event.event_type = e.get("event_type")
        event.message = e.get("message")

        firebase_order_id = e.get("firebase_order_id")
        if isinstance(firebase_order_id, str) and firebase_order_id:
            order = HallManagerOperationsOrder.query.filter_by(firebase_order_id=firebase_order_id).first()
            event.order_id = order.id if order is not None else None
        else:
            event.order_id = None

        firebase_table_id = e.get("firebase_table_id")
        if isinstance(firebase_table_id, str) and firebase_table_id:
            table = HallManagerOperationsTable.query.filter_by(firebase_table_id=firebase_table_id).first()
            event.table_id = table.id if table is not None else None
        else:
            event.table_id = None

        created_at = parse_iso_datetime(e.get("created_at"))
        event.created_at = created_at or datetime.utcnow()

        synced_events += 1

    db.session.commit()
    return jsonify({"synced": {"tables": synced_tables, "orders": synced_orders, "events": synced_events}}), 200