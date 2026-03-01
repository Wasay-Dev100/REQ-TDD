import os
import sys
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.category import Category
from models.product import Product
from models.admin_database_management_inventory_item import InventoryItem
from models.admin_database_management_employee import Employee
from controllers.admin_database_management_controller import (
    require_admin,
    parse_bool_arg,
    serialize_product,
    serialize_category,
    serialize_inventory_item,
    serialize_employee,
)
from views.admin_database_management_views import render_admin_dashboard

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

def _create_admin_user_in_db():
    u = User(email=f"{_unique('admin')}@example.com", username=_unique("admin"), is_admin=True)
    u.set_password("AdminPass123!")
    db.session.add(u)
    db.session.commit()
    return u

def _create_non_admin_user_in_db():
    u = User(email=f"{_unique('user')}@example.com", username=_unique("user"), is_admin=False)
    u.set_password("UserPass123!")
    db.session.add(u)
    db.session.commit()
    return u

def _create_category_in_db(name=None):
    c = Category(name=name or _unique("cat"), description="desc", is_active=True)
    db.session.add(c)
    db.session.commit()
    return c

def _create_product_in_db(category_id=None, sku=None, name=None, price_cents=1234):
    p = Product(
        name=name or _unique("prod"),
        sku=sku or _unique("sku"),
        description="desc",
        price_cents=price_cents,
        is_active=True,
        category_id=category_id if category_id is not None else _create_category_in_db().id,
    )
    db.session.add(p)
    db.session.commit()
    return p

def _create_inventory_item_in_db(product_id=None, quantity_on_hand=10, reorder_level=2):
    if product_id is None:
        product_id = _create_product_in_db().id
    item = InventoryItem(
        product_id=product_id,
        quantity_on_hand=quantity_on_hand,
        reorder_level=reorder_level,
        location="A1",
        updated_at=datetime.utcnow(),
    )
    db.session.add(item)
    db.session.commit()
    return item

def _create_employee_in_db(user_id=None, employee_number=None):
    if user_id is None:
        user_id = _create_non_admin_user_in_db().id
    emp = Employee(
        user_id=user_id,
        employee_number=employee_number or _unique("empno"),
        first_name="First",
        last_name="Last",
        phone="123",
        role="Cashier",
        hourly_rate_cents=1500,
        is_active=True,
        hired_at=datetime.utcnow(),
        terminated_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(emp)
    db.session.commit()
    return emp

def _assert_route_supports_method(rule: str, method: str):
    rules = [r for r in app.url_map.iter_rules() if r.rule == rule]
    assert rules, f"Expected route {rule} to exist"
    assert any(method in r.methods for r in rules), f"Expected route {rule} to accept {method}"

# MODEL: User (models/user.py)
def test_user_model_has_required_fields():
    for field in [
        "id",
        "email",
        "username",
        "password_hash",
        "is_admin",
        "is_active",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(User, field), f"User missing required field: {field}"

def test_user_set_password(app_context):
    user = User(email=f"{_unique('u')}@example.com", username=_unique("u"))
    user.set_password("Password123!")
    assert user.password_hash
    assert user.password_hash != "Password123!"

def test_user_check_password(app_context):
    user = User(email=f"{_unique('u')}@example.com", username=_unique("u"))
    user.set_password("Password123!")
    assert user.check_password("Password123!") is True
    assert user.check_password("WrongPassword!") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")

    u1 = User(email=email, username=username)
    u1.set_password("Password123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("otheruser"))
    u2.set_password("Password123!")
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username)
    u3.set_password("Password123!")
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: Category (models/category.py)
def test_category_model_has_required_fields():
    for field in ["id", "name", "description", "is_active", "created_at", "updated_at"]:
        assert hasattr(Category, field), f"Category missing required field: {field}"

def test_category_unique_constraints(app_context):
    name = _unique("catdup")
    c1 = Category(name=name, description="d1", is_active=True)
    db.session.add(c1)
    db.session.commit()

    c2 = Category(name=name, description="d2", is_active=True)
    db.session.add(c2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: Product (models/product.py)
def test_product_model_has_required_fields():
    for field in [
        "id",
        "name",
        "sku",
        "description",
        "price_cents",
        "is_active",
        "category_id",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(Product, field), f"Product missing required field: {field}"

def test_product_unique_constraints(app_context):
    sku = _unique("skudup")
    cat = _create_category_in_db()
    p1 = Product(name=_unique("p"), sku=sku, description="d", price_cents=100, is_active=True, category_id=cat.id)
    db.session.add(p1)
    db.session.commit()

    p2 = Product(name=_unique("p"), sku=sku, description="d", price_cents=200, is_active=True, category_id=cat.id)
    db.session.add(p2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: InventoryItem (models/admin_database_management_inventory_item.py)
def test_inventoryitem_model_has_required_fields():
    for field in ["id", "product_id", "quantity_on_hand", "reorder_level", "location", "updated_at"]:
        assert hasattr(InventoryItem, field), f"InventoryItem missing required field: {field}"

def test_inventoryitem_unique_constraints(app_context):
    product = _create_product_in_db()
    i1 = InventoryItem(product_id=product.id, quantity_on_hand=1, reorder_level=0, location="A", updated_at=datetime.utcnow())
    db.session.add(i1)
    db.session.commit()

    i2 = InventoryItem(product_id=product.id, quantity_on_hand=2, reorder_level=0, location="B", updated_at=datetime.utcnow())
    db.session.add(i2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: Employee (models/admin_database_management_employee.py)
def test_employee_model_has_required_fields():
    for field in [
        "id",
        "user_id",
        "employee_number",
        "first_name",
        "last_name",
        "phone",
        "role",
        "hourly_rate_cents",
        "is_active",
        "hired_at",
        "terminated_at",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(Employee, field), f"Employee missing required field: {field}"

def test_employee_unique_constraints(app_context):
    user = _create_non_admin_user_in_db()
    empno = _unique("empno")

    e1 = Employee(
        user_id=user.id,
        employee_number=empno,
        first_name="A",
        last_name="B",
        phone=None,
        role="Role",
        hourly_rate_cents=None,
        is_active=True,
        hired_at=None,
        terminated_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(e1)
    db.session.commit()

    user2 = _create_non_admin_user_in_db()
    e2 = Employee(
        user_id=user.id,
        employee_number=_unique("empno2"),
        first_name="C",
        last_name="D",
        phone=None,
        role="Role",
        hourly_rate_cents=None,
        is_active=True,
        hired_at=None,
        terminated_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(e2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    e3 = Employee(
        user_id=user2.id,
        employee_number=empno,
        first_name="E",
        last_name="F",
        phone=None,
        role="Role",
        hourly_rate_cents=None,
        is_active=True,
        hired_at=None,
        terminated_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(e3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# ROUTE: /menu/items (GET) - list_menu_items
def test_menu_items_get_exists():
    _assert_route_supports_method("/admin/menu/items", "GET")

def test_menu_items_get_renders_template(client):
    resp = client.get("/admin/menu/items")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# ROUTE: /menu/items (POST) - create_menu_item
def test_menu_items_post_exists():
    _assert_route_supports_method("/admin/menu/items", "POST")

def test_menu_items_post_success(client, app_context):
    cat = _create_category_in_db()
    payload = {
        "name": _unique("burger"),
        "sku": _unique("sku"),
        "description": "Tasty",
        "price_cents": "999",
        "is_active": "true",
        "category_id": str(cat.id),
    }
    resp = client.post("/admin/menu/items", data=payload, follow_redirects=False)
    assert resp.status_code in (200, 201, 302)

    created = Product.query.filter_by(sku=payload["sku"]).first()
    assert created is not None
    assert created.name == payload["name"]
    assert created.category_id == cat.id

def test_menu_items_post_missing_required_fields(client, app_context):
    resp = client.post("/admin/menu/items", data={"name": _unique("x")}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)
    assert Product.query.count() == 0

def test_menu_items_post_invalid_data(client, app_context):
    cat = _create_category_in_db()
    resp = client.post(
        "/admin/menu/items",
        data={
            "name": _unique("x"),
            "sku": _unique("sku"),
            "price_cents": "not-an-int",
            "category_id": str(cat.id),
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)
    assert Product.query.filter_by(sku=None).count() == 0

def test_menu_items_post_duplicate_data(client, app_context):
    cat = _create_category_in_db()
    sku = _unique("dupsku")
    _create_product_in_db(category_id=cat.id, sku=sku)

    resp = client.post(
        "/admin/menu/items",
        data={
            "name": _unique("x"),
            "sku": sku,
            "price_cents": "100",
            "category_id": str(cat.id),
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 409, 422)
    assert Product.query.filter_by(sku=sku).count() == 1

# ROUTE: /menu/items/<int:product_id> (GET) - get_menu_item
def test_menu_items_product_id_get_exists():
    _assert_route_supports_method("/admin/menu/items/<int:product_id>", "GET")

def test_menu_items_product_id_get_renders_template(client, app_context):
    p = _create_product_in_db()
    resp = client.get(f"/admin/menu/items/{p.id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# ROUTE: /menu/items/<int:product_id> (PUT) - update_menu_item
def test_menu_items_product_id_put_exists():
    _assert_route_supports_method("/admin/menu/items/<int:product_id>", "PUT")

# ROUTE: /menu/items/<int:product_id> (DELETE) - delete_menu_item
def test_menu_items_product_id_delete_exists():
    _assert_route_supports_method("/admin/menu/items/<int:product_id>", "DELETE")

# ROUTE: /menu/categories (GET) - list_categories
def test_menu_categories_get_exists():
    _assert_route_supports_method("/admin/menu/categories", "GET")

def test_menu_categories_get_renders_template(client):
    resp = client.get("/admin/menu/categories")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# ROUTE: /menu/categories (POST) - create_category
def test_menu_categories_post_exists():
    _assert_route_supports_method("/admin/menu/categories", "POST")

def test_menu_categories_post_success(client, app_context):
    name = _unique("cat")
    resp = client.post(
        "/admin/menu/categories",
        data={"name": name, "description": "desc", "is_active": "true"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 201, 302)
    created = Category.query.filter_by(name=name).first()
    assert created is not None
    assert created.name == name

def test_menu_categories_post_missing_required_fields(client, app_context):
    resp = client.post("/admin/menu/categories", data={"description": "desc"}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)
    assert Category.query.count() == 0

def test_menu_categories_post_invalid_data(client, app_context):
    resp = client.post(
        "/admin/menu/categories",
        data={"name": _unique("cat"), "is_active": "not-a-bool"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)

def test_menu_categories_post_duplicate_data(client, app_context):
    name = _unique("catdup")
    _create_category_in_db(name=name)
    resp = client.post("/admin/menu/categories", data={"name": name}, follow_redirects=False)
    assert resp.status_code in (200, 400, 409, 422)
    assert Category.query.filter_by(name=name).count() == 1

# ROUTE: /menu/categories/<int:category_id> (GET) - get_category
def test_menu_categories_category_id_get_exists():
    _assert_route_supports_method("/admin/menu/categories/<int:category_id>", "GET")

def test_menu_categories_category_id_get_renders_template(client, app_context):
    c = _create_category_in_db()
    resp = client.get(f"/admin/menu/categories/{c.id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# ROUTE: /menu/categories/<int:category_id> (PUT) - update_category
def test_menu_categories_category_id_put_exists():
    _assert_route_supports_method("/admin/menu/categories/<int:category_id>", "PUT")

# ROUTE: /menu/categories/<int:category_id> (DELETE) - delete_category
def test_menu_categories_category_id_delete_exists():
    _assert_route_supports_method("/admin/menu/categories/<int:category_id>", "DELETE")

# ROUTE: /inventory (GET) - list_inventory
def test_inventory_get_exists():
    _assert_route_supports_method("/admin/inventory", "GET")

def test_inventory_get_renders_template(client):
    resp = client.get("/admin/inventory")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# ROUTE: /inventory (POST) - create_inventory_item
def test_inventory_post_exists():
    _assert_route_supports_method("/admin/inventory", "POST")

def test_inventory_post_success(client, app_context):
    p = _create_product_in_db()
    resp = client.post(
        "/admin/inventory",
        data={
            "product_id": str(p.id),
            "quantity_on_hand": "5",
            "reorder_level": "1",
            "location": "B2",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 201, 302)
    created = InventoryItem.query.filter_by(product_id=p.id).first()
    assert created is not None
    assert created.quantity_on_hand == 5
    assert created.reorder_level == 1
    assert created.location == "B2"

def test_inventory_post_missing_required_fields(client, app_context):
    resp = client.post("/admin/inventory", data={"quantity_on_hand": "1"}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)
    assert InventoryItem.query.count() == 0

def test_inventory_post_invalid_data(client, app_context):
    p = _create_product_in_db()
    resp = client.post(
        "/admin/inventory",
        data={"product_id": str(p.id), "quantity_on_hand": "NaN", "reorder_level": "1"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)
    assert InventoryItem.query.filter_by(product_id=p.id).first() is None

def test_inventory_post_duplicate_data(client, app_context):
    p = _create_product_in_db()
    _create_inventory_item_in_db(product_id=p.id)
    resp = client.post(
        "/admin/inventory",
        data={"product_id": str(p.id), "quantity_on_hand": "7", "reorder_level": "2"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 409, 422)
    assert InventoryItem.query.filter_by(product_id=p.id).count() == 1

# ROUTE: /inventory/<int:inventory_item_id> (GET) - get_inventory_item
def test_inventory_inventory_item_id_get_exists():
    _assert_route_supports_method("/admin/inventory/<int:inventory_item_id>", "GET")

def test_inventory_inventory_item_id_get_renders_template(client, app_context):
    item = _create_inventory_item_in_db()
    resp = client.get(f"/admin/inventory/{item.id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# ROUTE: /inventory/<int:inventory_item_id> (PUT) - update_inventory_item
def test_inventory_inventory_item_id_put_exists():
    _assert_route_supports_method("/admin/inventory/<int:inventory_item_id>", "PUT")

# ROUTE: /inventory/<int:inventory_item_id> (DELETE) - delete_inventory_item
def test_inventory_inventory_item_id_delete_exists():
    _assert_route_supports_method("/admin/inventory/<int:inventory_item_id>", "DELETE")

# ROUTE: /employees (GET) - list_employees
def test_employees_get_exists():
    _assert_route_supports_method("/admin/employees", "GET")

def test_employees_get_renders_template(client):
    resp = client.get("/admin/employees")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# ROUTE: /employees (POST) - create_employee
def test_employees_post_exists():
    _assert_route_supports_method("/admin/employees", "POST")

def test_employees_post_success(client, app_context):
    user = _create_non_admin_user_in_db()
    empno = _unique("empno")
    resp = client.post(
        "/admin/employees",
        data={
            "user_id": str(user.id),
            "employee_number": empno,
            "first_name": "Jane",
            "last_name": "Doe",
            "phone": "555",
            "role": "Manager",
            "hourly_rate_cents": "2500",
            "is_active": "true",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 201, 302)
    created = Employee.query.filter_by(employee_number=empno).first()
    assert created is not None
    assert created.user_id == user.id
    assert created.first_name == "Jane"
    assert created.last_name == "Doe"
    assert created.role == "Manager"
    assert created.hourly_rate_cents == 2500

def test_employees_post_missing_required_fields(client, app_context):
    resp = client.post("/admin/employees", data={"first_name": "Only"}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)
    assert Employee.query.count() == 0

def test_employees_post_invalid_data(client, app_context):
    user = _create_non_admin_user_in_db()
    resp = client.post(
        "/admin/employees",
        data={
            "user_id": str(user.id),
            "employee_number": _unique("empno"),
            "first_name": "A",
            "last_name": "B",
            "role": "Role",
            "hourly_rate_cents": "not-int",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)
    assert Employee.query.count() == 0

def test_employees_post_duplicate_data(client, app_context):
    emp = _create_employee_in_db()
    user2 = _create_non_admin_user_in_db()

    resp1 = client.post(
        "/admin/employees",
        data={
            "user_id": str(emp.user_id),
            "employee_number": _unique("empno"),
            "first_name": "A",
            "last_name": "B",
            "role": "Role",
        },
        follow_redirects=False,
    )
    assert resp1.status_code in (200, 400, 409, 422)

    resp2 = client.post(
        "/admin/employees",
        data={
            "user_id": str(user2.id),
            "employee_number": emp.employee_number,
            "first_name": "A",
            "last_name": "B",
            "role": "Role",
        },
        follow_redirects=False,
    )
    assert resp2.status_code in (200, 400, 409, 422)

    assert Employee.query.filter_by(user_id=emp.user_id).count() == 1
    assert Employee.query.filter_by(employee_number=emp.employee_number).count() == 1

# ROUTE: /employees/<int:employee_id> (GET) - get_employee
def test_employees_employee_id_get_exists():
    _assert_route_supports_method("/admin/employees/<int:employee_id>", "GET")

def test_employees_employee_id_get_renders_template(client, app_context):
    emp = _create_employee_in_db()
    resp = client.get(f"/admin/employees/{emp.id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# ROUTE: /employees/<int:employee_id> (PUT) - update_employee
def test_employees_employee_id_put_exists():
    _assert_route_supports_method("/admin/employees/<int:employee_id>", "PUT")

# ROUTE: /employees/<int:employee_id> (DELETE) - delete_employee
def test_employees_employee_id_delete_exists():
    _assert_route_supports_method("/admin/employees/<int:employee_id>", "DELETE")

# HELPER: require_admin(current_user: User)
def test_require_admin_function_exists():
    assert callable(require_admin)

def test_require_admin_with_valid_input(app_context):
    admin = User(email=f"{_unique('a')}@example.com", username=_unique("a"), is_admin=True)
    result = require_admin(admin)
    assert result is None or result is True

def test_require_admin_with_invalid_input(app_context):
    non_admin = User(email=f"{_unique('na')}@example.com", username=_unique("na"), is_admin=False)
    with pytest.raises(Exception):
        require_admin(non_admin)

# HELPER: parse_bool_arg(value: str|None)
def test_parse_bool_arg_function_exists():
    assert callable(parse_bool_arg)

def test_parse_bool_arg_with_valid_input():
    assert parse_bool_arg("true") is True
    assert parse_bool_arg("false") is False
    assert parse_bool_arg("1") is True
    assert parse_bool_arg("0") is False
    assert parse_bool_arg(None) is None

def test_parse_bool_arg_with_invalid_input():
    with pytest.raises(Exception):
        parse_bool_arg("notabool")

# HELPER: serialize_product(product: Product)
def test_serialize_product_function_exists():
    assert callable(serialize_product)

def test_serialize_product_with_valid_input(app_context):
    p = _create_product_in_db()
    data = serialize_product(p)
    assert isinstance(data, dict)
    assert data.get("id") == p.id
    assert data.get("name") == p.name
    assert data.get("sku") == p.sku

def test_serialize_product_with_invalid_input():
    with pytest.raises(Exception):
        serialize_product(None)

# HELPER: serialize_category(category: Category)
def test_serialize_category_function_exists():
    assert callable(serialize_category)

def test_serialize_category_with_valid_input(app_context):
    c = _create_category_in_db()
    data = serialize_category(c)
    assert isinstance(data, dict)
    assert data.get("id") == c.id
    assert data.get("name") == c.name

def test_serialize_category_with_invalid_input():
    with pytest.raises(Exception):
        serialize_category(None)

# HELPER: serialize_inventory_item(item: InventoryItem)
def test_serialize_inventory_item_function_exists():
    assert callable(serialize_inventory_item)

def test_serialize_inventory_item_with_valid_input(app_context):
    item = _create_inventory_item_in_db()
    data = serialize_inventory_item(item)
    assert isinstance(data, dict)
    assert data.get("id") == item.id
    assert data.get("product_id") == item.product_id
    assert data.get("quantity_on_hand") == item.quantity_on_hand

def test_serialize_inventory_item_with_invalid_input():
    with pytest.raises(Exception):
        serialize_inventory_item(None)

# HELPER: serialize_employee(employee: Employee)
def test_serialize_employee_function_exists():
    assert callable(serialize_employee)

def test_serialize_employee_with_valid_input(app_context):
    emp = _create_employee_in_db()
    data = serialize_employee(emp)
    assert isinstance(data, dict)
    assert data.get("id") == emp.id
    assert data.get("user_id") == emp.user_id
    assert data.get("employee_number") == emp.employee_number

def test_serialize_employee_with_invalid_input():
    with pytest.raises(Exception):
        serialize_employee(None)