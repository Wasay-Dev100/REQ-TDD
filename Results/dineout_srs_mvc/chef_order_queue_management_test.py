import sys
import os
import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.chef_order_queue_management_chef import Chef
from models.chef_order_queue_management_dish_queue_item import DishQueueItem
from controllers.chef_order_queue_management_controller import (
    get_chef_or_404,
    get_queue_item_or_404,
    serialize_queue,
)
from views.chef_order_queue_management_views import render_chef_queue_page

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

def _unique_name(prefix="chef"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_chef(name=None, specialty="Grill", is_active=True):
    chef = Chef(name=name or _unique_name("chef"), specialty=specialty, is_active=is_active)
    db.session.add(chef)
    db.session.commit()
    return chef

def _create_queue_item(
    chef_id,
    order_id=None,
    dish_name="Dish",
    status="QUEUED",
    priority=0,
    notes=None,
):
    item = DishQueueItem(
        chef_id=chef_id,
        order_id=order_id or f"order_{uuid.uuid4().hex[:10]}",
        dish_name=dish_name,
        status=status,
        priority=priority,
        notes=notes,
    )
    db.session.add(item)
    db.session.commit()
    return item

class TestChefModel:
    def test_chef_model_has_required_fields(self, app_context):
        chef = Chef(name=_unique_name("chef"), specialty="Sushi")
        for field in ["id", "name", "specialty", "is_active", "created_at"]:
            assert hasattr(chef, field), f"Missing field on Chef: {field}"

    def test_chef_to_dict(self, app_context):
        chef = _create_chef(specialty="Pastry", is_active=True)
        assert hasattr(chef, "to_dict") and callable(chef.to_dict)
        data = chef.to_dict()
        assert isinstance(data, dict)
        assert data.get("id") == chef.id
        assert data.get("name") == chef.name
        assert data.get("specialty") == chef.specialty
        assert data.get("is_active") == chef.is_active
        assert "created_at" in data

    def test_chef_unique_constraints(self, app_context):
        name = _unique_name("chef_unique")
        chef1 = Chef(name=name, specialty="Grill")
        db.session.add(chef1)
        db.session.commit()

        chef2 = Chef(name=name, specialty="Sushi")
        db.session.add(chef2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

class TestDishQueueItemModel:
    def test_dishqueueitem_model_has_required_fields(self, app_context):
        item = DishQueueItem(
            chef_id=1,
            order_id=f"order_{uuid.uuid4().hex[:8]}",
            dish_name="Burger",
        )
        for field in [
            "id",
            "chef_id",
            "order_id",
            "dish_name",
            "status",
            "priority",
            "queued_at",
            "started_at",
            "ready_at",
            "notes",
        ]:
            assert hasattr(item, field), f"Missing field on DishQueueItem: {field}"

    def test_dishqueueitem_to_dict(self, app_context):
        chef = _create_chef()
        item = _create_queue_item(
            chef_id=chef.id,
            dish_name="Risotto",
            status="QUEUED",
            priority=2,
            notes="No cheese",
        )
        assert hasattr(item, "to_dict") and callable(item.to_dict)
        data = item.to_dict()
        assert isinstance(data, dict)
        assert data.get("id") == item.id
        assert data.get("chef_id") == item.chef_id
        assert data.get("order_id") == item.order_id
        assert data.get("dish_name") == item.dish_name
        assert data.get("status") == item.status
        assert data.get("priority") == item.priority
        assert "queued_at" in data
        assert "started_at" in data
        assert "ready_at" in data
        assert data.get("notes") == item.notes

    def test_dishqueueitem_unique_constraints(self, app_context):
        chef = _create_chef()
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        item1 = DishQueueItem(chef_id=chef.id, order_id=order_id, dish_name="Soup")
        item2 = DishQueueItem(chef_id=chef.id, order_id=order_id, dish_name="Soup")
        db.session.add(item1)
        db.session.add(item2)
        db.session.commit()
        assert item1.id is not None
        assert item2.id is not None
        assert item1.id != item2.id

class TestChefQueueRoutes:
    def test_chef_id_queue_get_exists(self, client):
        rules = [r for r in app.url_map.iter_rules() if r.rule == "/chef/<int:chef_id>/queue"]
        assert rules, "Route /chef/<int:chef_id>/queue is missing"
        assert any("GET" in r.methods for r in rules), "Route /chef/<int:chef_id>/queue must accept GET"

    def test_chef_id_queue_get_renders_template(self, client, app_context):
        chef = _create_chef()
        response = client.get(f"/chef/{chef.id}/queue")
        assert response.status_code == 200
        assert response.mimetype in ("text/html", "application/xhtml+xml", "text/html; charset=utf-8")
        assert str(chef.id).encode() in response.data or chef.name.encode() in response.data

class TestStartQueueItemRoute:
    def test_chef_id_queue_item_id_start_post_exists(self, client):
        rules = [
            r
            for r in app.url_map.iter_rules()
            if r.rule == "/chef/<int:chef_id>/queue/<int:item_id>/start"
        ]
        assert rules, "Route /chef/<int:chef_id>/queue/<int:item_id>/start is missing"
        assert any("POST" in r.methods for r in rules), "Route must accept POST"

    def test_chef_id_queue_item_id_start_post_success(self, client, app_context):
        chef = _create_chef()
        item = _create_queue_item(chef_id=chef.id, status="QUEUED")
        response = client.post(f"/chef/{chef.id}/queue/{item.id}/start", data={})
        assert response.status_code in (200, 204, 302)

        refreshed = DishQueueItem.query.filter_by(id=item.id).first()
        assert refreshed is not None
        assert refreshed.status in ("IN_PROGRESS", "READY")
        if refreshed.status == "IN_PROGRESS":
            assert refreshed.started_at is not None

    def test_chef_id_queue_item_id_start_post_missing_required_fields(self, client, app_context):
        chef = _create_chef()
        item = _create_queue_item(chef_id=chef.id, status="QUEUED")
        response = client.post(
            f"/chef/{chef.id}/queue/{item.id}/start",
            data={"unexpected": ""},
        )
        assert response.status_code in (200, 204, 302, 400, 422)

    def test_chef_id_queue_item_id_start_post_invalid_data(self, client, app_context):
        chef = _create_chef()
        item = _create_queue_item(chef_id=chef.id, status="QUEUED")
        response = client.post(
            f"/chef/{chef.id}/queue/{item.id}/start",
            data={"started_at": "not-a-datetime"},
        )
        assert response.status_code in (200, 204, 302, 400, 422)

    def test_chef_id_queue_item_id_start_post_duplicate_data(self, client, app_context):
        chef = _create_chef()
        item = _create_queue_item(chef_id=chef.id, status="QUEUED")
        first = client.post(f"/chef/{chef.id}/queue/{item.id}/start", data={})
        assert first.status_code in (200, 204, 302)

        second = client.post(f"/chef/{chef.id}/queue/{item.id}/start", data={})
        assert second.status_code in (200, 204, 302, 400, 409, 422)

        refreshed = DishQueueItem.query.filter_by(id=item.id).first()
        assert refreshed is not None
        assert refreshed.status in ("IN_PROGRESS", "READY")

class TestMarkQueueItemReadyRoute:
    def test_chef_id_queue_item_id_ready_post_exists(self, client):
        rules = [
            r
            for r in app.url_map.iter_rules()
            if r.rule == "/chef/<int:chef_id>/queue/<int:item_id>/ready"
        ]
        assert rules, "Route /chef/<int:chef_id>/queue/<int:item_id>/ready is missing"
        assert any("POST" in r.methods for r in rules), "Route must accept POST"

    def test_chef_id_queue_item_id_ready_post_success(self, client, app_context):
        chef = _create_chef()
        item = _create_queue_item(chef_id=chef.id, status="IN_PROGRESS")
        response = client.post(f"/chef/{chef.id}/queue/{item.id}/ready", data={})
        assert response.status_code in (200, 204, 302)

        refreshed = DishQueueItem.query.filter_by(id=item.id).first()
        assert refreshed is not None
        assert refreshed.status == "READY"
        assert refreshed.ready_at is not None

    def test_chef_id_queue_item_id_ready_post_missing_required_fields(self, client, app_context):
        chef = _create_chef()
        item = _create_queue_item(chef_id=chef.id, status="IN_PROGRESS")
        response = client.post(
            f"/chef/{chef.id}/queue/{item.id}/ready",
            data={"unexpected": ""},
        )
        assert response.status_code in (200, 204, 302, 400, 422)

    def test_chef_id_queue_item_id_ready_post_invalid_data(self, client, app_context):
        chef = _create_chef()
        item = _create_queue_item(chef_id=chef.id, status="IN_PROGRESS")
        response = client.post(
            f"/chef/{chef.id}/queue/{item.id}/ready",
            data={"ready_at": "not-a-datetime"},
        )
        assert response.status_code in (200, 204, 302, 400, 422)

    def test_chef_id_queue_item_id_ready_post_duplicate_data(self, client, app_context):
        chef = _create_chef()
        item = _create_queue_item(chef_id=chef.id, status="IN_PROGRESS")
        first = client.post(f"/chef/{chef.id}/queue/{item.id}/ready", data={})
        assert first.status_code in (200, 204, 302)

        second = client.post(f"/chef/{chef.id}/queue/{item.id}/ready", data={})
        assert second.status_code in (200, 204, 302, 400, 409, 422)

        refreshed = DishQueueItem.query.filter_by(id=item.id).first()
        assert refreshed is not None
        assert refreshed.status == "READY"

class TestHelperGetChefOr404:
    def test_get_chef_or_404_function_exists(self):
        assert callable(get_chef_or_404)

    def test_get_chef_or_404_with_valid_input(self, app_context):
        chef = _create_chef()
        result = get_chef_or_404(chef.id)
        assert isinstance(result, Chef)
        assert result.id == chef.id

    def test_get_chef_or_404_with_invalid_input(self, app_context):
        with pytest.raises(Exception):
            get_chef_or_404(999999)

class TestHelperGetQueueItemOr404:
    def test_get_queue_item_or_404_function_exists(self):
        assert callable(get_queue_item_or_404)

    def test_get_queue_item_or_404_with_valid_input(self, app_context):
        chef = _create_chef()
        item = _create_queue_item(chef_id=chef.id)
        result = get_queue_item_or_404(chef.id, item.id)
        assert isinstance(result, DishQueueItem)
        assert result.id == item.id
        assert result.chef_id == chef.id

    def test_get_queue_item_or_404_with_invalid_input(self, app_context):
        chef = _create_chef()
        other_chef = _create_chef()
        item = _create_queue_item(chef_id=chef.id)
        with pytest.raises(Exception):
            get_queue_item_or_404(other_chef.id, item.id)

class TestHelperSerializeQueue:
    def test_serialize_queue_function_exists(self):
        assert callable(serialize_queue)

    def test_serialize_queue_with_valid_input(self, app_context):
        chef = _create_chef()
        item1 = _create_queue_item(chef_id=chef.id, dish_name="A", priority=1)
        item2 = _create_queue_item(chef_id=chef.id, dish_name="B", priority=0)
        data = serialize_queue(chef, [item1, item2])
        assert isinstance(data, dict)
        assert "chef" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        assert data["chef"].get("id") == chef.id
        ids = [it.get("id") for it in data["items"] if isinstance(it, dict)]
        assert item1.id in ids and item2.id in ids

    def test_serialize_queue_with_invalid_input(self, app_context):
        chef = _create_chef()
        with pytest.raises(Exception):
            serialize_queue(chef, None)