from flask import Blueprint, request, jsonify
from app import db
from models.category import Category
from models.product import Product
from models.customer_order_management_order import Order
from models.customer_order_management_order_item import OrderItem
from models.customer_order_management_bill_request import BillRequest
from models.customer_order_management_feedback import Feedback
from views.customer_order_management_views import serialize_category, serialize_product, serialize_order, serialize_order_item, serialize_bill, serialize_feedback

customer_order_management_bp = Blueprint('customer_order_management', __name__)

@customer_order_management_bp.route('/menu', methods=['GET'])
def get_menu():
    category_id = request.args.get('category_id', type=int)
    q = request.args.get('q', type=str)
    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=10, type=int)

    query = Product.query.filter_by(is_available=True)
    if category_id:
        query = query.filter_by(category_id=category_id)
    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))

    products = query.paginate(page, per_page, False).items
    return jsonify([serialize_product(product) for product in products])

@customer_order_management_bp.route('/orders', methods=['POST'])
def create_order():
    data = request.json
    customer_id = data['customer_id']
    table_identifier = data['table_identifier']
    items = data['items']
    notes = data.get('notes')

    order = Order(customer_id=customer_id, table_identifier=table_identifier, status='pending', notes=notes, subtotal_cents=0, tax_cents=0, service_charge_cents=0, total_cents=0)
    db.session.add(order)
    db.session.commit()

    for item in items:
        product = Product.query.get(item['product_id'])
        order_item = OrderItem(order_id=order.id, product_id=product.id, product_name_snapshot=product.name, unit_price_cents_snapshot=product.price_cents, quantity=item['quantity'], special_instructions=item.get('special_instructions'))
        order_item.recalculate_line_total()
        db.session.add(order_item)
        order.subtotal_cents += order_item.line_total_cents

    order.recalculate_totals(tax_rate=0.1, service_charge_rate=0.05)
    db.session.commit()

    return jsonify(serialize_order(order)), 201

@customer_order_management_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    order = Order.query.get_or_404(order_id)
    return jsonify(serialize_order(order))

@customer_order_management_bp.route('/orders/<int:order_id>', methods=['PATCH'])
def update_order(order_id):
    order = Order.query.get_or_404(order_id)
    if not order.is_editable():
        return jsonify({'error': 'Order cannot be edited'}), 400

    data = request.json
    items = data.get('items')
    notes = data.get('notes')

    if items is not None:
        order.subtotal_cents = 0
        OrderItem.query.filter_by(order_id=order.id).delete()
        for item in items:
            product = Product.query.get(item['product_id'])
            order_item = OrderItem(order_id=order.id, product_id=product.id, product_name_snapshot=product.name, unit_price_cents_snapshot=product.price_cents, quantity=item['quantity'], special_instructions=item.get('special_instructions'))
            order_item.recalculate_line_total()
            db.session.add(order_item)
            order.subtotal_cents += order_item.line_total_cents

    if notes is not None:
        order.notes = notes

    order.recalculate_totals(tax_rate=0.1, service_charge_rate=0.05)
    db.session.commit()

    return jsonify(serialize_order(order))

@customer_order_management_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    order = Order.query.get_or_404(order_id)
    if not order.is_editable():
        return jsonify({'error': 'Order cannot be cancelled'}), 400

    order.status = 'cancelled'
    order.cancelled_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'status': 'Order cancelled'})

@customer_order_management_bp.route('/orders/<int:order_id>/bill', methods=['POST'])
def request_bill(order_id):
    data = request.json
    customer_id = data['customer_id']
    notes = data.get('notes')

    bill_request = BillRequest(order_id=order_id, requested_by_customer_id=customer_id, status='requested', notes=notes)
    db.session.add(bill_request)
    db.session.commit()

    return jsonify({'status': 'Bill requested'})

@customer_order_management_bp.route('/orders/<int:order_id>/bill', methods=['GET'])
def get_bill(order_id):
    order = Order.query.get_or_404(order_id)
    return jsonify(serialize_bill(order))

@customer_order_management_bp.route('/orders/<int:order_id>/feedback', methods=['POST'])
def create_feedback(order_id):
    data = request.json
    customer_id = data['customer_id']
    rating = data['rating']
    comment = data.get('comment')

    feedback = Feedback(order_id=order_id, customer_id=customer_id, rating=rating, comment=comment)
    db.session.add(feedback)
    db.session.commit()

    return jsonify({'status': 'Feedback submitted'})

def validate_order_editable(order: Order):
    if not order.is_editable():
        return None, {'error': 'Order cannot be edited'}
    return None

def apply_order_items_patch(order: Order, items_payload: list[dict]):
    order.subtotal_cents = 0
    OrderItem.query.filter_by(order_id=order.id).delete()
    for item in items_payload:
        product = Product.query.get(item['product_id'])
        order_item = OrderItem(order_id=order.id, product_id=product.id, product_name_snapshot=product.name, unit_price_cents_snapshot=product.price_cents, quantity=item['quantity'], special_instructions=item.get('special_instructions'))
        order_item.recalculate_line_total()
        db.session.add(order_item)
        order.subtotal_cents += order_item.line_total_cents

def compute_totals(order: Order) -> dict:
    order.recalculate_totals(tax_rate=0.1, service_charge_rate=0.05)
    return {
        'subtotal_cents': order.subtotal_cents,
        'tax_cents': order.tax_cents,
        'service_charge_cents': order.service_charge_cents,
        'total_cents': order.total_cents
    }

def firebase_upsert_order(order: Order):
    # Placeholder for Firebase integration
    pass

def firebase_upsert_bill_request(bill_request: BillRequest):
    # Placeholder for Firebase integration
    pass

def firebase_upsert_feedback(feedback: Feedback):
    # Placeholder for Firebase integration
    pass