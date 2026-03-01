from flask import Blueprint, request, jsonify, render_template
from app import db
from models.customer_help_request import CustomerHelpRequest
from models.order import Order
from datetime import datetime

customer_help_bp = Blueprint('customer_help', __name__)

@customer_help_bp.route('/help', methods=['GET'])
def help_home():
    return render_template('customer_help_home.html')

@customer_help_bp.route('/help/request', methods=['POST'])
def create_help_request():
    data = request.json
    table_number = data.get('table_number')
    request_type = data.get('request_type')
    message = data.get('message', '')
    
    if not validate_request_type(request_type):
        return jsonify({'error': 'Invalid request type'}), 400

    help_request = CustomerHelpRequest(
        table_number=table_number,
        request_type=request_type,
        message=message,
        status='pending'
    )
    db.session.add(help_request)
    db.session.commit()
    return jsonify({'id': help_request.id}), 201

@customer_help_bp.route('/help/requests/<int:request_id>', methods=['GET'])
def get_help_request(request_id):
    help_request = get_help_request_or_404(request_id)
    return jsonify({
        'id': help_request.id,
        'table_number': help_request.table_number,
        'request_type': help_request.request_type,
        'message': help_request.message,
        'status': help_request.status,
        'created_at': help_request.created_at,
        'resolved_at': help_request.resolved_at
    })

@customer_help_bp.route('/help/requests/<int:request_id>/resolve', methods=['POST'])
def resolve_help_request(request_id):
    help_request = get_help_request_or_404(request_id)
    help_request.mark_resolved(datetime.utcnow())
    return jsonify({'status': 'resolved'}), 200

@customer_help_bp.route('/help/call-waiter/manage-order', methods=['POST'])
def call_waiter_manage_order():
    data = request.json
    order_id = data.get('order_id')
    order = get_order_or_404(order_id)
    order.set_given_by_waiter(True)
    return jsonify({'status': 'order managed by waiter'}), 200

def validate_request_type(request_type):
    valid_types = ['general', 'order']
    return request_type in valid_types

def get_order_or_404(order_id):
    order = Order.query.filter_by(id=order_id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    return order

def get_help_request_or_404(request_id):
    help_request = CustomerHelpRequest.query.filter_by(id=request_id).first()
    if not help_request:
        return jsonify({'error': 'Help request not found'}), 404
    return help_request