from flask import Blueprint, request, jsonify
from app import db
from models.edit_order_order import EditOrderOrder
from models.edit_order_order_item import EditOrderOrderItem
from models.edit_order_chef_approval_request import EditOrderChefApprovalRequest
from models.user import User
from views.edit_order_views import render_edit_order_page

edit_order_bp = Blueprint('edit_order', __name__)

@edit_order_bp.route('/orders/<int:order_id>/edit', methods=['GET'])
def enter_edit_mode(order_id):
    order = EditOrderOrder.query.get(order_id)
    if order and order.is_editable():
        order_dict = serialize_order(order)
        return render_edit_order_page(order_dict)
    return jsonify({'error': 'Order not editable'}), 400

@edit_order_bp.route('/orders/<int:order_id>', methods=['PATCH'])
def edit_order(order_id):
    order = EditOrderOrder.query.get(order_id)
    if not order or not order.is_editable():
        return jsonify({'error': 'Order not editable'}), 400
    
    payload = request.json
    change_set = validate_edit_payload(payload)
    
    if requires_head_chef_approval(order, change_set):
        current_user = get_current_user()
        approval_request = create_approval_request(order, current_user, 'Order modification', change_set)
        db.session.add(approval_request)
        db.session.commit()
        return jsonify({'message': 'Approval required'}), 202
    
    apply_change_set(order, change_set)
    db.session.commit()
    return jsonify({'message': 'Order updated successfully'}), 200

@edit_order_bp.route('/orders/<int:order_id>/items', methods=['POST'])
def add_dish_to_order(order_id):
    order = EditOrderOrder.query.get(order_id)
    if not order or not order.is_editable():
        return jsonify({'error': 'Order not editable'}), 400
    
    data = request.json
    new_item = EditOrderOrderItem(
        order_id=order.id,
        dish_id=data['dish_id'],
        dish_name=data['dish_name'],
        unit_price_cents=data['unit_price_cents'],
        quantity=data['quantity'],
        notes=data.get('notes')
    )
    db.session.add(new_item)
    db.session.commit()
    return jsonify({'message': 'Dish added to order'}), 201

@edit_order_bp.route('/orders/<int:order_id>/items/<int:item_id>', methods=['PATCH'])
def update_order_item(order_id, item_id):
    item = EditOrderOrderItem.query.get(item_id)
    if not item or item.order_id != order_id:
        return jsonify({'error': 'Order item not found'}), 404
    
    data = request.json
    item.quantity = data.get('quantity', item.quantity)
    item.notes = data.get('notes', item.notes)
    db.session.commit()
    return jsonify({'message': 'Order item updated'}), 200

@edit_order_bp.route('/orders/<int:order_id>/items/<int:item_id>', methods=['DELETE'])
def remove_dish_from_order(order_id, item_id):
    item = EditOrderOrderItem.query.get(item_id)
    if not item or item.order_id != order_id:
        return jsonify({'error': 'Order item not found'}), 404
    
    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': 'Order item removed'}), 200

@edit_order_bp.route('/chef-approvals/<int:approval_id>', methods=['POST'])
def decide_chef_approval(approval_id):
    approval_request = EditOrderChefApprovalRequest.query.get(approval_id)
    if not approval_request or not approval_request.is_pending():
        return jsonify({'error': 'Approval request not found or already decided'}), 404
    
    data = request.json
    approval_request.status = data['status']
    approval_request.approved_by_user_id = get_current_user().id
    approval_request.decided_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'message': 'Approval decision recorded'}), 200

def get_current_user():
    # Mock implementation for current user retrieval
    return User.query.first()

def serialize_order(order):
    return {
        'id': order.id,
        'customer_id': order.customer_id,
        'status': order.status,
        'version': order.version,
        'created_at': order.created_at.isoformat(),
        'updated_at': order.updated_at.isoformat(),
    }

def serialize_order_item(item):
    return {
        'id': item.id,
        'order_id': item.order_id,
        'dish_id': item.dish_id,
        'dish_name': item.dish_name,
        'unit_price_cents': item.unit_price_cents,
        'quantity': item.quantity,
        'notes': item.notes,
        'created_at': item.created_at.isoformat(),
        'updated_at': item.updated_at.isoformat(),
    }

def compute_order_totals(order):
    items = EditOrderOrderItem.query.filter_by(order_id=order.id).all()
    total_cents = sum(item.line_total_cents() for item in items)
    return {'total_cents': total_cents}

def validate_edit_payload(payload):
    # Mock validation logic
    return payload

def requires_head_chef_approval(order, change_set):
    # Mock logic for determining if approval is needed
    return False

def create_approval_request(order, requested_by_user, reason, change_set):
    return EditOrderChefApprovalRequest(
        order_id=order.id,
        requested_by_user_id=requested_by_user.id,
        status='pending',
        reason=reason,
        change_set_json=str(change_set)
    )

def apply_change_set(order, change_set):
    # Mock logic for applying changes
    pass