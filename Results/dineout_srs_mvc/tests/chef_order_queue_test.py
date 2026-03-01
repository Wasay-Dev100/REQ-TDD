import osfrom unittest.mock import patch

import sys
import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db  # noqa: E402
from models.user import User  # noqa: E402
from models.chef_order_queue_chef import Chef  # noqa: E402
from models.chef_order_queue_dish_category import DishCategory  # noqa: E402
from models.chef_order_queue_dish import Dish  # noqa: E402
from models.chef_order_queue_order import Order  # noqa: E402
from models.chef_order_queue_order_item import OrderItem  # noqa: E402
from models.chef_order_queue_chef_specialty import ChefSpecialty  # noqa: E402
from models.chef_order_queue_chef_queue_item import ChefQueueItem  # noqa: E402

from controllers.chef_order_queue_controller import (  # noqa: E402
    chef_order_queue_bp,
    classify_dish_category,
    select_chef_for_category,
    enqueue_order_item_for_chef,
    recompute_queue_positions,
    serialize_kitchen_queue,
)

from views.chef_order_queue_views import render_kitchen_screen  # noqa: E402

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

def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_user(*, email=None, username=None, role="chef", password="pw12345"):
    u = User(
        email=email or f"{_uid('u')}@example.com",
        username=username or _uid("user"),
        role=role,
        password_hash="",
    )
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u

def _create_category(*, code=None, name=None):
    c = DishCategory(code=code or _uid("cat"), name=name or _uid("Category"))
    db.session.add(c)
    db.session.commit()
    return c

def _create_dish(*, name=None, category_id=None, is_active=True):
    d = Dish(name=name or _uid("Dish"), category_id=category_id, is_active=is_active)
    db.session.add(d)
    db.session.commit()
    return d

def _create_chef(*, user_id=None, display_name=None, is_active=True):
    chef = Chef(
        user_id=user_id,
        display_name=display_name or _uid("Chef"),
        is_active=is_active,
    )
    db.session.add(chef)
    db.session.commit()
    return chef

def _create_specialty(*, chef_id=None, dish_category_id=None, priority=100):
    s = ChefSpecialty(chef_id=chef_id, dish_category_id=dish_category_id, priority=priority)
    db.session.add(s)
    db.session.commit()
    return s

def _create_order(*, customer_name=None, status="confirmed"):
    o = Order(customer_name=customer_name or _uid("Customer"), status=status)
    db.session.add(o)
    db.session.commit()
    return o

def _create_order_item(*, order_id=None, dish_id=None, quantity=1, notes=None):
    oi = OrderItem(order_id=order_id, dish_id=dish_id, quantity=quantity, notes=notes)
    db.session.add(oi)
    db.session.commit()
    return oi

def _create_queue_item(
    *,
    chef_id=None,
    order_item_id=None,
    status="queued",
    position=1,
    assigned_at=None,
    started_at=None,
    completed_at=None,
):
    kwargs = dict(
        chef_id=chef_id,
        order_item_id=order_item_id,
        status=status,
        position=position,
    )
    if assigned_at is not None:
        kwargs["assigned_at"] = assigned_at
    if started_at is not None:
        kwargs["started_at"] = started_at
    if completed_at is not None:
        kwargs["completed_at"] = completed_at
    qi = ChefQueueItem(**kwargs)
    db.session.add(qi)
    db.session.commit()
    return qi

# MODEL: User (models/user.py)
def test_user_model_has_required_fields():
    for field in ["id", "email", "username", "password_hash", "role"]:
        assert hasattr(User, field), f"Missing field on User: {field}"

def test_user_set_password():
    u = User(email=f"{_uid('u')}@example.com", username=_uid("user"), password_hash="", role="customer")
    u.set_password("secret123")
    assert u.password_hash
    assert u.password_hash != "secret123"

def test_user_check_password():
    u = User(email=f"{_uid('u')}@example.com", username=_uid("user"), password_hash="", role="customer")
    u.set_password("secret123")
    assert u.check_password("secret123") is True
    assert u.check_password("wrong") is False

def test_user_unique_constraints(app_context):
    email = f"{_uid('dup')}@example.com"
    username = _uid("dupuser")
    u1 = User(email=email, username=username, password_hash="", role="customer")
    u1.set_password("pw")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_uid("otheruser"), password_hash="", role="customer")
    u2.set_password("pw")
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_uid('other')}@example.com", username=username, password_hash="", role="customer")
    u3.set_password("pw")
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: Chef (models/chef_order_queue_chef.py)
def test_chef_model_has_required_fields():
    for field in ["id", "user_id", "display_name", "is_active", "created_at"]:
        assert hasattr(Chef, field), f"Missing field on Chef: {field}"

def test_chef_is_specialized_for(app_context):
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id, display_name=_uid("Chef"))
    cat = _create_category()
    _create_specialty(chef_id=chef.id, dish_category_id=cat.id, priority=10)

    assert chef.is_specialized_for(cat) is True

    other_cat = _create_category()
    assert chef.is_specialized_for(other_cat) is False

def test_chef_unique_constraints(app_context):
    user = _create_user(role="chef")
    chef1 = _create_chef(user_id=user.id, display_name=_uid("Chef"))
    assert chef1.id is not None

    chef2 = Chef(user_id=user.id, display_name=_uid("Chef2"), is_active=True)
    db.session.add(chef2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: DishCategory (models/chef_order_queue_dish_category.py)
def test_dishcategory_model_has_required_fields():
    for field in ["id", "code", "name", "created_at"]:
        assert hasattr(DishCategory, field), f"Missing field on DishCategory: {field}"

def test_dishcategory_to_dict(app_context):
    cat = _create_category(code=_uid("code"), name=_uid("name"))
    d = cat.to_dict()
    assert isinstance(d, dict)
    for k in ["id", "code", "name"]:
        assert k in d

def test_dishcategory_unique_constraints(app_context):
    code = _uid("code")
    name = _uid("name")
    c1 = DishCategory(code=code, name=name)
    db.session.add(c1)
    db.session.commit()

    c2 = DishCategory(code=code, name=_uid("name2"))
    db.session.add(c2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    c3 = DishCategory(code=_uid("code2"), name=name)
    db.session.add(c3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: Dish (models/chef_order_queue_dish.py)
def test_dish_model_has_required_fields():
    for field in ["id", "name", "category_id", "is_active", "created_at"]:
        assert hasattr(Dish, field), f"Missing field on Dish: {field}"

def test_dish_to_dict(app_context):
    cat = _create_category()
    dish = _create_dish(category_id=cat.id, name=_uid("Dish"))
    d = dish.to_dict()
    assert isinstance(d, dict)
    for k in ["id", "name", "category_id", "is_active"]:
        assert k in d

def test_dish_unique_constraints(app_context):
    cat = _create_category()
    d1 = Dish(name=_uid("Dish"), category_id=cat.id, is_active=True)
    d2 = Dish(name=_uid("Dish"), category_id=cat.id, is_active=True)
    db.session.add_all([d1, d2])
    db.session.commit()
    assert d1.id is not None and d2.id is not None

# MODEL: Order (models/chef_order_queue_order.py)
def test_order_model_has_required_fields():
    for field in ["id", "customer_name", "status", "confirmed_at"]:
        assert hasattr(Order, field), f"Missing field on Order: {field}"

def test_order_to_dict(app_context):
    order = _create_order(customer_name=_uid("Customer"), status="confirmed")
    d = order.to_dict()
    assert isinstance(d, dict)
    for k in ["id", "customer_name", "status", "confirmed_at"]:
        assert k in d

def test_order_unique_constraints(app_context):
    o1 = Order(customer_name=_uid("Customer"), status="confirmed")
    o2 = Order(customer_name=_uid("Customer"), status="confirmed")
    db.session.add_all([o1, o2])
    db.session.commit()
    assert o1.id is not None and o2.id is not None

# MODEL: OrderItem (models/chef_order_queue_order_item.py)
def test_orderitem_model_has_required_fields():
    for field in ["id", "order_id", "dish_id", "quantity", "notes"]:
        assert hasattr(OrderItem, field), f"Missing field on OrderItem: {field}"

def test_orderitem_to_dict(app_context):
    cat = _create_category()
    dish = _create_dish(category_id=cat.id)
    order = _create_order()
    oi = _create_order_item(order_id=order.id, dish_id=dish.id, quantity=2, notes="no onions")
    d = oi.to_dict()
    assert isinstance(d, dict)
    for k in ["id", "order_id", "dish_id", "quantity", "notes"]:
        assert k in d

def test_orderitem_unique_constraints(app_context):
    cat = _create_category()
    dish = _create_dish(category_id=cat.id)
    order = _create_order()
    oi1 = OrderItem(order_id=order.id, dish_id=dish.id, quantity=1, notes=None)
    oi2 = OrderItem(order_id=order.id, dish_id=dish.id, quantity=1, notes=None)
    db.session.add_all([oi1, oi2])
    db.session.commit()
    assert oi1.id is not None and oi2.id is not None

# MODEL: ChefSpecialty (models/chef_order_queue_chef_specialty.py)
def test_chefspecialty_model_has_required_fields():
    for field in ["id", "chef_id", "dish_category_id", "priority"]:
        assert hasattr(ChefSpecialty, field), f"Missing field on ChefSpecialty: {field}"

def test_chefspecialty_to_dict(app_context):
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id)
    cat = _create_category()
    spec = _create_specialty(chef_id=chef.id, dish_category_id=cat.id, priority=5)
    d = spec.to_dict()
    assert isinstance(d, dict)
    for k in ["id", "chef_id", "dish_category_id", "priority"]:
        assert k in d

def test_chefspecialty_unique_constraints(app_context):
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id)
    cat = _create_category()
    s1 = ChefSpecialty(chef_id=chef.id, dish_category_id=cat.id, priority=10)
    s2 = ChefSpecialty(chef_id=chef.id, dish_category_id=cat.id, priority=10)
    db.session.add_all([s1, s2])
    db.session.commit()
    assert s1.id is not None and s2.id is not None

# MODEL: ChefQueueItem (models/chef_order_queue_chef_queue_item.py)
def test_chefqueueitem_model_has_required_fields():
    for field in [
        "id",
        "chef_id",
        "order_item_id",
        "status",
        "position",
        "assigned_at",
        "started_at",
        "completed_at",
    ]:
        assert hasattr(ChefQueueItem, field), f"Missing field on ChefQueueItem: {field}"

def test_chefqueueitem_to_dict(app_context):
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id)
    cat = _create_category()
    dish = _create_dish(category_id=cat.id)
    order = _create_order()
    oi = _create_order_item(order_id=order.id, dish_id=dish.id, quantity=1, notes=None)
    qi = _create_queue_item(chef_id=chef.id, order_item_id=oi.id, status="queued", position=1)
    d = qi.to_dict()
    assert isinstance(d, dict)
    for k in ["id", "chef_id", "order_item_id", "status", "position", "assigned_at", "started_at", "completed_at"]:
        assert k in d

def test_chefqueueitem_unique_constraints(app_context):
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id)
    cat = _create_category()
    dish = _create_dish(category_id=cat.id)
    order = _create_order()
    oi1 = _create_order_item(order_id=order.id, dish_id=dish.id, quantity=1)
    oi2 = _create_order_item(order_id=order.id, dish_id=dish.id, quantity=1)
    q1 = ChefQueueItem(chef_id=chef.id, order_item_id=oi1.id, status="queued", position=1)
    q2 = ChefQueueItem(chef_id=chef.id, order_item_id=oi2.id, status="queued", position=2)
    db.session.add_all([q1, q2])
    db.session.commit()
    assert q1.id is not None and q2.id is not None

# ROUTE: /orders/confirm (POST)
def test_orders_confirm_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/orders/confirm"]
    assert rules, "Route /orders/confirm is missing"
    assert any("POST" in r.methods for r in rules), "Route /orders/confirm does not accept POST"

    resp = client.post("/orders/confirm", json={})
    assert resp.status_code in (400, 404, 409, 415)

def test_orders_confirm_post_success(client, app_context):
    cat = _create_category(code=_uid("hot"), name=_uid("Hot"))
    dish = _create_dish(category_id=cat.id, name=_uid("Dish"))
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id, display_name=_uid("Chef"), is_active=True)
    _create_specialty(chef_id=chef.id, dish_category_id=cat.id, priority=1)

    payload = {"customer_name": "Alice", "items": [{"dish_id": dish.id, "quantity": 2, "notes": "extra spicy"}]}
    resp = client.post("/orders/confirm", json=payload)
    assert resp.status_code == 201
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "order" in data and "assignments" in data
    assert isinstance(data["assignments"], list)
    assert len(data["assignments"]) == 1

    order_obj = data["order"]
    for k in ["id", "customer_name", "status", "confirmed_at"]:
        assert k in order_obj

    assignment = data["assignments"][0]
    for k in [
        "order_item_id",
        "dish_id",
        "dish_name",
        "dish_category",
        "chef_id",
        "chef_display_name",
        "queue_item_id",
        "position",
        "status",
    ]:
        assert k in assignment
    assert assignment["dish_id"] == dish.id
    assert assignment["chef_id"] == chef.id
    assert assignment["status"] == "queued"
    assert assignment["position"] == 1

    created_order = Order.query.filter_by(id=order_obj["id"]).first()
    assert created_order is not None
    created_items = OrderItem.query.filter_by(order_id=created_order.id).all()
    assert len(created_items) == 1
    created_queue_items = ChefQueueItem.query.filter_by(chef_id=chef.id).all()
    assert len(created_queue_items) == 1

def test_orders_confirm_post_missing_required_fields(client, app_context):
    resp = client.post("/orders/confirm", json={"items": []})
    assert resp.status_code == 400
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "error" in data

    resp2 = client.post("/orders/confirm", json={"customer_name": "Bob"})
    assert resp2.status_code == 400
    data2 = resp2.get_json()
    assert isinstance(data2, dict)
    assert "error" in data2

def test_orders_confirm_post_invalid_data(client, app_context):
    resp = client.post("/orders/confirm", json={"customer_name": "", "items": [{"dish_id": 1, "quantity": 1}]})
    assert resp.status_code == 400
    assert "error" in (resp.get_json() or {})

    resp2 = client.post("/orders/confirm", json={"customer_name": "A", "items": []})
    assert resp2.status_code == 400
    assert "error" in (resp2.get_json() or {})

    resp3 = client.post(
        "/orders/confirm",
        json={"customer_name": "A", "items": [{"dish_id": 0, "quantity": 1}]},
    )
    assert resp3.status_code == 400
    assert "error" in (resp3.get_json() or {})

    resp4 = client.post(
        "/orders/confirm",
        json={"customer_name": "A", "items": [{"dish_id": 1, "quantity": 0}]},
    )
    assert resp4.status_code == 400
    assert "error" in (resp4.get_json() or {})

    resp5 = client.post(
        "/orders/confirm",
        json={"customer_name": "A", "items": [{"dish_id": 1, "quantity": 51}]},
    )
    assert resp5.status_code == 400
    assert "error" in (resp5.get_json() or {})

    long_name = "x" * 121
    resp6 = client.post(
        "/orders/confirm",
        json={"customer_name": long_name, "items": [{"dish_id": 1, "quantity": 1}]},
    )
    assert resp6.status_code == 400
    assert "error" in (resp6.get_json() or {})

def test_orders_confirm_post_duplicate_data(client, app_context):
    cat = _create_category()
    dish = _create_dish(category_id=cat.id)
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id, is_active=True)
    _create_specialty(chef_id=chef.id, dish_category_id=cat.id, priority=1)

    payload = {"customer_name": "Dup", "items": [{"dish_id": dish.id, "quantity": 1}]}
    resp1 = client.post("/orders/confirm", json=payload)
    resp2 = client.post("/orders/confirm", json=payload)
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert Order.query.count() == 2

# ROUTE: /kitchen/queue (GET)
def test_kitchen_queue_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/kitchen/queue"]
    assert rules, "Route /kitchen/queue is missing"
    assert any("GET" in r.methods for r in rules), "Route /kitchen/queue does not accept GET"

    resp = client.get("/kitchen/queue")
    assert resp.status_code in (200, 404, 500)

def test_kitchen_queue_get_renders_template(client, app_context):
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id, display_name="A Chef", is_active=True)

    resp = client.get("/kitchen/queue")
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "generated_at" in data
    assert "chefs" in data
    assert isinstance(data["chefs"], list)
    if data["chefs"]:
        first = data["chefs"][0]
        for k in ["chef_id", "chef_display_name", "is_active", "queue"]:
            assert k in first
        assert first["chef_id"] == chef.id

# ROUTE: /chefs/<int:chef_id>/queue (GET)
def test_chefs_chef_id_queue_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/chefs/<int:chef_id>/queue"]
    assert rules, "Route /chefs/<int:chef_id>/queue is missing"
    assert any("GET" in r.methods for r in rules), "Route /chefs/<int:chef_id>/queue does not accept GET"

    resp = client.get("/chefs/1/queue")
    assert resp.status_code in (200, 404)

def test_chefs_chef_id_queue_get_renders_template(client, app_context):
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id, display_name=_uid("Chef"), is_active=True)

    resp = client.get(f"/chefs/{chef.id}/queue")
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()
    assert isinstance(data, dict)
    for k in ["chef_id", "chef_display_name", "queue"]:
        assert k in data
    assert data["chef_id"] == chef.id
    assert isinstance(data["queue"], list)

# ROUTE: /queue/items/<int:queue_item_id>/status (PATCH)
def test_queue_items_queue_item_id_status_patch_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/queue/items/<int:queue_item_id>/status"]
    assert rules, "Route /queue/items/<int:queue_item_id>/status is missing"
    assert any("PATCH" in r.methods for r in rules), "Route /queue/items/<int:queue_item_id>/status does not accept PATCH"

    resp = client.patch("/queue/items/1/status", json={})
    assert resp.status_code in (400, 404, 409)

# HELPER: classify_dish_category(dish)
def test_classify_dish_category_function_exists():
    assert callable(classify_dish_category)

def test_classify_dish_category_with_valid_input(app_context):
    cat = _create_category()
    dish = _create_dish(category_id=cat.id)
    result = classify_dish_category(dish)
    assert result is not None
    assert isinstance(result, DishCategory)
    assert result.id == cat.id

def test_classify_dish_category_with_invalid_input(app_context):
    with pytest.raises(Exception):
        classify_dish_category(None)

# HELPER: select_chef_for_category(dish_category)
def test_select_chef_for_category_function_exists():
    assert callable(select_chef_for_category)

def test_select_chef_for_category_with_valid_input(app_context):
    cat = _create_category()
    user1 = _create_user(role="chef")
    chef1 = _create_chef(user_id=user1.id, display_name="Chef1", is_active=True)
    _create_specialty(chef_id=chef1.id, dish_category_id=cat.id, priority=5)

    user2 = _create_user(role="chef")
    chef2 = _create_chef(user_id=user2.id, display_name="Chef2", is_active=True)
    _create_specialty(chef_id=chef2.id, dish_category_id=cat.id, priority=1)

    selected = select_chef_for_category(cat)
    assert selected is not None
    assert isinstance(selected, Chef)
    assert selected.id == chef2.id

def test_select_chef_for_category_with_invalid_input(app_context):
    with pytest.raises(Exception):
        select_chef_for_category(None)

# HELPER: enqueue_order_item_for_chef(chef, order_item)
def test_enqueue_order_item_for_chef_function_exists():
    assert callable(enqueue_order_item_for_chef)

def test_enqueue_order_item_for_chef_with_valid_input(app_context):
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id, is_active=True)
    cat = _create_category()
    dish = _create_dish(category_id=cat.id)
    order = _create_order()
    oi = _create_order_item(order_id=order.id, dish_id=dish.id, quantity=1)

    q1 = enqueue_order_item_for_chef(chef, oi)
    assert q1 is not None
    assert isinstance(q1, ChefQueueItem)
    assert q1.chef_id == chef.id
    assert q1.order_item_id == oi.id
    assert q1.position == 1
    assert q1.status == "queued"

    oi2 = _create_order_item(order_id=order.id, dish_id=dish.id, quantity=1)
    q2 = enqueue_order_item_for_chef(chef, oi2)
    assert q2.position == 2

def test_enqueue_order_item_for_chef_with_invalid_input(app_context):
    with pytest.raises(Exception):
        enqueue_order_item_for_chef(None, None)

# HELPER: recompute_queue_positions(chef_id)
def test_recompute_queue_positions_function_exists():
    assert callable(recompute_queue_positions)

def test_recompute_queue_positions_with_valid_input(app_context):
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id, is_active=True)
    cat = _create_category()
    dish = _create_dish(category_id=cat.id)
    order = _create_order()
    oi1 = _create_order_item(order_id=order.id, dish_id=dish.id, quantity=1)
    oi2 = _create_order_item(order_id=order.id, dish_id=dish.id, quantity=1)
    oi3 = _create_order_item(order_id=order.id, dish_id=dish.id, quantity=1)

    t1 = datetime.utcnow()
    t2 = datetime.utcnow()
    t3 = datetime.utcnow()

    q1 = _create_queue_item(chef_id=chef.id, order_item_id=oi1.id, status="queued", position=1, assigned_at=t1)
    q2 = _create_queue_item(chef_id=chef.id, order_item_id=oi2.id, status="queued", position=3, assigned_at=t2)
    q3 = _create_queue_item(chef_id=chef.id, order_item_id=oi3.id, status="in_progress", position=10, assigned_at=t3)

    recompute_queue_positions(chef.id)

    refreshed = (
        ChefQueueItem.query.filter_by(chef_id=chef.id)
        .filter(ChefQueueItem.status.in_(["queued", "in_progress"]))
        .order_by(ChefQueueItem.position.asc(), ChefQueueItem.assigned_at.asc())
        .all()
    )
    assert [x.id for x in refreshed] == [q1.id, q2.id, q3.id]
    assert [x.position for x in refreshed] == [1, 2, 3]

def test_recompute_queue_positions_with_invalid_input(app_context):
    with pytest.raises(Exception):
        recompute_queue_positions(None)

# HELPER: serialize_kitchen_queue(chefs)
def test_serialize_kitchen_queue_function_exists():
    assert callable(serialize_kitchen_queue)

def test_serialize_kitchen_queue_with_valid_input(app_context):
    user = _create_user(role="chef")
    chef = _create_chef(user_id=user.id, display_name="Chef A", is_active=True)

    cat = _create_category()
    dish = _create_dish(category_id=cat.id, name="Dish A")
    order = _create_order(customer_name="Cust A")
    oi = _create_order_item(order_id=order.id, dish_id=dish.id, quantity=2, notes=None)
    _create_queue_item(chef_id=chef.id, order_item_id=oi.id, status="queued", position=1)

    result = serialize_kitchen_queue([chef])
    assert isinstance(result, dict)
    assert "generated_at" in result
    assert "chefs" in result
    assert isinstance(result["chefs"], list)
    assert len(result["chefs"]) == 1
    chef_dict = result["chefs"][0]
    for k in ["chef_id", "chef_display_name", "is_active", "queue"]:
        assert k in chef_dict
    assert chef_dict["chef_id"] == chef.id
    assert isinstance(chef_dict["queue"], list)
    if chef_dict["queue"]:
        item = chef_dict["queue"][0]
        for k in [
            "queue_item_id",
            "position",
            "status",
            "assigned_at",
            "order_id",
            "order_item_id",
            "dish_id",
            "dish_name",
            "quantity",
            "notes",
        ]:
            assert k in item

def test_serialize_kitchen_queue_with_invalid_input(app_context):
    with pytest.raises(Exception):
        serialize_kitchen_queue(None)