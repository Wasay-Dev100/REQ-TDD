from flask import Blueprint
from flask import jsonify
from app import db
from models.manager_interface_table import ManagerInterfaceTable
from models.manager_interface_order import ManagerInterfaceOrder
from datetime import datetime
from decimal import Decimal

manager_interface_bp = Blueprint("manager_interface", __name__)


@manager_interface_bp.route("/manager/tables/free", methods=["GET"])
def view_free_tables():
    free_tables = ManagerInterfaceTable.query.filter_by(status="free").all()
    return jsonify([serialize_table(table) for table in free_tables]), 200


@manager_interface_bp.route("/manager/orders/<int:order_id>/mark_paid", methods=["POST"])
def mark_order_paid(order_id):
    order = ManagerInterfaceOrder.query.get(order_id)
    if not order or order.is_paid():
        return jsonify({"error": "Order not found or already paid"}), 404

    order.mark_paid(get_utcnow())
    db.session.add(order)
    db.session.commit()
    return jsonify(serialize_order(order)), 200


def serialize_table(table) -> dict:
    return {
        "id": table.id,
        "table_number": table.table_number,
        "status": table.status,
    }


def serialize_order(order) -> dict:
    total_amount = order.total_amount
    if isinstance(total_amount, Decimal):
        total_amount_str = format(total_amount, "f")
    else:
        total_amount_str = str(total_amount) if total_amount is not None else None

    return {
        "id": order.id,
        "table_id": order.table_id,
        "status": order.status,
        "total_amount": total_amount_str,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
    }


def get_utcnow():
    return datetime.utcnow()