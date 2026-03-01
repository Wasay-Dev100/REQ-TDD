from flask import Blueprint, request, jsonify, render_template
from app import db
from models.user import User
from models.product import Product
from models.place_order_order import PlaceOrderOrder
from models.place_order_order_item import PlaceOrderOrderItem
from datetime import datetime

place_order_bp = Blueprint('place_order', __name__)

@place_order_bp.route('/place-order', methods=['GET'])
def place_order_page():
    return render_template('place_order_page.html')

@place_order_bp.route('/api/place-order/dishes', methods=['GET'])
def list_dishes():
    products = Product.query.all()
    dishes = [product.to_card_dict() for product in products]
    return jsonify({"dishes": dishes}), 200

@place_order_bp.route('/api/place-order/validate-quantity', methods=['POST'])
def validate_quantity():
    data = request.get_json()
    quantity = data.get('quantity', '')
    if not quantity.isdigit() or not (1 <= int(quantity) <= 999):
        return jsonify({"error": "Invalid quantity", "message": "Quantity must be a number between 1 and 999"}), 400
    return jsonify({"is_valid": True, "normalized_quantity": int(quantity)}), 200

@place_order_bp.route('/api/place-order/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    customer_id = get_current_user().id
    items = parse_and_validate_order_payload(data['items'])
    assert_products_available_for_order(items)
    order = create_order_models(customer_id, items, utcnow())
    db.session.add(order)
    db.session.commit()
    enqueue_order_for_chef(order)
    return jsonify(order.to_dict()), 201

@place_order_bp.route('/api/place-order/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    order = PlaceOrderOrder.query.get(order_id)
    if not order:
        return jsonify({"error": "Order not found", "message": "The order does not exist"}), 404
    return jsonify(order.to_dict()), 200

@place_order_bp.route('/api/place-order/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    order = PlaceOrderOrder.query.get(order_id)
    if not order:
        return jsonify({"error": "Order not found", "message": "The order does not exist"}), 404
    if not order.is_cancelable(utcnow()):
        return jsonify({"error": "Order cannot be canceled", "message": "The order is not cancelable"}), 403
    order.status = 'CANCELED'
    order.canceled_at = utcnow()
    order.cancel_reason = request.json.get('reason', '')
    db.session.commit()
    return jsonify({"order_id": order.id, "status": order.status, "canceled_at": order.canceled_at.isoformat()}), 200

def get_current_user():
    # Placeholder for actual user retrieval logic
    return User.query.first()

def parse_and_validate_order_payload(payload):
    # Placeholder for actual payload validation logic
    return payload

def assert_products_available_for_order(items):
    # Placeholder for product availability check logic
    pass

def create_order_models(customer_id, items, now_utc):
    order = PlaceOrderOrder(customer_id=customer_id, created_at=now_utc)
    for item_data in items:
        product = Product.query.get(item_data['product_id'])
        if not product or not product.is_available:
            raise ValueError("Product not available")
        order_item = PlaceOrderOrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=item_data['quantity'],
            unit_price_cents=product.price_cents
        )
        order_item.compute_line_total()
        db.session.add(order_item)
    order.recalculate_total(order.items)
    return order

def enqueue_order_for_chef(order):
    # Placeholder for order queue logic
    pass

def utcnow():
    return datetime.utcnow()