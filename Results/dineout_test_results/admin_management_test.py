import os
import sys
import uuid
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db  # noqa: E402
from models.user import User  # noqa: E402
from models.product import Product  # noqa: E402
from models.admin_management_inventory_item import InventoryItem  # noqa: E402
from models.admin_management_inventory_transaction import InventoryTransaction  # noqa: E402
from controllers.admin_management_controller import (  # noqa: E402
    require_admin,
    get_request_json,
    validate_staff_payload,
    validate_menu_item_payload,
    validate_inventory_item_payload,
    validate_adjust_stock_payload,
)
from views.admin_management_views import render_admin_dashboard  # noqa: E402

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

def _create_admin_user():
    u = User(email=f"{_unique('admin')}@example.com", username=_unique("admin"), role="admin", is_active=True)
    u.set_password("AdminPass123!")
    db.session.add(u)
    db.session.commit()
    return u

def _create_staff_user(role="staff"):
    u = User(email=f"{_unique('staff')}@example.com", username=_unique("staff"), role=role, is_active=True)
    u.set_password("StaffPass123!")
    db.session.add(u)
    db.session.commit()
    return u

def _create_product():
    p = Product(
        name=_unique("product"),
        description="desc",
        price=Decimal("9.99"),
        is_available=True,
    )
    db.session.add(p)
    db.session.commit()
    return p

def _create_inventory_item():
    item = InventoryItem(
        sku=_unique("SKU"),
        name=_unique("Flour"),
        unit="kg",
        stock_quantity=10,
        reorder_level=2,
        is_active=True,
    )
    db.session.add(item)
    db.session.commit()
    return item

def _assert_has_keys(d: dict, keys: list[str]):
    assert isinstance(d, dict)
    for k in keys:
        assert k in d

def _assert_error_contract(resp_json: dict):
    _assert_has_keys(resp_json, ["error", "message"])
    assert isinstance(resp_json["error"], str)
    assert isinstance(resp_json["message"], str)

def _route_exists(rule: str, method: str) -> bool:
    for r in app.url_map.iter_rules():
        if r.rule == rule and method in r.methods:
            return True
    return False

# =========================
# MODEL: User (models/user.py)
# =========================
def test_user_model_has_required_fields(app_context):
    user = User(email=f"{_unique('e')}@example.com", username=_unique("u"), password_hash="x", role="staff")
    for field in ["id", "email", "username", "password_hash", "role", "is_active", "created_at", "updated_at"]:
        assert hasattr(user, field), field

def test_user_set_password(app_context):
    user = User(email=f"{_unique('e')}@example.com", username=_unique("u"), role="staff")
    user.set_password("Password123!")
    assert user.password_hash
    assert user.password_hash != "Password123!"

def test_user_check_password(app_context):
    user = User(email=f"{_unique('e')}@example.com", username=_unique("u"), role="staff")
    user.set_password("Password123!")
    assert user.check_password("Password123!") is True
    assert user.check_password("WrongPassword!") is False

def test_user_is_admin(app_context):
    admin = User(email=f"{_unique('e')}@example.com", username=_unique("u"), role="admin")
    staff = User(email=f"{_unique('e2')}@example.com", username=_unique("u2"), role="staff")
    assert admin.is_admin() is True
    assert staff.is_admin() is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")

    u1 = User(email=email, username=username, role="staff", is_active=True)
    u1.set_password("Password123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("otheruser"), role="staff", is_active=True)
    u2.set_password("Password123!")
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, role="staff", is_active=True)
    u3.set_password("Password123!")
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# =========================
# MODEL: Product (models/product.py)
# =========================
def test_product_model_has_required_fields(app_context):
    product = Product(name=_unique("p"), description=None, price=Decimal("1.00"), is_available=True)
    for field in ["id", "name", "description", "price", "is_available", "created_at", "updated_at"]:
        assert hasattr(product, field), field

def test_product_to_dict(app_context):
    product = Product(name=_unique("p"), description="d", price=Decimal("12.34"), is_available=False)
    db.session.add(product)
    db.session.commit()
    d = product.to_dict()
    _assert_has_keys(d, ["id", "name", "description", "price", "is_available", "created_at", "updated_at"])
    assert d["id"] == product.id
    assert d["name"] == product.name

def test_product_unique_constraints(app_context):
    name = _unique("unique_product")
    p1 = Product(name=name, description="d1", price=Decimal("1.00"), is_available=True)
    db.session.add(p1)
    db.session.commit()

    p2 = Product(name=name, description="d2", price=Decimal("2.00"), is_available=True)
    db.session.add(p2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# =========================
# MODEL: InventoryItem (models/admin_management_inventory_item.py)
# =========================
def test_inventoryitem_model_has_required_fields(app_context):
    item = InventoryItem(sku=_unique("SKU"), name=_unique("n"), unit="kg")
    for field in [
        "id",
        "sku",
        "name",
        "unit",
        "stock_quantity",
        "reorder_level",
        "is_active",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(item, field), field

def test_inventoryitem_adjust_stock(app_context):
    item = InventoryItem(sku=_unique("SKU"), name=_unique("n"), unit="kg", stock_quantity=5, reorder_level=0, is_active=True)
    db.session.add(item)
    db.session.commit()

    new_qty = item.adjust_stock(3)
    assert isinstance(new_qty, int)
    assert new_qty == 8
    assert item.stock_quantity == 8

    new_qty2 = item.adjust_stock(-2)
    assert new_qty2 == 6
    assert item.stock_quantity == 6

def test_inventoryitem_to_dict(app_context):
    item = InventoryItem(
        sku=_unique("SKU"),
        name=_unique("Sugar"),
        unit="kg",
        stock_quantity=7,
        reorder_level=1,
        is_active=False,
    )
    db.session.add(item)
    db.session.commit()
    d = item.to_dict()
    _assert_has_keys(
        d,
        [
            "id",
            "sku",
            "name",
            "unit",
            "stock_quantity",
            "reorder_level",
            "is_active",
            "created_at",
            "updated_at",
        ],
    )
    assert d["id"] == item.id
    assert d["sku"] == item.sku

def test_inventoryitem_unique_constraints(app_context):
    sku = _unique("SKU")
    i1 = InventoryItem(sku=sku, name=_unique("n1"), unit="kg", stock_quantity=0, reorder_level=0, is_active=True)
    db.session.add(i1)
    db.session.commit()

    i2 = InventoryItem(sku=sku, name=_unique("n2"), unit="kg", stock_quantity=0, reorder_level=0, is_active=True)
    db.session.add(i2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# =========================
# MODEL: InventoryTransaction (models/admin_management_inventory_transaction.py)
# =========================
def test_inventorytransaction_model_has_required_fields(app_context):
    tx = InventoryTransaction(inventory_item_id=1, admin_user_id=1, delta=1, reason=None)
    for field in ["id", "inventory_item_id", "admin_user_id", "delta", "reason", "created_at"]:
        assert hasattr(tx, field), field

def test_inventorytransaction_to_dict(app_context):
    admin = _create_admin_user()
    item = _create_inventory_item()
    tx = InventoryTransaction(inventory_item_id=item.id, admin_user_id=admin.id, delta=5, reason="restock")
    db.session.add(tx)
    db.session.commit()
    d = tx.to_dict()
    _assert_has_keys(d, ["id", "inventory_item_id", "admin_user_id", "delta", "reason", "created_at"])
    assert d["inventory_item_id"] == item.id
    assert d["admin_user_id"] == admin.id
    assert d["delta"] == 5

def test_inventorytransaction_unique_constraints(app_context):
    admin = _create_admin_user()
    item = _create_inventory_item()
    tx1 = InventoryTransaction(inventory_item_id=item.id, admin_user_id=admin.id, delta=1, reason="a")
    tx2 = InventoryTransaction(inventory_item_id=item.id, admin_user_id=admin.id, delta=1, reason="a")
    db.session.add_all([tx1, tx2])
    db.session.commit()
    assert tx1.id is not None
    assert tx2.id is not None
    assert tx1.id != tx2.id

# =========================
# ROUTE: /admin/staff (GET) - list_staff
# =========================
def test_admin_staff_get_exists(app_context):
    assert _route_exists("/admin/staff", "GET") is True

def test_admin_staff_get_renders_template(client):
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.get("/admin/staff")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# =========================
# ROUTE: /admin/staff (POST) - create_staff
# =========================
def test_admin_staff_post_exists(app_context):
    assert _route_exists("/admin/staff", "POST") is True

def test_admin_staff_post_success(client):
    payload = {
        "email": f"{_unique('s')}@example.com",
        "username": _unique("staff"),
        "password": "Password123!",
        "role": "staff",
        "is_active": True,
    }
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/staff", json=payload)
    assert resp.status_code in (200, 201)
    if resp.is_json:
        data = resp.get_json()
        if isinstance(data, dict) and "error" in data:
            pytest.fail(f"Expected success response, got error: {data}")
        if isinstance(data, dict):
            _assert_has_keys(data, ["id", "email", "username", "role", "is_active", "created_at", "updated_at"])

def test_admin_staff_post_missing_required_fields(client):
    payload = {"email": f"{_unique('s')}@example.com"}
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/staff", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        _assert_error_contract(resp.get_json())

def test_admin_staff_post_invalid_data(client):
    payload = {
        "email": "not-an-email",
        "username": "",
        "password": "",
        "role": "not_a_role",
    }
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/staff", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        _assert_error_contract(resp.get_json())

def test_admin_staff_post_duplicate_data(client):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupstaff")

    with app.app_context():
        existing = User(email=email, username=username, role="staff", is_active=True)
        existing.set_password("Password123!")
        db.session.add(existing)
        db.session.commit()

    payload = {"email": email, "username": username, "password": "Password123!", "role": "staff"}
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/staff", json=payload)
    assert resp.status_code in (400, 409, 422)
    if resp.is_json:
        _assert_error_contract(resp.get_json())

# =========================
# ROUTE: /admin/staff/<int:user_id> (GET) - get_staff
# =========================
def test_admin_staff_user_id_get_exists(app_context):
    assert _route_exists("/admin/staff/<int:user_id>", "GET") is True

def test_admin_staff_user_id_get_renders_template(client):
    with app.app_context():
        staff = _create_staff_user(role="staff")
        staff_id = staff.id

    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.get(f"/admin/staff/{staff_id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# =========================
# ROUTE: /admin/staff/<int:user_id> (PUT) - update_staff
# =========================
def test_admin_staff_user_id_put_exists(app_context):
    assert _route_exists("/admin/staff/<int:user_id>", "PUT") is True

# =========================
# ROUTE: /admin/staff/<int:user_id> (DELETE) - delete_staff
# =========================
def test_admin_staff_user_id_delete_exists(app_context):
    assert _route_exists("/admin/staff/<int:user_id>", "DELETE") is True

# =========================
# ROUTE: /admin/menu (GET) - list_menu_items
# =========================
def test_admin_menu_get_exists(app_context):
    assert _route_exists("/admin/menu", "GET") is True

def test_admin_menu_get_renders_template(client):
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.get("/admin/menu")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# =========================
# ROUTE: /admin/menu (POST) - create_menu_item
# =========================
def test_admin_menu_post_exists(app_context):
    assert _route_exists("/admin/menu", "POST") is True

def test_admin_menu_post_success(client):
    payload = {"name": _unique("MenuItem"), "price": "12.50", "description": "tasty", "is_available": True}
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/menu", json=payload)
    assert resp.status_code in (200, 201)
    if resp.is_json:
        data = resp.get_json()
        if isinstance(data, dict) and "error" in data:
            pytest.fail(f"Expected success response, got error: {data}")
        if isinstance(data, dict):
            _assert_has_keys(data, ["id", "name", "description", "price", "is_available", "created_at", "updated_at"])

def test_admin_menu_post_missing_required_fields(client):
    payload = {"description": "x"}
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/menu", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        _assert_error_contract(resp.get_json())

def test_admin_menu_post_invalid_data(client):
    payload = {"name": "", "price": "not-a-number", "is_available": "not-bool"}
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/menu", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        _assert_error_contract(resp.get_json())

def test_admin_menu_post_duplicate_data(client):
    name = _unique("DupMenu")
    with app.app_context():
        p = Product(name=name, description="d", price=Decimal("1.00"), is_available=True)
        db.session.add(p)
        db.session.commit()

    payload = {"name": name, "price": "2.00"}
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/menu", json=payload)
    assert resp.status_code in (400, 409, 422)
    if resp.is_json:
        _assert_error_contract(resp.get_json())

# =========================
# ROUTE: /admin/menu/<int:product_id> (GET) - get_menu_item
# =========================
def test_admin_menu_product_id_get_exists(app_context):
    assert _route_exists("/admin/menu/<int:product_id>", "GET") is True

def test_admin_menu_product_id_get_renders_template(client):
    with app.app_context():
        p = _create_product()
        pid = p.id

    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.get(f"/admin/menu/{pid}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# =========================
# ROUTE: /admin/menu/<int:product_id> (PUT) - update_menu_item
# =========================
def test_admin_menu_product_id_put_exists(app_context):
    assert _route_exists("/admin/menu/<int:product_id>", "PUT") is True

# =========================
# ROUTE: /admin/menu/<int:product_id> (DELETE) - delete_menu_item
# =========================
def test_admin_menu_product_id_delete_exists(app_context):
    assert _route_exists("/admin/menu/<int:product_id>", "DELETE") is True

# =========================
# ROUTE: /admin/inventory (GET) - list_inventory_items
# =========================
def test_admin_inventory_get_exists(app_context):
    assert _route_exists("/admin/inventory", "GET") is True

def test_admin_inventory_get_renders_template(client):
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.get("/admin/inventory")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# =========================
# ROUTE: /admin/inventory (POST) - create_inventory_item
# =========================
def test_admin_inventory_post_exists(app_context):
    assert _route_exists("/admin/inventory", "POST") is True

def test_admin_inventory_post_success(client):
    payload = {
        "sku": _unique("SKU"),
        "name": _unique("Rice"),
        "unit": "kg",
        "stock_quantity": 5,
        "reorder_level": 1,
        "is_active": True,
    }
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/inventory", json=payload)
    assert resp.status_code in (200, 201)
    if resp.is_json:
        data = resp.get_json()
        if isinstance(data, dict) and "error" in data:
            pytest.fail(f"Expected success response, got error: {data}")
        if isinstance(data, dict):
            _assert_has_keys(
                data,
                [
                    "id",
                    "sku",
                    "name",
                    "unit",
                    "stock_quantity",
                    "reorder_level",
                    "is_active",
                    "created_at",
                    "updated_at",
                ],
            )

def test_admin_inventory_post_missing_required_fields(client):
    payload = {"sku": _unique("SKU")}
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/inventory", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        _assert_error_contract(resp.get_json())

def test_admin_inventory_post_invalid_data(client):
    payload = {"sku": "", "name": "", "unit": "", "stock_quantity": "NaN", "reorder_level": "NaN"}
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/inventory", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        _assert_error_contract(resp.get_json())

def test_admin_inventory_post_duplicate_data(client):
    sku = _unique("SKU")
    with app.app_context():
        item = InventoryItem(sku=sku, name=_unique("n"), unit="kg", stock_quantity=0, reorder_level=0, is_active=True)
        db.session.add(item)
        db.session.commit()

    payload = {"sku": sku, "name": _unique("n2"), "unit": "kg"}
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post("/admin/inventory", json=payload)
    assert resp.status_code in (400, 409, 422)
    if resp.is_json:
        _assert_error_contract(resp.get_json())

# =========================
# ROUTE: /admin/inventory/<int:item_id> (GET) - get_inventory_item
# =========================
def test_admin_inventory_item_id_get_exists(app_context):
    assert _route_exists("/admin/inventory/<int:item_id>", "GET") is True

def test_admin_inventory_item_id_get_renders_template(client):
    with app.app_context():
        item = _create_inventory_item()
        item_id = item.id

    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.get(f"/admin/inventory/{item_id}")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/json")

# =========================
# ROUTE: /admin/inventory/<int:item_id> (PUT) - update_inventory_item
# =========================
def test_admin_inventory_item_id_put_exists(app_context):
    assert _route_exists("/admin/inventory/<int:item_id>", "PUT") is True

# =========================
# ROUTE: /admin/inventory/<int:item_id> (DELETE) - delete_inventory_item
# =========================
def test_admin_inventory_item_id_delete_exists(app_context):
    assert _route_exists("/admin/inventory/<int:item_id>", "DELETE") is True

# =========================
# ROUTE: /admin/inventory/<int:item_id>/adjust (POST) - adjust_inventory_stock
# =========================
def test_admin_inventory_item_id_adjust_post_exists(app_context):
    assert _route_exists("/admin/inventory/<int:item_id>/adjust", "POST") is True

def test_admin_inventory_item_id_adjust_post_success(client):
    with app.app_context():
        admin = _create_admin_user()
        item = _create_inventory_item()
        item_id = item.id
        admin_id = admin.id

    payload = {"delta": 3, "reason": "restock"}
    with patch("services.auth.get_current_user", return_value=MagicMock(id=admin_id, is_admin=lambda: True)):
        resp = client.post(f"/admin/inventory/{item_id}/adjust", json=payload)
    assert resp.status_code in (200, 201)
    if resp.is_json:
        data = resp.get_json()
        if isinstance(data, dict) and "error" in data:
            pytest.fail(f"Expected success response, got error: {data}")

def test_admin_inventory_item_id_adjust_post_missing_required_fields(client):
    with app.app_context():
        _create_admin_user()
        item = _create_inventory_item()
        item_id = item.id

    payload = {"reason": "oops"}
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post(f"/admin/inventory/{item_id}/adjust", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        _assert_error_contract(resp.get_json())

def test_admin_inventory_item_id_adjust_post_invalid_data(client):
    with app.app_context():
        _create_admin_user()
        item = _create_inventory_item()
        item_id = item.id

    payload = {"delta": "NaN", "reason": 123}
    with patch("services.auth.get_current_user", return_value=MagicMock(is_admin=lambda: True)):
        resp = client.post(f"/admin/inventory/{item_id}/adjust", json=payload)
    assert resp.status_code in (400, 422)
    if resp.is_json:
        _assert_error_contract(resp.get_json())

def test_admin_inventory_item_id_adjust_post_duplicate_data(client):
    with app.app_context():
        admin = _create_admin_user()
        item = _create_inventory_item()
        item_id = item.id
        admin_id = admin.id

    payload = {"delta": 1, "reason": "cyclecount"}
    with patch("services.auth.get_current_user", return_value=MagicMock(id=admin_id, is_admin=lambda: True)):
        resp1 = client.post(f"/admin/inventory/{item_id}/adjust", json=payload)
        resp2 = client.post(f"/admin/inventory/{item_id}/adjust", json=payload)

    assert resp1.status_code in (200, 201)
    assert resp2.status_code in (200, 201, 409)
    if resp2.status_code == 409 and resp2.is_json:
        _assert_error_contract(resp2.get_json())

# =========================
# HELPER: require_admin(user: User)
# =========================
def test_require_admin_function_exists():
    assert callable(require_admin)

def test_require_admin_with_valid_input(app_context):
    admin = User(email=f"{_unique('a')}@example.com", username=_unique("a"), role="admin", is_active=True)
    admin.set_password("Password123!")
    result = require_admin(admin)
    assert result is None or result is True

def test_require_admin_with_invalid_input(app_context):
    staff = User(email=f"{_unique('s')}@example.com", username=_unique("s"), role="staff", is_active=True)
    staff.set_password("Password123!")
    with pytest.raises(Exception):
        require_admin(staff)

# =========================
# HELPER: get_request_json()
# =========================
def test_get_request_json_function_exists():
    assert callable(get_request_json)

def test_get_request_json_with_valid_input(app_context):
    with app.test_request_context("/admin/staff", method="POST", json={"a": 1}):
        data = get_request_json()
    assert isinstance(data, dict)
    assert data.get("a") == 1

def test_get_request_json_with_invalid_input(app_context):
    with app.test_request_context("/admin/staff", method="POST", data="not-json", content_type="text/plain"):
        with pytest.raises(Exception):
            get_request_json()

# =========================
# HELPER: validate_staff_payload(payload: dict, partial: bool)
# =========================
def test_validate_staff_payload_function_exists():
    assert callable(validate_staff_payload)

def test_validate_staff_payload_with_valid_input():
    payload = {"email": "user@example.com", "username": "user1", "password": "Password123!", "role": "staff", "is_active": True}
    out = validate_staff_payload(payload, partial=False)
    assert isinstance(out, dict)
    for k in ["email", "username", "password", "role"]:
        assert k in out

def test_validate_staff_payload_with_invalid_input():
    payload = {"email": "bad", "username": "", "password": "", "role": "nope"}
    with pytest.raises(Exception):
        validate_staff_payload(payload, partial=False)

# =========================
# HELPER: validate_menu_item_payload(payload: dict, partial: bool)
# =========================
def test_validate_menu_item_payload_function_exists():
    assert callable(validate_menu_item_payload)

def test_validate_menu_item_payload_with_valid_input():
    payload = {"name": "Burger", "price": "10.00", "description": "x", "is_available": True}
    out = validate_menu_item_payload(payload, partial=False)
    assert isinstance(out, dict)
    for k in ["name", "price"]:
        assert k in out

def test_validate_menu_item_payload_with_invalid_input():
    payload = {"name": "", "price": "NaN", "is_available": "no"}
    with pytest.raises(Exception):
        validate_menu_item_payload(payload, partial=False)

# =========================
# HELPER: validate_inventory_item_payload(payload: dict, partial: bool)
# =========================
def test_validate_inventory_item_payload_function_exists():
    assert callable(validate_inventory_item_payload)

def test_validate_inventory_item_payload_with_valid_input():
    payload = {"sku": "SKU123", "name": "Flour", "unit": "kg", "stock_quantity": 0, "reorder_level": 0, "is_active": True}
    out = validate_inventory_item_payload(payload, partial=False)
    assert isinstance(out, dict)
    for k in ["sku", "name", "unit"]:
        assert k in out

def test_validate_inventory_item_payload_with_invalid_input():
    payload = {"sku": "", "name": "", "unit": "", "stock_quantity": "NaN"}
    with pytest.raises(Exception):
        validate_inventory_item_payload(payload, partial=False)

# =========================
# HELPER: validate_adjust_stock_payload(payload: dict)
# =========================
def test_validate_adjust_stock_payload_function_exists():
    assert callable(validate_adjust_stock_payload)

def test_validate_adjust_stock_payload_with_valid_input():
    payload = {"delta": 5, "reason": "restock"}
    out = validate_adjust_stock_payload(payload)
    assert isinstance(out, dict)
    assert "delta" in out
    assert out["delta"] == 5

def test_validate_adjust_stock_payload_with_invalid_input():
    payload = {"delta": "NaN"}
    with pytest.raises(Exception):
        validate_adjust_stock_payload(payload)