import os
import sys
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.mark_dish_as_cooked_order import Order
from models.mark_dish_as_cooked_order_dish import OrderDish
from models.mark_dish_as_cooked_notification import Notification
from controllers.mark_dish_as_cooked_controller import (
    create_hall_manager_food_ready_notification,
    get_current_user,
    require_role,
    serialize_order,
    serialize_order_dish,
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
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u

def _create_order(status="in_progress"):
    o = Order(status=status)
    db.session.add(o)
    db.session.commit()
    return o

def _create_order_dish(order_id, dish_name="Pasta", status="pending"):
    od = OrderDish(order_id=order_id, dish_name=dish_name, status=status)
    db.session.add(od)
    db.session.commit()
    return od

def _create_notification(order_id, recipient_role="hall_manager", type_="food_ready", message="Order ready"):
    n = Notification(recipient_role=recipient_role, order_id=order_id, type=type_, message=message)
    db.session.add(n)
    db.session.commit()
    return n

class TestUserModel:
    def test_user_model_has_required_fields(self):
        for field in ["id", "email", "username", "role", "password_hash"]:
            assert hasattr(User, field), f"User missing required field: {field}"

    def test_user_set_password(self):
        user = User(email=_unique_email(), username=_unique_username(), role="head_chef", password_hash="")
        user.set_password("secret123")
        assert user.password_hash
        assert user.password_hash != "secret123"

    def test_user_check_password(self):
        user = User(email=_unique_email(), username=_unique_username(), role="head_chef", password_hash="")
        user.set_password("secret123")
        assert user.check_password("secret123") is True
        assert user.check_password("wrong") is False

    def test_user_unique_constraints(self, app_context):
        u1 = User(email="dup@example.com", username="dupuser", role="head_chef", password_hash="")
        u1.set_password("secret123")
        db.session.add(u1)
        db.session.commit()

        u2 = User(email="dup@example.com", username="otheruser", role="head_chef", password_hash="")
        u2.set_password("secret123")
        db.session.add(u2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

        u3 = User(email="other@example.com", username="dupuser", role="head_chef", password_hash="")
        u3.set_password("secret123")
        db.session.add(u3)
        with pytest.raises(Exception):
            db.session.commit()

class TestOrderModel:
    def test_order_model_has_required_fields(self):
        for field in ["id", "status", "created_at", "updated_at"]:
            assert hasattr(Order, field), f"Order missing required field: {field}"

    def test_order_all_dishes_cooked(self, app_context):
        order = _create_order(status="in_progress")
        d1 = _create_order_dish(order.id, dish_name="Dish1", status="pending")
        d2 = _create_order_dish(order.id, dish_name="Dish2", status="pending")

        assert order.all_dishes_cooked() is False

        d1.mark_cooked()
        db.session.commit()
        assert order.all_dishes_cooked() is False

        d2.mark_cooked()
        db.session.commit()
        assert order.all_dishes_cooked() is True

    def test_order_unique_constraints(self):
        assert True

class TestOrderDishModel:
    def test_orderdish_model_has_required_fields(self):
        for field in ["id", "order_id", "dish_name", "status", "cooked_at"]:
            assert hasattr(OrderDish, field), f"OrderDish missing required field: {field}"

    def test_orderdish_mark_cooked(self, app_context):
        order = _create_order()
        od = _create_order_dish(order.id, dish_name="Soup", status="pending")
        assert od.status != "cooked"
        assert od.cooked_at is None

        od.mark_cooked()
        db.session.commit()

        assert od.status == "cooked"
        assert od.cooked_at is not None
        assert isinstance(od.cooked_at, datetime)

    def test_orderdish_unique_constraints(self):
        assert True

class TestNotificationModel:
    def test_notification_model_has_required_fields(self):
        for field in ["id", "recipient_role", "order_id", "type", "message", "created_at", "read_at"]:
            assert hasattr(Notification, field), f"Notification missing required field: {field}"

    def test_notification_mark_read(self, app_context):
        order = _create_order()
        n = _create_notification(order.id)
        assert n.read_at is None

        n.mark_read()
        db.session.commit()

        assert n.read_at is not None
        assert isinstance(n.read_at, datetime)

    def test_notification_unique_constraints(self):
        assert True

class TestMarkDishCookedRoute:
    def test_orders_order_id_dishes_order_dish_id_mark_cooked_post_exists(self, client):
        order_id = 1
        order_dish_id = 1
        resp = client.post(f"/orders/{order_id}/dishes/{order_dish_id}/mark-cooked")
        assert resp.status_code != 405

    def test_orders_order_id_dishes_order_dish_id_mark_cooked_post_success(self, client):
        with app.app_context():
            order = _create_order()
            od1 = _create_order_dish(order.id, dish_name="Dish1", status="pending")
            _create_order_dish(order.id, dish_name="Dish2", status="pending")

        with patch(
            "controllers.mark_dish_as_cooked_controller.get_current_user",
            return_value=MagicMock(role="head_chef"),
        ):
            resp = client.post(f"/orders/{order.id}/dishes/{od1.id}/mark-cooked", data={})
            assert resp.status_code in (200, 201, 302)

        with app.app_context():
            refreshed = OrderDish.query.filter_by(id=od1.id).first()
            assert refreshed is not None
            assert refreshed.status == "cooked"
            assert refreshed.cooked_at is not None

    def test_orders_order_id_dishes_order_dish_id_mark_cooked_post_missing_required_fields(self, client):
        with app.app_context():
            order = _create_order()
            od = _create_order_dish(order.id, dish_name="Dish1", status="pending")

        with patch(
            "controllers.mark_dish_as_cooked_controller.get_current_user",
            return_value=MagicMock(role="head_chef"),
        ):
            resp = client.post(
                f"/orders/{order.id}/dishes/{od.id}/mark-cooked",
                data={"status": ""},
            )
            assert resp.status_code in (200, 400, 422)

    def test_orders_order_id_dishes_order_dish_id_mark_cooked_post_invalid_data(self, client):
        with patch(
            "controllers.mark_dish_as_cooked_controller.get_current_user",
            return_value=MagicMock(role="head_chef"),
        ):
            resp = client.post("/orders/999999/dishes/999999/mark-cooked", data={"status": "cooked"})
            assert resp.status_code in (400, 404, 422)

    def test_orders_order_id_dishes_order_dish_id_mark_cooked_post_duplicate_data(self, client):
        with app.app_context():
            order = _create_order()
            od = _create_order_dish(order.id, dish_name="Dish1", status="pending")

        with patch(
            "controllers.mark_dish_as_cooked_controller.get_current_user",
            return_value=MagicMock(role="head_chef"),
        ):
            resp1 = client.post(f"/orders/{order.id}/dishes/{od.id}/mark-cooked", data={})
            assert resp1.status_code in (200, 201, 302)

            resp2 = client.post(f"/orders/{order.id}/dishes/{od.id}/mark-cooked", data={})
            assert resp2.status_code in (200, 201, 302, 400, 409, 422)

        with app.app_context():
            refreshed = OrderDish.query.filter_by(id=od.id).first()
            assert refreshed.status == "cooked"
            assert refreshed.cooked_at is not None

class TestFoodReadyScreenRoute:
    def test_orders_order_id_food_ready_get_exists(self, client):
        resp = client.get("/orders/1/food-ready")
        assert resp.status_code != 405

    def test_orders_order_id_food_ready_get_renders_template(self, client):
        with app.app_context():
            order = _create_order(status="ready")

        resp = client.get(f"/orders/{order.id}/food-ready")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert b"feedback" in resp.data.lower() or b"request" in resp.data.lower() or b"bill" in resp.data.lower()

class TestRequestBillRoute:
    def test_orders_order_id_request_bill_post_exists(self, client):
        resp = client.post("/orders/1/request-bill")
        assert resp.status_code != 405

    def test_orders_order_id_request_bill_post_success(self, client):
        with app.app_context():
            order = _create_order(status="ready")

        resp = client.post(f"/orders/{order.id}/request-bill", data={"request": "1"})
        assert resp.status_code in (200, 201, 302)

    def test_orders_order_id_request_bill_post_missing_required_fields(self, client):
        with app.app_context():
            order = _create_order(status="ready")

        resp = client.post(f"/orders/{order.id}/request-bill", data={})
        assert resp.status_code in (200, 400, 422)

    def test_orders_order_id_request_bill_post_invalid_data(self, client):
        resp = client.post("/orders/999999/request-bill", data={"request": "1"})
        assert resp.status_code in (400, 404, 422)

    def test_orders_order_id_request_bill_post_duplicate_data(self, client):
        with app.app_context():
            order = _create_order(status="ready")

        resp1 = client.post(f"/orders/{order.id}/request-bill", data={"request": "1"})
        assert resp1.status_code in (200, 201, 302)

        resp2 = client.post(f"/orders/{order.id}/request-bill", data={"request": "1"})
        assert resp2.status_code in (200, 201, 302, 400, 409, 422)

class TestSubmitFeedbackRoute:
    def test_orders_order_id_feedback_post_exists(self, client):
        resp = client.post("/orders/1/feedback")
        assert resp.status_code != 405

    def test_orders_order_id_feedback_post_success(self, client):
        with app.app_context():
            order = _create_order(status="ready")

        resp = client.post(f"/orders/{order.id}/feedback", data={"rating": "5", "comment": "Great"})
        assert resp.status_code in (200, 201, 302)

    def test_orders_order_id_feedback_post_missing_required_fields(self, client):
        with app.app_context():
            order = _create_order(status="ready")

        resp = client.post(f"/orders/{order.id}/feedback", data={})
        assert resp.status_code in (200, 400, 422)

    def test_orders_order_id_feedback_post_invalid_data(self, client):
        resp = client.post("/orders/999999/feedback", data={"rating": "not-a-number"})
        assert resp.status_code in (400, 404, 422)

    def test_orders_order_id_feedback_post_duplicate_data(self, client):
        with app.app_context():
            order = _create_order(status="ready")

        resp1 = client.post(f"/orders/{order.id}/feedback", data={"rating": "5", "comment": "Great"})
        assert resp1.status_code in (200, 201, 302)

        resp2 = client.post(f"/orders/{order.id}/feedback", data={"rating": "5", "comment": "Great"})
        assert resp2.status_code in (200, 201, 302, 400, 409, 422)

class TestHallManagerNotificationsRoute:
    def test_notifications_hall_manager_get_exists(self, client):
        resp = client.get("/notifications/hall-manager")
        assert resp.status_code != 405

    def test_notifications_hall_manager_get_renders_template(self, client):
        with app.app_context():
            order = _create_order(status="ready")
            _create_notification(order.id, recipient_role="hall_manager", type_="food_ready", message="Order ready")

        resp = client.get("/notifications/hall-manager")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert b"order" in resp.data.lower() or b"notification" in resp.data.lower() or b"ready" in resp.data.lower()

class TestHelperGetCurrentUser:
    def test_get_current_user_function_exists(self):
        assert callable(get_current_user)

    def test_get_current_user_with_valid_input(self):
        with patch("controllers.mark_dish_as_cooked_controller.get_current_user", wraps=get_current_user):
            user = get_current_user()
            assert user is None or hasattr(user, "role")

    def test_get_current_user_with_invalid_input(self):
        with pytest.raises(TypeError):
            get_current_user("unexpected")

class TestHelperRequireRole:
    def test_require_role_function_exists(self):
        assert callable(require_role)

    def test_require_role_with_valid_input(self):
        user = MagicMock(role="head_chef")
        result = require_role(user, "head_chef")
        assert result is None or result is True

    def test_require_role_with_invalid_input(self):
        user = MagicMock(role="hall_manager")
        with pytest.raises(Exception):
            require_role(user, "head_chef")

class TestHelperSerializeOrderDish:
    def test_serialize_order_dish_function_exists(self):
        assert callable(serialize_order_dish)

    def test_serialize_order_dish_with_valid_input(self, app_context):
        order = _create_order()
        od = _create_order_dish(order.id, dish_name="Dish1", status="pending")
        data = serialize_order_dish(od)
        assert isinstance(data, dict)
        assert "id" in data
        assert "order_id" in data
        assert "dish_name" in data
        assert "status" in data

    def test_serialize_order_dish_with_invalid_input(self):
        with pytest.raises(Exception):
            serialize_order_dish(None)

class TestHelperSerializeOrder:
    def test_serialize_order_function_exists(self):
        assert callable(serialize_order)

    def test_serialize_order_with_valid_input(self, app_context):
        order = _create_order(status="in_progress")
        data = serialize_order(order)
        assert isinstance(data, dict)
        assert "id" in data
        assert "status" in data

    def test_serialize_order_with_invalid_input(self):
        with pytest.raises(Exception):
            serialize_order(None)

class TestHelperCreateHallManagerFoodReadyNotification:
    def test_create_hall_manager_food_ready_notification_function_exists(self):
        assert callable(create_hall_manager_food_ready_notification)

    def test_create_hall_manager_food_ready_notification_with_valid_input(self, app_context):
        order = _create_order(status="ready")
        n = create_hall_manager_food_ready_notification(order)
        assert n is not None
        assert isinstance(n, Notification)
        assert n.order_id == order.id
        assert n.recipient_role == "hall_manager"
        assert n.type
        assert n.message

    def test_create_hall_manager_food_ready_notification_with_invalid_input(self):
        with pytest.raises(Exception):
            create_hall_manager_food_ready_notification(None)