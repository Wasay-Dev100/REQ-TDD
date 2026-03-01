import os
import sys
import uuid
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.chef_order_queue_chef import Chef
from models.chef_order_queue_order import KitchenOrder
from models.chef_order_queue_order_item import KitchenOrderItem
from models.chef_order_queue_queue_item import ChefQueueItem
from controllers.chef_order_queue_controller import (
    classify_dish_category,
    select_chef_for_category,
    assign_order_items_to_chefs,
    serialize_queue_item,
    serialize_chef_queue,
)
from views.chef_order_queue_views import render_kitchen_screen, render_chef_queue

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

def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_chef(*, name=None, specialty_category="grill", is_active=True):
    chef = Chef(
        name=name or _unique("chef"),
        specialty_category=specialty_category,
        is_active=is_active,
    )
    db.session.add(chef)
    db.session.commit()
    return chef

def _create_kitchen_order(*, external_order_id=None, status="queued"):
    order = KitchenOrder(
        external_order_id=external_order_id or _unique("ext_order"),
        status=status,
    )
    db.session.add(order)
    db.session.commit()
    return order

def _create_order_item(
    *,
    kitchen_order_id: int,
    dish_name="Burger",
    dish_category="grill",
    quantity=1,
    notes=None,
):
    item = KitchenOrderItem(
        kitchen_order_id=kitchen_order_id,
        dish_name=dish_name,
        dish_category=dish_category,
        quantity=quantity,
        notes=notes,
    )
    db.session.add(item)
    db.session.commit()
    return item

def _create_queue_item(
    *,
    chef_id: int,
    kitchen_order_item_id: int,
    queue_status="queued",
    priority=0,
):
    qi = ChefQueueItem(
        chef_id=chef_id,
        kitchen_order_item_id=kitchen_order_item_id,
        queue_status=queue_status,
        priority=priority,
    )
    db.session.add(qi)
    db.session.commit()
    return qi

def _route_exists(path: str, method: str) -> bool:
    method = method.upper()
    for rule in app.url_map.iter_rules():
        if rule.rule == path and method in rule.methods:
            return True
    return False

def _assert_template_like_response(response):
    assert response.status_code == 200
    ct = response.headers.get("Content-Type", "")
    assert "text/html" in ct or "application/xhtml+xml" in ct or ct.startswith("text/html")

# MODEL: Chef
def test_chef_model_has_required_fields(app_context):
    for field in ["id", "name", "specialty_category", "is_active", "created_at"]:
        assert hasattr(Chef, field), f"Chef missing required field: {field}"

def test_chef_can_prepare(app_context):
    chef = Chef(name=_unique("chef"), specialty_category="grill", is_active=True)
    assert hasattr(chef, "can_prepare")
    assert callable(getattr(chef, "can_prepare"))
    assert chef.can_prepare("grill") is True
    assert chef.can_prepare("salad") is False

def test_chef_unique_constraints(app_context):
    name = _unique("chef")
    c1 = Chef(name=name, specialty_category="grill", is_active=True)
    db.session.add(c1)
    db.session.commit()

    c2 = Chef(name=name, specialty_category="grill", is_active=True)
    db.session.add(c2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# MODEL: KitchenOrder
def test_kitchenorder_model_has_required_fields(app_context):
    for field in ["id", "external_order_id", "status", "created_at"]:
        assert hasattr(KitchenOrder, field), f"KitchenOrder missing required field: {field}"

def test_kitchenorder_is_open(app_context):
    order = KitchenOrder(external_order_id=_unique("ext"), status="queued")
    assert hasattr(order, "is_open")
    assert callable(getattr(order, "is_open"))
    assert order.is_open() is True
    order.status = "completed"
    assert order.is_open() is False

def test_kitchenorder_unique_constraints(app_context):
    ext_id = _unique("ext")
    o1 = KitchenOrder(external_order_id=ext_id, status="queued")
    db.session.add(o1)
    db.session.commit()

    o2 = KitchenOrder(external_order_id=ext_id, status="queued")
    db.session.add(o2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# MODEL: KitchenOrderItem
def test_kitchenorderitem_model_has_required_fields(app_context):
    for field in [
        "id",
        "kitchen_order_id",
        "dish_name",
        "dish_category",
        "quantity",
        "notes",
        "created_at",
    ]:
        assert hasattr(KitchenOrderItem, field), f"KitchenOrderItem missing required field: {field}"

def test_kitchenorderitem_display_label(app_context):
    order = _create_kitchen_order()
    item = KitchenOrderItem(
        kitchen_order_id=order.id,
        dish_name="Margherita Pizza",
        dish_category="pizza",
        quantity=2,
        notes="extra basil",
    )
    assert hasattr(item, "display_label")
    assert callable(getattr(item, "display_label"))
    label = item.display_label()
    assert isinstance(label, str)
    assert "Margherita" in label or "Pizza" in label or "2" in label

def test_kitchenorderitem_unique_constraints(app_context):
    order = _create_kitchen_order()
    i1 = KitchenOrderItem(
        kitchen_order_id=order.id,
        dish_name="Dish A",
        dish_category="grill",
        quantity=1,
        notes=None,
    )
    i2 = KitchenOrderItem(
        kitchen_order_id=order.id,
        dish_name="Dish A",
        dish_category="grill",
        quantity=1,
        notes=None,
    )
    db.session.add_all([i1, i2])
    db.session.commit()
    assert i1.id is not None and i2.id is not None and i1.id != i2.id

# MODEL: ChefQueueItem
def test_chefqueueitem_model_has_required_fields(app_context):
    for field in [
        "id",
        "chef_id",
        "kitchen_order_item_id",
        "queue_status",
        "priority",
        "assigned_at",
        "started_at",
        "completed_at",
    ]:
        assert hasattr(ChefQueueItem, field), f"ChefQueueItem missing required field: {field}"

def test_chefqueueitem_mark_started(app_context):
    chef = _create_chef(specialty_category="grill")
    order = _create_kitchen_order()
    item = _create_order_item(kitchen_order_id=order.id, dish_name="Burger", dish_category="grill")
    qi = ChefQueueItem(chef_id=chef.id, kitchen_order_item_id=item.id, queue_status="queued", priority=0)
    db.session.add(qi)
    db.session.commit()

    assert hasattr(qi, "mark_started")
    assert callable(getattr(qi, "mark_started"))
    qi.mark_started()
    db.session.commit()

    assert qi.started_at is not None
    assert qi.queue_status in ("in_progress", "started", "processing")

def test_chefqueueitem_mark_completed(app_context):
    chef = _create_chef(specialty_category="grill")
    order = _create_kitchen_order()
    item = _create_order_item(kitchen_order_id=order.id, dish_name="Burger", dish_category="grill")
    qi = ChefQueueItem(chef_id=chef.id, kitchen_order_item_id=item.id, queue_status="queued", priority=0)
    db.session.add(qi)
    db.session.commit()

    assert hasattr(qi, "mark_completed")
    assert callable(getattr(qi, "mark_completed"))
    qi.mark_completed()
    db.session.commit()

    assert qi.completed_at is not None
    assert qi.queue_status in ("completed", "done", "finished")

def test_chefqueueitem_unique_constraints(app_context):
    chef = _create_chef(specialty_category="grill")
    order = _create_kitchen_order()
    item = _create_order_item(kitchen_order_id=order.id, dish_name="Burger", dish_category="grill")

    q1 = ChefQueueItem(chef_id=chef.id, kitchen_order_item_id=item.id, queue_status="queued", priority=0)
    db.session.add(q1)
    db.session.commit()

    q2 = ChefQueueItem(chef_id=chef.id, kitchen_order_item_id=item.id, queue_status="queued", priority=0)
    db.session.add(q2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

# ROUTE: /chef-order-queue/chefs (GET)
def test_chef_order_queue_chefs_get_exists(client):
    assert _route_exists("/chef-order-queue/chefs", "GET") is True

def test_chef_order_queue_chefs_get_renders_template(client):
    response = client.get("/chef-order-queue/chefs")
    _assert_template_like_response(response)

# ROUTE: /chef-order-queue/chefs (POST)
def test_chef_order_queue_chefs_post_exists(client):
    assert _route_exists("/chef-order-queue/chefs", "POST") is True

def test_chef_order_queue_chefs_post_success(client):
    payload = {"name": _unique("chef"), "specialty_category": "grill", "is_active": "true"}
    response = client.post("/chef-order-queue/chefs", data=payload, follow_redirects=False)
    assert response.status_code in (200, 201, 302)

    with app.app_context():
        created = Chef.query.filter_by(name=payload["name"]).first()
        assert created is not None
        assert created.specialty_category == "grill"

def test_chef_order_queue_chefs_post_missing_required_fields(client):
    response = client.post("/chef-order-queue/chefs", data={"specialty_category": "grill"})
    assert response.status_code in (200, 400, 422)

def test_chef_order_queue_chefs_post_invalid_data(client):
    response = client.post(
        "/chef-order-queue/chefs",
        data={"name": "", "specialty_category": "", "is_active": "notabool"},
    )
    assert response.status_code in (200, 400, 422)

def test_chef_order_queue_chefs_post_duplicate_data(client):
    name = _unique("chef")
    with app.app_context():
        db.session.add(Chef(name=name, specialty_category="grill", is_active=True))
        db.session.commit()

    response = client.post("/chef-order-queue/chefs", data={"name": name, "specialty_category": "grill"})
    assert response.status_code in (200, 400, 409, 422)

# ROUTE: /chef-order-queue/orders (POST)
def test_chef_order_queue_orders_post_exists(client):
    assert _route_exists("/chef-order-queue/orders", "POST") is True

def test_chef_order_queue_orders_post_success(client):
    with app.app_context():
        _create_chef(specialty_category="grill")
        _create_chef(specialty_category="salad")

    ext_id = _unique("ext_order")
    payload = {
        "external_order_id": ext_id,
        "items": [
            {"dish_name": "Burger", "dish_category": "grill", "quantity": 1, "notes": ""},
            {"dish_name": "Caesar Salad", "dish_category": "salad", "quantity": 2, "notes": "no croutons"},
        ],
    }
    response = client.post("/chef-order-queue/orders", json=payload, follow_redirects=False)
    assert response.status_code in (200, 201, 302)

    with app.app_context():
        order = KitchenOrder.query.filter_by(external_order_id=ext_id).first()
        assert order is not None
        assert ChefQueueItem.query.count() >= 1

def test_chef_order_queue_orders_post_missing_required_fields(client):
    response = client.post("/chef-order-queue/orders", json={"items": []})
    assert response.status_code in (200, 400, 422)

def test_chef_order_queue_orders_post_invalid_data(client):
    response = client.post(
        "/chef-order-queue/orders",
        json={"external_order_id": "", "items": "not-a-list"},
    )
    assert response.status_code in (200, 400, 422)

def test_chef_order_queue_orders_post_duplicate_data(client):
    ext_id = _unique("ext_order")
    with app.app_context():
        _create_kitchen_order(external_order_id=ext_id)

    response = client.post(
        "/chef-order-queue/orders",
        json={"external_order_id": ext_id, "items": [{"dish_name": "Burger", "dish_category": "grill", "quantity": 1}]},
    )
    assert response.status_code in (200, 400, 409, 422)

# ROUTE: /chef-order-queue/chefs/<int:chef_id>/queue (GET)
def test_chef_order_queue_chefs_chef_id_queue_get_exists(client):
    assert _route_exists("/chef-order-queue/chefs/<int:chef_id>/queue", "GET") is True

def test_chef_order_queue_chefs_chef_id_queue_get_renders_template(client):
    with app.app_context():
        chef = _create_chef(specialty_category="grill")
    response = client.get(f"/chef-order-queue/chefs/{chef.id}/queue")
    _assert_template_like_response(response)

# ROUTE: /chef-order-queue/kitchen-screen (GET)
def test_chef_order_queue_kitchen_screen_get_exists(client):
    assert _route_exists("/chef-order-queue/kitchen-screen", "GET") is True

def test_chef_order_queue_kitchen_screen_get_renders_template(client):
    response = client.get("/chef-order-queue/kitchen-screen")
    _assert_template_like_response(response)

# ROUTE: /chef-order-queue/queue-items/<int:queue_item_id>/start (POST)
def test_chef_order_queue_queue_items_queue_item_id_start_post_exists(client):
    assert _route_exists("/chef-order-queue/queue-items/<int:queue_item_id>/start", "POST") is True

def test_chef_order_queue_queue_items_queue_item_id_start_post_success(client):
    with app.app_context():
        chef = _create_chef(specialty_category="grill")
        order = _create_kitchen_order()
        item = _create_order_item(kitchen_order_id=order.id, dish_name="Burger", dish_category="grill")
        qi = _create_queue_item(chef_id=chef.id, kitchen_order_item_id=item.id)

    response = client.post(f"/chef-order-queue/queue-items/{qi.id}/start", data={}, follow_redirects=False)
    assert response.status_code in (200, 204, 302)

    with app.app_context():
        refreshed = ChefQueueItem.query.filter_by(id=qi.id).first()
        assert refreshed is not None
        assert refreshed.started_at is not None
        assert refreshed.queue_status in ("in_progress", "started", "processing")

def test_chef_order_queue_queue_items_queue_item_id_start_post_missing_required_fields(client):
    response = client.post("/chef-order-queue/queue-items/999999/start", data={})
    assert response.status_code in (200, 400, 404, 422)

def test_chef_order_queue_queue_items_queue_item_id_start_post_invalid_data(client):
    response = client.post("/chef-order-queue/queue-items/not-an-int/start", data={})
    assert response.status_code in (404, 405)

def test_chef_order_queue_queue_items_queue_item_id_start_post_duplicate_data(client):
    with app.app_context():
        chef = _create_chef(specialty_category="grill")
        order = _create_kitchen_order()
        item = _create_order_item(kitchen_order_id=order.id, dish_name="Burger", dish_category="grill")
        qi = _create_queue_item(chef_id=chef.id, kitchen_order_item_id=item.id)
        qi.mark_started()
        db.session.commit()

    response = client.post(f"/chef-order-queue/queue-items/{qi.id}/start", data={}, follow_redirects=False)
    assert response.status_code in (200, 204, 302, 400, 409, 422)

# ROUTE: /chef-order-queue/queue-items/<int:queue_item_id>/complete (POST)
def test_chef_order_queue_queue_items_queue_item_id_complete_post_exists(client):
    assert _route_exists("/chef-order-queue/queue-items/<int:queue_item_id>/complete", "POST") is True

def test_chef_order_queue_queue_items_queue_item_id_complete_post_success(client):
    with app.app_context():
        chef = _create_chef(specialty_category="grill")
        order = _create_kitchen_order()
        item = _create_order_item(kitchen_order_id=order.id, dish_name="Burger", dish_category="grill")
        qi = _create_queue_item(chef_id=chef.id, kitchen_order_item_id=item.id)
        qi.mark_started()
        db.session.commit()

    response = client.post(f"/chef-order-queue/queue-items/{qi.id}/complete", data={}, follow_redirects=False)
    assert response.status_code in (200, 204, 302)

    with app.app_context():
        refreshed = ChefQueueItem.query.filter_by(id=qi.id).first()
        assert refreshed is not None
        assert refreshed.completed_at is not None
        assert refreshed.queue_status in ("completed", "done", "finished")

def test_chef_order_queue_queue_items_queue_item_id_complete_post_missing_required_fields(client):
    response = client.post("/chef-order-queue/queue-items/999999/complete", data={})
    assert response.status_code in (200, 400, 404, 422)

def test_chef_order_queue_queue_items_queue_item_id_complete_post_invalid_data(client):
    response = client.post("/chef-order-queue/queue-items/not-an-int/complete", data={})
    assert response.status_code in (404, 405)

def test_chef_order_queue_queue_items_queue_item_id_complete_post_duplicate_data(client):
    with app.app_context():
        chef = _create_chef(specialty_category="grill")
        order = _create_kitchen_order()
        item = _create_order_item(kitchen_order_id=order.id, dish_name="Burger", dish_category="grill")
        qi = _create_queue_item(chef_id=chef.id, kitchen_order_item_id=item.id)
        qi.mark_completed()
        db.session.commit()

    response = client.post(f"/chef-order-queue/queue-items/{qi.id}/complete", data={}, follow_redirects=False)
    assert response.status_code in (200, 204, 302, 400, 409, 422)

# HELPER: classify_dish_category(dish_name, dish_category)
def test_classify_dish_category_function_exists():
    assert callable(classify_dish_category)

def test_classify_dish_category_with_valid_input():
    result = classify_dish_category("Burger", "grill")
    assert isinstance(result, str)
    assert result != ""

def test_classify_dish_category_with_invalid_input():
    with pytest.raises(Exception):
        classify_dish_category(None, None)

# HELPER: select_chef_for_category(dish_category)
def test_select_chef_for_category_function_exists():
    assert callable(select_chef_for_category)

def test_select_chef_for_category_with_valid_input(app_context):
    chef = _create_chef(specialty_category="grill", is_active=True)
    selected = select_chef_for_category("grill")
    assert selected is not None
    assert isinstance(selected, Chef)
    assert selected.id == chef.id

def test_select_chef_for_category_with_invalid_input(app_context):
    _create_chef(specialty_category="grill", is_active=True)
    with pytest.raises(Exception):
        select_chef_for_category(None)

# HELPER: assign_order_items_to_chefs(kitchen_order, items_payload)
def test_assign_order_items_to_chefs_function_exists():
    assert callable(assign_order_items_to_chefs)

def test_assign_order_items_to_chefs_with_valid_input(app_context):
    _create_chef(specialty_category="grill", is_active=True)
    _create_chef(specialty_category="salad", is_active=True)

    order = _create_kitchen_order()
    items_payload = [
        {"dish_name": "Burger", "dish_category": "grill", "quantity": 1, "notes": ""},
        {"dish_name": "Caesar Salad", "dish_category": "salad", "quantity": 2, "notes": "no croutons"},
    ]
    queue_items = assign_order_items_to_chefs(order, items_payload)
    assert isinstance(queue_items, list)
    assert len(queue_items) == 2
    assert all(isinstance(qi, ChefQueueItem) for qi in queue_items)

def test_assign_order_items_to_chefs_with_invalid_input(app_context):
    order = _create_kitchen_order()
    with pytest.raises(Exception):
        assign_order_items_to_chefs(order, None)

# HELPER: serialize_queue_item(queue_item)
def test_serialize_queue_item_function_exists():
    assert callable(serialize_queue_item)

def test_serialize_queue_item_with_valid_input(app_context):
    chef = _create_chef(specialty_category="grill")
    order = _create_kitchen_order()
    item = _create_order_item(kitchen_order_id=order.id, dish_name="Burger", dish_category="grill")
    qi = _create_queue_item(chef_id=chef.id, kitchen_order_item_id=item.id)

    payload = serialize_queue_item(qi)
    assert isinstance(payload, dict)
    assert "id" in payload
    assert payload.get("id") == qi.id

def test_serialize_queue_item_with_invalid_input():
    with pytest.raises(Exception):
        serialize_queue_item(None)

# HELPER: serialize_chef_queue(chef, queue_items)
def test_serialize_chef_queue_function_exists():
    assert callable(serialize_chef_queue)

def test_serialize_chef_queue_with_valid_input(app_context):
    chef = _create_chef(specialty_category="grill")
    order = _create_kitchen_order()
    item = _create_order_item(kitchen_order_id=order.id, dish_name="Burger", dish_category="grill")
    qi = _create_queue_item(chef_id=chef.id, kitchen_order_item_id=item.id)

    payload = serialize_chef_queue(chef, [qi])
    assert isinstance(payload, dict)
    assert "chef" in payload or "chef_id" in payload or "name" in payload
    assert "queue" in payload or "items" in payload or "queue_items" in payload

def test_serialize_chef_queue_with_invalid_input(app_context):
    chef = _create_chef(specialty_category="grill")
    with pytest.raises(Exception):
        serialize_chef_queue(chef, None)