from flask import Blueprint, request, jsonify
from app import db
from models.user import User
from models.cancel_order_order import CancelOrderOrder
from models.cancel_order_order_item import CancelOrderOrderItem
from models.cancel_order_cancellation_request import CancelOrderCancellationRequest
from models.cancel_order_dish_cancellation_decision import CancelOrderDishCancellationDecision
from datetime import datetime

cancel_order_bp = Blueprint('cancel_order', __name__)

def get_current_user():
    # Placeholder for actual user retrieval logic
    return User.query.first()

def require_role(user, role):
    if user.role != role:
        raise PermissionError("User does not have the required role.")

def serialize_order_item(item):
    return {
        "id": item.id,
        "order_id": item.order_id,
        "dish_name": item.dish_name,
        "quantity": item.quantity,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat()
    }

def serialize_cancellation_request(req):
    dish_decisions = CancelOrderDishCancellationDecision.query.filter_by(cancellation_request_id=req.id).all()
    return {
        "id": req.id,
        "order_id": req.order_id,
        "requested_by_user_id": req.requested_by_user_id,
        "status": req.status,
        "customer_reason": req.customer_reason,
        "created_at": req.created_at.isoformat(),
        "updated_at": req.updated_at.isoformat(),
        "dish_decisions": [serialize_order_item(decision) for decision in dish_decisions]
    }

def create_cancellation_request_with_pending_decisions(order, requested_by_user_id, customer_reason):
    cancellation_request = CancelOrderCancellationRequest(
        order_id=order.id,
        requested_by_user_id=requested_by_user_id,
        status='PENDING_CHEF_APPROVAL',
        customer_reason=customer_reason
    )
    db.session.add(cancellation_request)
    db.session.commit()

    order_items = CancelOrderOrderItem.query.filter_by(order_id=order.id).all()
    for item in order_items:
        decision = CancelOrderDishCancellationDecision(
            cancellation_request_id=cancellation_request.id,
            order_item_id=item.id,
            decision_status='PENDING'
        )
        db.session.add(decision)
    db.session.commit()

    return cancellation_request

def apply_approved_cancellations(req):
    decisions = CancelOrderDishCancellationDecision.query.filter_by(cancellation_request_id=req.id).all()
    dropped_item_ids = []
    kept_item_ids = []

    for decision in decisions:
        if decision.decision_status == 'APPROVED_DROP':
            dropped_item_ids.append(decision.order_item_id)
        else:
            kept_item_ids.append(decision.order_item_id)

    order = CancelOrderOrder.query.get(req.order_id)
    if len(dropped_item_ids) == len(decisions):
        order.status = 'CANCELLED'
    else:
        order.status = 'IN_PROGRESS'
    db.session.commit()

    return {
        "order_id": order.id,
        "order_status": order.status,
        "dropped_item_ids": dropped_item_ids,
        "kept_item_ids": kept_item_ids
    }

@cancel_order_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def request_cancel_order(order_id):
    user = get_current_user()
    require_role(user, 'CUSTOMER')

    order = CancelOrderOrder.query.get(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    if order.customer_id != user.id:
        return jsonify({"error": "Not allowed (not the order owner)"}), 403

    if not order.is_cancellable():
        return jsonify({"error": "Invalid state (e.g., already served)"}), 400

    existing_request = CancelOrderCancellationRequest.query.filter_by(order_id=order_id, status='PENDING_CHEF_APPROVAL').first()
    if existing_request:
        return jsonify({"error": "Cancellation already requested for this order"}), 409

    customer_reason = request.json.get('reason', None)
    cancellation_request = create_cancellation_request_with_pending_decisions(order, user.id, customer_reason)
    return jsonify({"cancellation_request": serialize_cancellation_request(cancellation_request)}), 202

@cancel_order_bp.route('/cancellation-requests/<int:request_id>', methods=['GET'])
def get_cancellation_request(request_id):
    user = get_current_user()
    cancellation_request = CancelOrderCancellationRequest.query.get(request_id)
    if not cancellation_request:
        return jsonify({"error": "Cancellation request not found"}), 404

    order = CancelOrderOrder.query.get(cancellation_request.order_id)
    if order.customer_id != user.id and user.role != 'HEAD_CHEF':
        return jsonify({"error": "Not allowed (must be order owner or head chef)"}), 403

    return jsonify(serialize_cancellation_request(cancellation_request)), 200

@cancel_order_bp.route('/cancellation-requests/<int:request_id>/chef-decisions', methods=['POST'])
def submit_chef_decisions(request_id):
    user = get_current_user()
    require_role(user, 'HEAD_CHEF')

    cancellation_request = CancelOrderCancellationRequest.query.get(request_id)
    if not cancellation_request:
        return jsonify({"error": "Cancellation request not found"}), 404

    if cancellation_request.status != 'PENDING_CHEF_APPROVAL':
        return jsonify({"error": "Invalid payload or request not pending"}), 400

    decisions_data = request.json.get('decisions', [])
    if not decisions_data:
        return jsonify({"error": "Invalid payload"}), 400

    for decision_data in decisions_data:
        decision = CancelOrderDishCancellationDecision.query.filter_by(
            cancellation_request_id=request_id,
            order_item_id=decision_data['order_item_id']
        ).first()
        if decision:
            decision.decision_status = decision_data['decision_status']
            decision.decision_note = decision_data.get('decision_note', None)
            decision.decided_by_user_id = user.id
            decision.decided_at = datetime.utcnow()
            db.session.commit()

    result = apply_approved_cancellations(cancellation_request)
    return jsonify({
        "cancellation_request": serialize_cancellation_request(cancellation_request),
        "result": result
    }), 200