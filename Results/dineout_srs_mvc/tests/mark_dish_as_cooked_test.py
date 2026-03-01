import os
import sys
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.mark_dish_as_cooked_order import Order
from models.mark_dish_as_cooked_order_dish import OrderDish
from models.mark_dish_as_cooked_notification import Notification
from controllers.mark_dish_as_cooked_controller import (
    get_current_user,
    require_role,
    serialize_order_dish,
    serialize_order,
    create_hall_manager_food_ready_notification,
)
from views.mark_dish_as_cooked_views import render_food_ready_screen

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()

@pytest.fixture
def app_context():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()

def _unique_email():
    return f"u_{uuid.uuid4().hex[:10]}@example.com"

def _unique_username():
    return f"user_{uuid.uuid4().hex[:10]}"

def _create_user(role="head_chef", password="Passw0rd!"):
    u = User(email=_unique_email(), username=_unique_username(), role=role, password_hash="")
    if hasattr(u, "set_password"):
        u.set_password(password)
    return u

def _create_order(status="in_progress"):
    o = Order(status=status)
    return o

def _create_order_dish(order_id, dish_name="Pasta", status="pending"):
    od = OrderDish(order_id=order_id, dish_name=dish_name, status=status)
    return od

def _route_exists(rule, method):
    for r in app.url_map.iter_rules():
        if r.rule == rule and method in r.methods:
            return True
    return False

class TestUserModel:
    def test_user_model_has_required_fields(self, app_context):
        for field in ["id", "email", "username", "role", "password_hash"]:
            assert hasattr(User, field), f"Missing required field on User: {field}"

    def test_user_set_password(self, app_context):
        user = _create_user()
        user.set_password("secret123")
        assert user.password_hash is not None
        assert user.password_hash != ""
        assert user.password_hash != "secret123"

    def test_user_check_password(self, app_context):
        user = _create_user()
        user.set_password("secret123")
        assert user.check_password("secret123") is True
        assert user.check_password("wrong") is False

    def test_user_unique_constraints(self, app_context):
        email = _unique_email()
        username = _unique_username()

        u1 = User(email=email, username=username, role="head_chef", password_hash="")
        u1.set_password("pw1")
        db.session.add(u1)
        db.session.commit()

        u2 = User(email=email, username=_unique_username(), role="head_chef", password_hash="")
        u2.set_password("pw2")
        db.session.add(u2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

        u3 = User(email=_unique_email(), username=username, role="head_chef", password_hash="")
        u3.set_password("pw3")
        db.session.add(u3)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

class TestOrderModel:
    def test_order_model_has_required_fields(self, app_context):
        for field in ["id", "status", "created_at", "updated_at"]:
            assert hasattr(Order, field), f"Missing required field on Order: {field}"

    def test_order_all_dishes_cooked(self, app_context):
        order = _create_order(status="in_progress")
        db.session.add(order)
        db.session.commit()

        d1 = _create_order_dish(order.id, dish_name="Dish1", status="pending")
        d2 = _create_order_dish(order.id, dish_name="Dish2", status="pending")
        db.session.add_all([d1, d2])
        db.session.commit()

        assert order.all_dishes_cooked() is False

        d1.status = "cooked"
        if hasattr(d1, "cooked_at"):
            d1.cooked_at = datetime.utcnow()
        db.session.commit()
        assert order.all_dishes_cooked() is False

        d2.status = "cooked"
        if hasattr(d2, "cooked_at"):
            d2.cooked_at = datetime.utcnow()
        db.session.commit()
        assert order.all_dishes_cooked() is True

    def test_order_unique_constraints(self, app_context):
        order1 = _create_order(status="in_progress")
        order2 = _create_order(status="in_progress")
        db.session.add_all([order1, order2])
        db.session.commit()
        assert order1.id != order2.id

class TestOrderDishModel:
    def test_orderdish_model_has_required_fields(self, app_context):
        for field in ["id", "order_id", "dish_name", "status", "cooked_at"]:
            assert hasattr(OrderDish, field), f"Missing required field on OrderDish: {field}"

    def test_orderdish_mark_cooked(self, app_context):
        order = _create_order()
        db.session.add(order)
        db.session.commit()

        od = _create_order_dish(order.id, dish_name="Soup", status="pending")
        db.session.add(od)
        db.session.commit()

        assert od.status != "cooked" or od.cooked_at is None

        od.mark_cooked()
        db.session.commit()

        assert od.status == "cooked"
        assert od.cooked_at is not None

    def test_orderdish_unique_constraints(self, app_context):
        order = _create_order()
        db.session.add(order)
        db.session.commit()

        d1 = _create_order_dish(order.id, dish_name="DishA", status="pending")
        d2 = _create_order_dish(order.id, dish_name="DishA", status="pending")
        db.session.add_all([d1, d2])
        db.session.commit()
        assert d1.id != d2.id

class TestNotificationModel:
    def test_notification_model_has_required_fields(self, app_context):
        for field in ["id", "recipient_role", "order_id", "type", "message", "created_at", "read_at"]:
            assert hasattr(Notification, field), f"Missing required field on Notification: {field}"

    def test_notification_mark_read(self, app_context):
        order = _create_order()
        db.session.add(order)
        db.session.commit()

        n = Notification(
            recipient_role="hall_manager",
            order_id=order.id,
            type="food_ready",
            message="Order ready",
        )
        db.session.add(n)
        db.session.commit()

        assert n.read_at is None
        n.mark_read()
        db.session.commit()
        assert n.read_at is not None

    def test_notification_unique_constraints(self, app_context):
        order = _create_order()
        db.session.add(order)
        db.session.commit()

        n1 = Notification(
            recipient_role="hall_manager",
            order_id=order.id,
            type="food_ready",
            message="Order ready 1",
        )
        n2 = Notification(
            recipient_role="hall_manager",
            order_id=order.id,
            type="food_ready",
            message="Order ready 2",
        )
        db.session.add_all([n1, n2])
        db.session.commit()
        assert n1.id != n2.id

class TestRoutesMarkCooked:
    def test_orders_order_id_dishes_order_dish_id_mark_cooked_post_exists(self, client):
        assert _route_exists(
            "/orders/<int:order_id>/dishes/<int:order_dish_id>/mark-cooked", "POST"
        ), "Missing POST route: /orders/<int:order_id>/dishes/<int:order_dish_id>/mark-cooked"

    def test_orders_order_id_dishes_order_dish_id_mark_cooked_post_success(self, client):
        with app.app_context():
            chef = _create_user(role="head_chef")
            db.session.add(chef)
            order = _create_order(status="in_progress")
            db.session.add(order)
            db.session.commit()

            dish1 = _create_order_dish(order.id, dish_name="Dish1", status="pending")
            dish2 = _create_order_dish(order.id, dish_name="Dish2", status="pending")
            db.session.add_all([dish1, dish2])
            db.session.commit()

            with patch(
                "controllers.mark_dish_as_cooked_controller.get_current_user", return_value=chef
            ):
                resp = client.post(
                    f"/orders/{order.id}/dishes/{dish1.id}/mark-cooked",
                    data={},
                    follow_redirects=False,
                )

            assert resp.status_code in (200, 201, 302)

            updated = OrderDish.query.filter_by(id=dish1.id).first()
            assert updated is not None
            assert updated.status == "cooked"
            assert updated.cooked_at is not None

            notifs = Notification.query.filter_by(order_id=order.id).all()
            assert len(notifs) == 0

    def test_orders_order_id_dishes_order_dish_id_mark_cooked_post_missing_required_fields(self, client):
        with app.app_context():
            chef = _create_user(role="head_chef")
            db.session.add(chef)
            order = _create_order(status="in_progress")
            db.session.add(order)
            db.session.commit()

            dish = _create_order_dish(order.id, dish_name="Dish1", status="pending")
            db.session.add(dish)
            db.session.commit()

            with patch(
                "controllers.mark_dish_as_cooked_controller.get_current_user", return_value=chef
            ):
                resp = client.post(
                    f"/orders/{order.id}/dishes/{dish.id}/mark-cooked",
                    data={"status": ""},
                    follow_redirects=False,
                )

            assert resp.status_code in (200, 400, 422)

    def test_orders_order_id_dishes_order_dish_id_mark_cooked_post_invalid_data(self, client):
        with app.app_context():
            chef = _create_user(role="head_chef")
            db.session.add(chef)
            order = _create_order(status="in_progress")
            db.session.add(order)
            db.session.commit()

            dish = _create_order_dish(order.id, dish_name="Dish1", status="pending")
            db.session.add(dish)
            db.session.commit()

            with patch(
                "controllers.mark_dish_as_cooked_controller.get_current_user", return_value=chef
            ):
                resp = client.post(
                    f"/orders/{order.id}/dishes/{dish.id}/mark-cooked",
                    data={"cooked_at": "not-a-date"},
                    follow_redirects=False,
                )

            assert resp.status_code in (200, 400, 422)

    def test_orders_order_id_dishes_order_dish_id_mark_cooked_post_duplicate_data(self, client):
        with app.app_context():
            chef = _create_user(role="head_chef")
            db.session.add(chef)
            order = _create_order(status="in_progress")
            db.session.add(order)
            db.session.commit()

            dish = _create_order_dish(order.id, dish_name="Dish1", status="pending")
            db.session.add(dish)
            db.session.commit()

            with patch(
                "controllers.mark_dish_as_cooked_controller.get_current_user", return_value=chef
            ):
                resp1 = client.post(
                    f"/orders/{order.id}/dishes/{dish.id}/mark-cooked",
                    data={},
                    follow_redirects=False,
                )
                resp2 = client.post(
                    f"/orders/{order.id}/dishes/{dish.id}/mark-cooked",
                    data={},
                    follow_redirects=False,
                )

            assert resp1.status_code in (200, 201, 302)
            assert resp2.status_code in (200, 201, 302, 409)

            updated = OrderDish.query.filter_by(id=dish.id).first()
            assert updated.status == "cooked"
            assert updated.cooked_at is not None

class TestRoutesFoodReady:
    def test_orders_order_id_food_ready_get_exists(self, client):
        assert _route_exists("/orders/<int:order_id>/food-ready", "GET"), "Missing GET route: /orders/<int:order_id>/food-ready"

    def test_orders_order_id_food_ready_get_renders_template(self, client):
        with app.app_context():
            order = _create_order(status="food_ready")
            db.session.add(order)
            db.session.commit()

            resp = client.get(f"/orders/{order.id}/food-ready")
            assert resp.status_code == 200
            assert len(resp.data) > 0

class TestRoutesRequestBill:
    def test_orders_order_id_request_bill_post_exists(self, client):
        assert _route_exists("/orders/<int:order_id>/request-bill", "POST"), "Missing POST route: /orders/<int:order_id>/request-bill"

    def test_orders_order_id_request_bill_post_success(self, client):
        with app.app_context():
            order = _create_order(status="food_ready")
            db.session.add(order)
            db.session.commit()

            resp = client.post(f"/orders/{order.id}/request-bill", data={"request": "1"}, follow_redirects=False)
            assert resp.status_code in (200, 201, 302)

    def test_orders_order_id_request_bill_post_missing_required_fields(self, client):
        with app.app_context():
            order = _create_order(status="food_ready")
            db.session.add(order)
            db.session.commit()

            resp = client.post(f"/orders/{order.id}/request-bill", data={}, follow_redirects=False)
            assert resp.status_code in (200, 400, 422)

    def test_orders_order_id_request_bill_post_invalid_data(self, client):
        with app.app_context():
            order = _create_order(status="food_ready")
            db.session.add(order)
            db.session.commit()

            resp = client.post(f"/orders/{order.id}/request-bill", data={"request": {"bad": "type"}}, follow_redirects=False)
            assert resp.status_code in (200, 400, 415, 422)

    def test_orders_order_id_request_bill_post_duplicate_data(self, client):
        with app.app_context():
            order = _create_order(status="food_ready")
            db.session.add(order)
            db.session.commit()

            resp1 = client.post(f"/orders/{order.id}/request-bill", data={"request": "1"}, follow_redirects=False)
            resp2 = client.post(f"/orders/{order.id}/request-bill", data={"request": "1"}, follow_redirects=False)
            assert resp1.status_code in (200, 201, 302)
            assert resp2.status_code in (200, 201, 302, 409)

class TestRoutesFeedback:
    def test_orders_order_id_feedback_post_exists(self, client):
        assert _route_exists("/orders/<int:order_id>/feedback", "POST"), "Missing POST route: /orders/<int:order_id>/feedback"

    def test_orders_order_id_feedback_post_success(self, client):
        with app.app_context():
            order = _create_order(status="food_ready")
            db.session.add(order)
            db.session.commit()

            resp = client.post(
                f"/orders/{order.id}/feedback",
                data={"rating": "5", "comment": "Great"},
                follow_redirects=False,
            )
            assert resp.status_code in (200, 201, 302)

    def test_orders_order_id_feedback_post_missing_required_fields(self, client):
        with app.app_context():
            order = _create_order(status="food_ready")
            db.session.add(order)
            db.session.commit()

            resp = client.post(f"/orders/{order.id}/feedback", data={}, follow_redirects=False)
            assert resp.status_code in (200, 400, 422)

    def test_orders_order_id_feedback_post_invalid_data(self, client):
        with app.app_context():
            order = _create_order(status="food_ready")
            db.session.add(order)
            db.session.commit()

            resp = client.post(
                f"/orders/{order.id}/feedback",
                data={"rating": "not-a-number", "comment": "Ok"},
                follow_redirects=False,
            )
            assert resp.status_code in (200, 400, 422)

    def test_orders_order_id_feedback_post_duplicate_data(self, client):
        with app.app_context():
            order = _create_order(status="food_ready")
            db.session.add(order)
            db.session.commit()

            resp1 = client.post(
                f"/orders/{order.id}/feedback",
                data={"rating": "4", "comment": "Nice"},
                follow_redirects=False,
            )
            resp2 = client.post(
                f"/orders/{order.id}/feedback",
                data={"rating": "4", "comment": "Nice"},
                follow_redirects=False,
            )
            assert resp1.status_code in (200, 201, 302)
            assert resp2.status_code in (200, 201, 302, 409)

class TestRoutesHallManagerNotifications:
    def test_notifications_hall_manager_get_exists(self, client):
        assert _route_exists("/notifications/hall-manager", "GET"), "Missing GET route: /notifications/hall-manager"

    def test_notifications_hall_manager_get_renders_template(self, client):
        with app.app_context():
            order = _create_order(status="food_ready")
            db.session.add(order)
            db.session.commit()

            n = Notification(
                recipient_role="hall_manager",
                order_id=order.id,
                type="food_ready",
                message="Order is ready",
            )
            db.session.add(n)
            db.session.commit()

            resp = client.get("/notifications/hall-manager")
            assert resp.status_code == 200
            assert len(resp.data) > 0

class TestHelpersGetCurrentUser:
    def test_get_current_user_function_exists(self):
        assert callable(get_current_user)

    def test_get_current_user_with_valid_input(self, app_context):
        user = _create_user(role="head_chef")
        db.session.add(user)
        db.session.commit()

        with patch("controllers.mark_dish_as_cooked_controller.get_current_user", return_value=user) as p:
            result = get_current_user()
            assert result is user
            assert result.id == user.id
            assert p.called

    def test_get_current_user_with_invalid_input(self, app_context):
        with patch("controllers.mark_dish_as_cooked_controller.get_current_user", return_value=None) as p:
            result = get_current_user()
            assert result is None
            assert p.called

class TestHelpersRequireRole:
    def test_require_role_function_exists(self):
        assert callable(require_role)

    def test_require_role_with_valid_input(self, app_context):
        user = _create_user(role="head_chef")
        db.session.add(user)
        db.session.commit()

        require_role(user, "head_chef")

    def test_require_role_with_invalid_input(self, app_context):
        user = _create_user(role="hall_manager")
        db.session.add(user)
        db.session.commit()

        with pytest.raises(Exception):
            require_role(user, "head_chef")

class TestHelpersSerializeOrderDish:
    def test_serialize_order_dish_function_exists(self):
        assert callable(serialize_order_dish)

    def test_serialize_order_dish_with_valid_input(self, app_context):
        order = _create_order()
        db.session.add(order)
        db.session.commit()

        od = _create_order_dish(order.id, dish_name="Burger", status="pending")
        db.session.add(od)
        db.session.commit()

        data = serialize_order_dish(od)
        assert isinstance(data, dict)
        assert "id" in data
        assert "order_id" in data
        assert "dish_name" in data
        assert "status" in data

    def test_serialize_order_dish_with_invalid_input(self, app_context):
        with pytest.raises(Exception):
            serialize_order_dish(None)

class TestHelpersSerializeOrder:
    def test_serialize_order_function_exists(self):
        assert callable(serialize_order)

    def test_serialize_order_with_valid_input(self, app_context):
        order = _create_order(status="in_progress")
        db.session.add(order)
        db.session.commit()

        data = serialize_order(order)
        assert isinstance(data, dict)
        assert "id" in data
        assert "status" in data

    def test_serialize_order_with_invalid_input(self, app_context):
        with pytest.raises(Exception):
            serialize_order(None)

class TestHelpersCreateHallManagerFoodReadyNotification:
    def test_create_hall_manager_food_ready_notification_function_exists(self):
        assert callable(create_hall_manager_food_ready_notification)

    def test_create_hall_manager_food_ready_notification_with_valid_input(self, app_context):
        order = _create_order(status="food_ready")
        db.session.add(order)
        db.session.commit()

        notif = create_hall_manager_food_ready_notification(order)
        assert notif is not None
        assert isinstance(notif, Notification)
        assert notif.recipient_role == "hall_manager"
        assert notif.order_id == order.id
        assert notif.type is not None
        assert notif.message is not None

    def test_create_hall_manager_food_ready_notification_with_invalid_input(self, app_context):
        with pytest.raises(Exception):
            create_hall_manager_food_ready_notification(None)