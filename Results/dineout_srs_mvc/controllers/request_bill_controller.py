from flask import Blueprint
from flask import request
from flask import jsonify
from app import db
from models.request_bill_order import Order
from models.request_bill_bill_request import BillRequest
from models.request_bill_payment import Payment
from views.request_bill_views import render_manager_bill_requests
from datetime import datetime

request_bill_bp = Blueprint("request_bill", __name__)


@request_bill_bp.route("/orders/<int:order_id>/request-bill", methods=["POST"])
def request_bill(order_id):
    order = Order.query.filter_by(id=order_id).first()
    if not order:
        return jsonify({"error": "Order not found"}), 404

    if order.status != "pending":
        return jsonify({"error": "Bill already requested or paid"}), 400

    order.mark_bill_requested()
    bill_request = BillRequest(order_id=order.id, requested_at=datetime.utcnow(), status="pending")
    db.session.add(bill_request)

    _ = print_bill(order)

    db.session.commit()

    notify_hall_manager_bill_requested(order, bill_request)

    return jsonify({"message": "Bill requested successfully"}), 200


@request_bill_bp.route("/manager/bill-requests", methods=["GET"])
def manager_bill_requests():
    bill_requests = BillRequest.query.filter_by(status="pending").all()
    items = []
    for br in bill_requests:
        order = Order.query.filter_by(id=br.order_id).first()
        if order:
            items.append(serialize_manager_bill_request(order, br))
    return render_manager_bill_requests(items)


@request_bill_bp.route("/manager/orders/<int:order_id>/pay", methods=["POST"])
def process_payment(order_id):
    order = Order.query.filter_by(id=order_id).first()
    if not order or not order.is_payable():
        return jsonify({"error": "Order not payable"}), 400

    payment_data = request.get_json(silent=True)
    if not isinstance(payment_data, dict):
        return jsonify({"error": "Invalid payment payload"}), 400

    method = payment_data.get("method")
    if not method or not isinstance(method, str):
        return jsonify({"error": "Invalid payment method"}), 400

    payment = Payment(
        order_id=order.id,
        amount=order.total_amount,
        method=method,
        reference=payment_data.get("reference"),
        paid_at=datetime.utcnow(),
    )
    db.session.add(payment)

    bill_request = (
        BillRequest.query.filter_by(order_id=order.id, status="pending")
        .order_by(BillRequest.id.desc())
        .first()
    )
    if bill_request:
        bill_request.mark_processed()

    order.mark_paid()
    db.session.commit()

    return jsonify({"message": "Payment processed successfully"}), 200


def notify_hall_manager_bill_requested(order, bill_request):
    if order is None or bill_request is None:
        raise Exception("order and bill_request are required")
    return True


def print_bill(order) -> str:
    if order is None:
        raise Exception("order is required")
    return f"Bill for Order No: {order.order_no} | Table No: {order.table_no} | Total: {order.total_amount}"


def serialize_manager_bill_request(order, bill_request) -> dict:
    if order is None or bill_request is None:
        raise Exception("order and bill_request are required")
    return {
        "order_no": order.order_no,
        "table_no": order.table_no,
        "total_amount": str(order.total_amount),
        "status": bill_request.status,
    }