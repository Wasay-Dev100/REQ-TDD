from flask import Blueprint, jsonify, request, abort
from app import db
from models.mark_dish_as_cooked_order import Order
from models.mark_dish_as_cooked_order_dish import OrderDish
from models.mark_dish_as_cooked_notification import Notification
from models.user import User

mark_dish_as_cooked_bp = Blueprint('mark_dish_as_cooked', __name__)

def get_current_user():
    # Mock function to get the current user
    return User.query.first()

def require_role(user, role):
    if user.role != role:
        abort(403)

def serialize_order_dish(order_dish):
    return {
        'id': order_dish.id,
        'order_id': order_dish.order_id,
        'dish_name': order_dish.dish_name,
        'status': order_dish.status,
        'cooked_at': order_dish.cooked_at
    }

def serialize_order(order):
    return {
        'id': order.id,
        'status': order.status,
        'created_at': order.created_at,
        'updated_at': order.updated_at
    }

def create_hall_manager_food_ready_notification(order):
    notification = Notification(
        recipient_role='hall_manager',
        order_id=order.id,
        type='food_ready',
        message=f'Order {order.id} is ready.'
    )
    db.session.add(notification)
    db.session.commit()
    return notification

@mark_dish_as_cooked_bp.route('/orders/<int:order_id>/dishes/<int:order_dish_id>/mark-cooked', methods=['POST'])
def mark_dish_cooked(order_id, order_dish_id):
    user = get_current_user()
    require_role(user, 'head_chef')

    order_dish = OrderDish.query.filter_by(id=order_dish_id, order_id=order_id).first_or_404()
    order_dish.mark_cooked()
    db.session.commit()

    order = Order.query.filter_by(id=order_id).first_or_404()
    if order.all_dishes_cooked():
        create_hall_manager_food_ready_notification(order)
        return jsonify({'message': 'All dishes cooked, notification sent to hall manager.'}), 200

    return jsonify({'message': 'Dish marked as cooked.'}), 200

@mark_dish_as_cooked_bp.route('/orders/<int:order_id>/food-ready', methods=['GET'])
def food_ready_screen(order_id):
    order = Order.query.filter_by(id=order_id).first_or_404()
    return render_food_ready_screen(order)

@mark_dish_as_cooked_bp.route('/orders/<int:order_id>/request-bill', methods=['POST'])
def request_bill(order_id):
    # Logic to request bill
    return jsonify({'message': 'Bill requested.'}), 200

@mark_dish_as_cooked_bp.route('/orders/<int:order_id>/feedback', methods=['POST'])
def submit_feedback(order_id):
    # Logic to submit feedback
    return jsonify({'message': 'Feedback submitted.'}), 200

@mark_dish_as_cooked_bp.route('/notifications/hall-manager', methods=['GET'])
def list_hall_manager_notifications():
    notifications = Notification.query.filter_by(recipient_role='hall_manager').all()
    return jsonify([{
        'id': n.id,
        'order_id': n.order_id,
        'type': n.type,
        'message': n.message,
        'created_at': n.created_at,
        'read_at': n.read_at
    } for n in notifications]), 200