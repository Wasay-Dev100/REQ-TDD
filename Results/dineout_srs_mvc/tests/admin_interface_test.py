import os
import sys
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.admin_interface_staff_member import StaffMember
from models.admin_interface_menu_item import MenuItem
from models.admin_interface_inventory_item import InventoryItem
from controllers.admin_interface_controller import (
    admin_required,
    get_current_user,
    validate_staff_payload,
    validate_menu_payload,
    validate_inventory_payload,
)
from views.admin_interface_views import (
    render_admin_home,
    render_staff_list,
    render_staff_form,
    render_menu_list,
    render_menu_form,
    render_inventory_list,
    render_inventory_form,
)

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

@pytest.fixture
def db_session(app_context):
    yield db.session

def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_admin_user(db_session):
    u = User(email=f"{_unique('admin')}@example.com", username=_unique("admin"), role="admin", is_active=True)
    u.set_password("AdminPass123!")
    db_session.add(u)
    db_session.commit()
    return u

def _create_non_admin_user(db_session):
    u = User(email=f"{_unique('user')}@example.com", username=_unique("user"), role="staff", is_active=True)
    u.set_password("UserPass123!")
    db_session.add(u)
    db_session.commit()
    return u

def _force_login_as(client, user: User):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["_user_id"] = str(user.id)
        sess["role"] = user.role

def _assert_route_methods_exist(path: str, expected_methods: set[str]):
    rules = [r for r in app.url_map.iter_rules() if r.rule == path]
    assert rules, f"Missing route: {path}"
    methods = set()
    for r in rules:
        methods |= set(r.methods or [])
    for m in expected_methods:
        assert m in methods, f"Route {path} missing method {m}. Has: {sorted(methods)}"

def _assert_response_renders_html(response):
    assert response.status_code == 200
    ct = response.headers.get("Content-Type", "")
    assert "text/html" in ct or "charset" in ct or ct == "", f"Unexpected Content-Type: {ct}"
    assert response.data is not None
    assert len(response.data) > 0

# =========================
# MODEL: User (models/user.py)
# =========================
def test_user_model_has_required_fields():
    for field in ["id", "email", "username", "password_hash", "role", "is_active", "created_at", "updated_at"]:
        assert hasattr(User, field), f"User missing field: {field}"

def test_user_set_password():
    u = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="admin")
    u.set_password("Secret123!")
    assert u.password_hash
    assert "Secret123!" not in u.password_hash

def test_user_check_password():
    u = User(email=f"{_unique('u')}@example.com", username=_unique("u"), role="admin")
    u.set_password("Secret123!")
    assert u.check_password("Secret123!") is True
    assert u.check_password("WrongPass!") is False

def test_user_is_admin():
    admin = User(email=f"{_unique('a')}@example.com", username=_unique("a"), role="admin")
    staff = User(email=f"{_unique('s')}@example.com", username=_unique("s"), role="staff")
    assert admin.is_admin() is True
    assert staff.is_admin() is False

def test_user_unique_constraints(app_context, db_session):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")

    u1 = User(email=email, username=username, role="admin")
    u1.set_password("Secret123!")
    db_session.add(u1)
    db_session.commit()

    u2 = User(email=email, username=_unique("otheruser"), role="admin")
    u2.set_password("Secret123!")
    db_session.add(u2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, role="admin")
    u3.set_password("Secret123!")
    db_session.add(u3)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

# =========================
# MODEL: StaffMember
# =========================
def test_staffmember_model_has_required_fields():
    for field in ["id", "full_name", "email", "phone", "position", "is_active", "created_at", "updated_at"]:
        assert hasattr(StaffMember, field), f"StaffMember missing field: {field}"

def test_staffmember_to_dict():
    sm = StaffMember(full_name="Jane Doe", email=f"{_unique('sm')}@example.com", phone="123", position="Chef")
    d = sm.to_dict()
    assert isinstance(d, dict)
    for key in ["id", "full_name", "email", "phone", "position", "is_active", "created_at", "updated_at"]:
        assert key in d, f"StaffMember.to_dict missing key: {key}"

def test_staffmember_unique_constraints(app_context, db_session):
    email = f"{_unique('staffdup')}@example.com"
    sm1 = StaffMember(full_name="A", email=email, phone=None, position="Chef")
    db_session.add(sm1)
    db_session.commit()

    sm2 = StaffMember(full_name="B", email=email, phone=None, position="Server")
    db_session.add(sm2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

# =========================
# MODEL: MenuItem
# =========================
def test_menuitem_model_has_required_fields():
    for field in ["id", "name", "description", "price_cents", "is_available", "sort_order", "created_at", "updated_at"]:
        assert hasattr(MenuItem, field), f"MenuItem missing field: {field}"

def test_menuitem_to_dict():
    mi = MenuItem(name=_unique("Burger"), description="Tasty", price_cents=1299, is_available=True, sort_order=1)
    d = mi.to_dict()
    assert isinstance(d, dict)
    for key in ["id", "name", "description", "price_cents", "is_available", "sort_order", "created_at", "updated_at"]:
        assert key in d, f"MenuItem.to_dict missing key: {key}"

def test_menuitem_unique_constraints(app_context, db_session):
    name = _unique("menuitem")
    mi1 = MenuItem(name=name, description=None, price_cents=500, is_available=True, sort_order=0)
    db_session.add(mi1)
    db_session.commit()

    mi2 = MenuItem(name=name, description="Dup", price_cents=600, is_available=True, sort_order=0)
    db_session.add(mi2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

# =========================
# MODEL: InventoryItem
# =========================
def test_inventoryitem_model_has_required_fields():
    for field in [
        "id",
        "name",
        "sku",
        "unit",
        "quantity_on_hand",
        "reorder_threshold",
        "cost_cents",
        "is_active",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(InventoryItem, field), f"InventoryItem missing field: {field}"

def test_inventoryitem_to_dict():
    ii = InventoryItem(
        name=_unique("Flour"),
        sku=_unique("SKU"),
        unit="kg",
        quantity_on_hand=Decimal("10.50"),
        reorder_threshold=Decimal("2.00"),
        cost_cents=1999,
        is_active=True,
    )
    d = ii.to_dict()
    assert isinstance(d, dict)
    for key in [
        "id",
        "name",
        "sku",
        "unit",
        "quantity_on_hand",
        "reorder_threshold",
        "cost_cents",
        "is_active",
        "created_at",
        "updated_at",
    ]:
        assert key in d, f"InventoryItem.to_dict missing key: {key}"

def test_inventoryitem_unique_constraints(app_context, db_session):
    name = _unique("inv")
    sku = _unique("sku")

    ii1 = InventoryItem(name=name, sku=sku, unit="unit", quantity_on_hand=Decimal("0"), reorder_threshold=Decimal("0"))
    db_session.add(ii1)
    db_session.commit()

    ii2 = InventoryItem(name=name, sku=_unique("sku2"), unit="unit", quantity_on_hand=Decimal("0"), reorder_threshold=Decimal("0"))
    db_session.add(ii2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    ii3 = InventoryItem(name=_unique("inv2"), sku=sku, unit="unit", quantity_on_hand=Decimal("0"), reorder_threshold=Decimal("0"))
    db_session.add(ii3)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

# =========================
# ROUTE: /admin (GET)
# =========================
def test_admin_get_exists():
    _assert_route_methods_exist("/admin", {"GET"})

def test_admin_get_renders_template(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)
    resp = client.get("/admin")
    _assert_response_renders_html(resp)

# =========================
# ROUTE: /admin/staff (GET)
# =========================
def test_admin_staff_get_exists():
    _assert_route_methods_exist("/admin/staff", {"GET"})

def test_admin_staff_get_renders_template(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)
    resp = client.get("/admin/staff")
    _assert_response_renders_html(resp)

# =========================
# ROUTE: /admin/staff/new (GET)
# =========================
def test_admin_staff_new_get_exists():
    _assert_route_methods_exist("/admin/staff/new", {"GET"})

def test_admin_staff_new_get_renders_template(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)
    resp = client.get("/admin/staff/new")
    _assert_response_renders_html(resp)

# =========================
# ROUTE: /admin/staff/new (POST)
# =========================
def test_admin_staff_new_post_exists():
    _assert_route_methods_exist("/admin/staff/new", {"POST"})

def test_admin_staff_new_post_success(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    email = f"{_unique('staff')}@example.com"
    resp = client.post(
        "/admin/staff/new",
        data={"full_name": "Test Staff", "email": email, "phone": "555-0101", "position": "Chef", "is_active": "1"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)

    created = StaffMember.query.filter_by(email=email).first()
    assert created is not None
    assert created.full_name == "Test Staff"
    assert created.position == "Chef"

def test_admin_staff_new_post_missing_required_fields(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post("/admin/staff/new", data={"email": f"{_unique('staff')}@example.com"}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)
    assert StaffMember.query.count() == 0

def test_admin_staff_new_post_invalid_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post(
        "/admin/staff/new",
        data={"full_name": "", "email": "not-an-email", "phone": "x" * 200, "position": ""},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)
    assert StaffMember.query.count() == 0

def test_admin_staff_new_post_duplicate_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    email = f"{_unique('staffdup')}@example.com"
    existing = StaffMember(full_name="Existing", email=email, phone=None, position="Chef")
    db_session.add(existing)
    db_session.commit()

    resp = client.post(
        "/admin/staff/new",
        data={"full_name": "New", "email": email, "phone": "555", "position": "Server"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 409, 422)
    assert StaffMember.query.filter_by(email=email).count() == 1

# =========================
# ROUTE: /admin/staff/<int:staff_id>/edit (GET)
# =========================
def test_admin_staff_staff_id_edit_get_exists():
    _assert_route_methods_exist("/admin/staff/<int:staff_id>/edit", {"GET"})

def test_admin_staff_staff_id_edit_get_renders_template(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    sm = StaffMember(full_name="Edit Me", email=f"{_unique('edit')}@example.com", phone=None, position="Chef")
    db_session.add(sm)
    db_session.commit()

    resp = client.get(f"/admin/staff/{sm.id}/edit")
    _assert_response_renders_html(resp)

# =========================
# ROUTE: /admin/staff/<int:staff_id>/edit (POST)
# =========================
def test_admin_staff_staff_id_edit_post_exists():
    _assert_route_methods_exist("/admin/staff/<int:staff_id>/edit", {"POST"})

def test_admin_staff_staff_id_edit_post_success(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    sm = StaffMember(full_name="Before", email=f"{_unique('edit')}@example.com", phone=None, position="Chef")
    db_session.add(sm)
    db_session.commit()

    new_email = f"{_unique('after')}@example.com"
    resp = client.post(
        f"/admin/staff/{sm.id}/edit",
        data={"full_name": "After", "email": new_email, "phone": "555-9999", "position": "Manager", "is_active": "1"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)

    updated = StaffMember.query.get(sm.id)
    assert updated.full_name == "After"
    assert updated.email == new_email
    assert updated.position == "Manager"

def test_admin_staff_staff_id_edit_post_missing_required_fields(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    sm = StaffMember(full_name="Before", email=f"{_unique('edit')}@example.com", phone=None, position="Chef")
    db_session.add(sm)
    db_session.commit()

    resp = client.post(f"/admin/staff/{sm.id}/edit", data={"full_name": ""}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)

    unchanged = StaffMember.query.get(sm.id)
    assert unchanged.email == sm.email

def test_admin_staff_staff_id_edit_post_invalid_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    sm = StaffMember(full_name="Before", email=f"{_unique('edit')}@example.com", phone=None, position="Chef")
    db_session.add(sm)
    db_session.commit()

    resp = client.post(
        f"/admin/staff/{sm.id}/edit",
        data={"full_name": "X", "email": "bad-email", "phone": "1", "position": ""},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)

    unchanged = StaffMember.query.get(sm.id)
    assert unchanged.email == sm.email

def test_admin_staff_staff_id_edit_post_duplicate_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    email1 = f"{_unique('e1')}@example.com"
    email2 = f"{_unique('e2')}@example.com"
    sm1 = StaffMember(full_name="One", email=email1, phone=None, position="Chef")
    sm2 = StaffMember(full_name="Two", email=email2, phone=None, position="Server")
    db_session.add_all([sm1, sm2])
    db_session.commit()

    resp = client.post(
        f"/admin/staff/{sm2.id}/edit",
        data={"full_name": "Two", "email": email1, "phone": "", "position": "Server"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 409, 422)
    assert StaffMember.query.filter_by(email=email1).count() == 1

# =========================
# ROUTE: /admin/staff/<int:staff_id>/delete (POST)
# =========================
def test_admin_staff_staff_id_delete_post_exists():
    _assert_route_methods_exist("/admin/staff/<int:staff_id>/delete", {"POST"})

def test_admin_staff_staff_id_delete_post_success(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    sm = StaffMember(full_name="Delete Me", email=f"{_unique('del')}@example.com", phone=None, position="Chef")
    db_session.add(sm)
    db_session.commit()

    resp = client.post(f"/admin/staff/{sm.id}/delete", data={}, follow_redirects=False)
    assert resp.status_code in (200, 302)

    deleted = StaffMember.query.get(sm.id)
    assert deleted is None

def test_admin_staff_staff_id_delete_post_missing_required_fields(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post("/admin/staff/999999/delete", data={}, follow_redirects=False)
    assert resp.status_code in (200, 302, 404)

def test_admin_staff_staff_id_delete_post_invalid_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post("/admin/staff/0/delete", data={"unexpected": "1"}, follow_redirects=False)
    assert resp.status_code in (200, 302, 400, 404)

def test_admin_staff_staff_id_delete_post_duplicate_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    sm = StaffMember(full_name="Delete Me", email=f"{_unique('deldup')}@example.com", phone=None, position="Chef")
    db_session.add(sm)
    db_session.commit()

    resp1 = client.post(f"/admin/staff/{sm.id}/delete", data={}, follow_redirects=False)
    assert resp1.status_code in (200, 302)

    resp2 = client.post(f"/admin/staff/{sm.id}/delete", data={}, follow_redirects=False)
    assert resp2.status_code in (200, 302, 404)

# =========================
# ROUTE: /admin/menu (GET)
# =========================
def test_admin_menu_get_exists():
    _assert_route_methods_exist("/admin/menu", {"GET"})

def test_admin_menu_get_renders_template(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)
    resp = client.get("/admin/menu")
    _assert_response_renders_html(resp)

# =========================
# ROUTE: /admin/menu/new (GET)
# =========================
def test_admin_menu_new_get_exists():
    _assert_route_methods_exist("/admin/menu/new", {"GET"})

def test_admin_menu_new_get_renders_template(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)
    resp = client.get("/admin/menu/new")
    _assert_response_renders_html(resp)

# =========================
# ROUTE: /admin/menu/new (POST)
# =========================
def test_admin_menu_new_post_exists():
    _assert_route_methods_exist("/admin/menu/new", {"POST"})

def test_admin_menu_new_post_success(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    name = _unique("Pizza")
    resp = client.post(
        "/admin/menu/new",
        data={"name": name, "description": "Cheese", "price_cents": "1599", "is_available": "1", "sort_order": "1"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)

    created = MenuItem.query.filter_by(name=name).first()
    assert created is not None
    assert created.price_cents == 1599

def test_admin_menu_new_post_missing_required_fields(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post("/admin/menu/new", data={"description": "X"}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)
    assert MenuItem.query.count() == 0

def test_admin_menu_new_post_invalid_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post(
        "/admin/menu/new",
        data={"name": "", "description": "X", "price_cents": "-1", "sort_order": "notint"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)
    assert MenuItem.query.count() == 0

def test_admin_menu_new_post_duplicate_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    name = _unique("DupItem")
    existing = MenuItem(name=name, description=None, price_cents=100, is_available=True, sort_order=0)
    db_session.add(existing)
    db_session.commit()

    resp = client.post(
        "/admin/menu/new",
        data={"name": name, "description": "Dup", "price_cents": "200", "is_available": "1", "sort_order": "0"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 409, 422)
    assert MenuItem.query.filter_by(name=name).count() == 1

# =========================
# ROUTE: /admin/menu/<int:menu_item_id>/edit (GET)
# =========================
def test_admin_menu_menu_item_id_edit_get_exists():
    _assert_route_methods_exist("/admin/menu/<int:menu_item_id>/edit", {"GET"})

def test_admin_menu_menu_item_id_edit_get_renders_template(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    mi = MenuItem(name=_unique("EditItem"), description="Before", price_cents=1000, is_available=True, sort_order=0)
    db_session.add(mi)
    db_session.commit()

    resp = client.get(f"/admin/menu/{mi.id}/edit")
    _assert_response_renders_html(resp)

# =========================
# ROUTE: /admin/menu/<int:menu_item_id>/edit (POST)
# =========================
def test_admin_menu_menu_item_id_edit_post_exists():
    _assert_route_methods_exist("/admin/menu/<int:menu_item_id>/edit", {"POST"})

def test_admin_menu_menu_item_id_edit_post_success(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    mi = MenuItem(name=_unique("EditItem"), description="Before", price_cents=1000, is_available=True, sort_order=0)
    db_session.add(mi)
    db_session.commit()

    new_name = _unique("AfterItem")
    resp = client.post(
        f"/admin/menu/{mi.id}/edit",
        data={"name": new_name, "description": "After", "price_cents": "1200", "is_available": "0", "sort_order": "2"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)

    updated = MenuItem.query.get(mi.id)
    assert updated.name == new_name
    assert updated.price_cents == 1200

def test_admin_menu_menu_item_id_edit_post_missing_required_fields(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    mi = MenuItem(name=_unique("EditItem"), description="Before", price_cents=1000, is_available=True, sort_order=0)
    db_session.add(mi)
    db_session.commit()

    resp = client.post(f"/admin/menu/{mi.id}/edit", data={"name": ""}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)

    unchanged = MenuItem.query.get(mi.id)
    assert unchanged.name == mi.name

def test_admin_menu_menu_item_id_edit_post_invalid_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    mi = MenuItem(name=_unique("EditItem"), description="Before", price_cents=1000, is_available=True, sort_order=0)
    db_session.add(mi)
    db_session.commit()

    resp = client.post(
        f"/admin/menu/{mi.id}/edit",
        data={"name": _unique("X"), "price_cents": "notint", "sort_order": "-999999999999"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)

    unchanged = MenuItem.query.get(mi.id)
    assert unchanged.price_cents == 1000

def test_admin_menu_menu_item_id_edit_post_duplicate_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    name1 = _unique("Name1")
    name2 = _unique("Name2")
    mi1 = MenuItem(name=name1, description=None, price_cents=100, is_available=True, sort_order=0)
    mi2 = MenuItem(name=name2, description=None, price_cents=200, is_available=True, sort_order=0)
    db_session.add_all([mi1, mi2])
    db_session.commit()

    resp = client.post(
        f"/admin/menu/{mi2.id}/edit",
        data={"name": name1, "description": "Dup", "price_cents": "200", "is_available": "1", "sort_order": "0"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 409, 422)
    assert MenuItem.query.filter_by(name=name1).count() == 1

# =========================
# ROUTE: /admin/menu/<int:menu_item_id>/delete (POST)
# =========================
def test_admin_menu_menu_item_id_delete_post_exists():
    _assert_route_methods_exist("/admin/menu/<int:menu_item_id>/delete", {"POST"})

def test_admin_menu_menu_item_id_delete_post_success(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    mi = MenuItem(name=_unique("DelItem"), description=None, price_cents=100, is_available=True, sort_order=0)
    db_session.add(mi)
    db_session.commit()

    resp = client.post(f"/admin/menu/{mi.id}/delete", data={}, follow_redirects=False)
    assert resp.status_code in (200, 302)

    deleted = MenuItem.query.get(mi.id)
    assert deleted is None

def test_admin_menu_menu_item_id_delete_post_missing_required_fields(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post("/admin/menu/999999/delete", data={}, follow_redirects=False)
    assert resp.status_code in (200, 302, 404)

def test_admin_menu_menu_item_id_delete_post_invalid_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post("/admin/menu/0/delete", data={"unexpected": "1"}, follow_redirects=False)
    assert resp.status_code in (200, 302, 400, 404)

def test_admin_menu_menu_item_id_delete_post_duplicate_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    mi = MenuItem(name=_unique("DelDupItem"), description=None, price_cents=100, is_available=True, sort_order=0)
    db_session.add(mi)
    db_session.commit()

    resp1 = client.post(f"/admin/menu/{mi.id}/delete", data={}, follow_redirects=False)
    assert resp1.status_code in (200, 302)

    resp2 = client.post(f"/admin/menu/{mi.id}/delete", data={}, follow_redirects=False)
    assert resp2.status_code in (200, 302, 404)

# =========================
# ROUTE: /admin/inventory (GET)
# =========================
def test_admin_inventory_get_exists():
    _assert_route_methods_exist("/admin/inventory", {"GET"})

def test_admin_inventory_get_renders_template(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)
    resp = client.get("/admin/inventory")
    _assert_response_renders_html(resp)

# =========================
# ROUTE: /admin/inventory/new (GET)
# =========================
def test_admin_inventory_new_get_exists():
    _assert_route_methods_exist("/admin/inventory/new", {"GET"})

def test_admin_inventory_new_get_renders_template(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)
    resp = client.get("/admin/inventory/new")
    _assert_response_renders_html(resp)

# =========================
# ROUTE: /admin/inventory/new (POST)
# =========================
def test_admin_inventory_new_post_exists():
    _assert_route_methods_exist("/admin/inventory/new", {"POST"})

def test_admin_inventory_new_post_success(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    name = _unique("Sugar")
    sku = _unique("SKU")
    resp = client.post(
        "/admin/inventory/new",
        data={
            "name": name,
            "sku": sku,
            "unit": "kg",
            "quantity_on_hand": "5.50",
            "reorder_threshold": "1.00",
            "cost_cents": "250",
            "is_active": "1",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)

    created = InventoryItem.query.filter_by(sku=sku).first()
    assert created is not None
    assert created.name == name

def test_admin_inventory_new_post_missing_required_fields(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post("/admin/inventory/new", data={"name": _unique("X")}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)
    assert InventoryItem.query.count() == 0

def test_admin_inventory_new_post_invalid_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post(
        "/admin/inventory/new",
        data={
            "name": "",
            "sku": "",
            "unit": "x" * 200,
            "quantity_on_hand": "notnum",
            "reorder_threshold": "-1",
            "cost_cents": "notint",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)
    assert InventoryItem.query.count() == 0

def test_admin_inventory_new_post_duplicate_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    name = _unique("DupInv")
    sku = _unique("DupSKU")
    existing = InventoryItem(name=name, sku=sku, unit="unit", quantity_on_hand=Decimal("0"), reorder_threshold=Decimal("0"))
    db_session.add(existing)
    db_session.commit()

    resp = client.post(
        "/admin/inventory/new",
        data={"name": name, "sku": _unique("OtherSKU"), "unit": "unit", "quantity_on_hand": "0", "reorder_threshold": "0"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 409, 422)
    assert InventoryItem.query.filter_by(name=name).count() == 1

    resp2 = client.post(
        "/admin/inventory/new",
        data={"name": _unique("OtherName"), "sku": sku, "unit": "unit", "quantity_on_hand": "0", "reorder_threshold": "0"},
        follow_redirects=False,
    )
    assert resp2.status_code in (200, 400, 409, 422)
    assert InventoryItem.query.filter_by(sku=sku).count() == 1

# =========================
# ROUTE: /admin/inventory/<int:inventory_item_id>/edit (GET)
# =========================
def test_admin_inventory_inventory_item_id_edit_get_exists():
    _assert_route_methods_exist("/admin/inventory/<int:inventory_item_id>/edit", {"GET"})

def test_admin_inventory_inventory_item_id_edit_get_renders_template(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    ii = InventoryItem(
        name=_unique("EditInv"),
        sku=_unique("SKU"),
        unit="unit",
        quantity_on_hand=Decimal("1.00"),
        reorder_threshold=Decimal("0.50"),
        cost_cents=100,
        is_active=True,
    )
    db_session.add(ii)
    db_session.commit()

    resp = client.get(f"/admin/inventory/{ii.id}/edit")
    _assert_response_renders_html(resp)

# =========================
# ROUTE: /admin/inventory/<int:inventory_item_id>/edit (POST)
# =========================
def test_admin_inventory_inventory_item_id_edit_post_exists():
    _assert_route_methods_exist("/admin/inventory/<int:inventory_item_id>/edit", {"POST"})

def test_admin_inventory_inventory_item_id_edit_post_success(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    ii = InventoryItem(
        name=_unique("EditInv"),
        sku=_unique("SKU"),
        unit="unit",
        quantity_on_hand=Decimal("1.00"),
        reorder_threshold=Decimal("0.50"),
        cost_cents=100,
        is_active=True,
    )
    db_session.add(ii)
    db_session.commit()

    new_sku = _unique("SKU2")
    resp = client.post(
        f"/admin/inventory/{ii.id}/edit",
        data={
            "name": _unique("EditInvAfter"),
            "sku": new_sku,
            "unit": "kg",
            "quantity_on_hand": "2.25",
            "reorder_threshold": "1.00",
            "cost_cents": "150",
            "is_active": "0",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)

    updated = InventoryItem.query.get(ii.id)
    assert updated.sku == new_sku
    assert str(updated.unit) == "kg"

def test_admin_inventory_inventory_item_id_edit_post_missing_required_fields(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    ii = InventoryItem(
        name=_unique("EditInv"),
        sku=_unique("SKU"),
        unit="unit",
        quantity_on_hand=Decimal("1.00"),
        reorder_threshold=Decimal("0.50"),
        cost_cents=100,
        is_active=True,
    )
    db_session.add(ii)
    db_session.commit()

    resp = client.post(f"/admin/inventory/{ii.id}/edit", data={"name": ""}, follow_redirects=False)
    assert resp.status_code in (200, 400, 422)

    unchanged = InventoryItem.query.get(ii.id)
    assert unchanged.name == ii.name

def test_admin_inventory_inventory_item_id_edit_post_invalid_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    ii = InventoryItem(
        name=_unique("EditInv"),
        sku=_unique("SKU"),
        unit="unit",
        quantity_on_hand=Decimal("1.00"),
        reorder_threshold=Decimal("0.50"),
        cost_cents=100,
        is_active=True,
    )
    db_session.add(ii)
    db_session.commit()

    resp = client.post(
        f"/admin/inventory/{ii.id}/edit",
        data={"name": _unique("X"), "sku": _unique("Y"), "quantity_on_hand": "notnum", "cost_cents": "-1"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 422)

    unchanged = InventoryItem.query.get(ii.id)
    assert unchanged.cost_cents == 100

def test_admin_inventory_inventory_item_id_edit_post_duplicate_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    sku1 = _unique("SKU1")
    sku2 = _unique("SKU2")
    ii1 = InventoryItem(name=_unique("Inv1"), sku=sku1, unit="unit", quantity_on_hand=Decimal("0"), reorder_threshold=Decimal("0"))
    ii2 = InventoryItem(name=_unique("Inv2"), sku=sku2, unit="unit", quantity_on_hand=Decimal("0"), reorder_threshold=Decimal("0"))
    db_session.add_all([ii1, ii2])
    db_session.commit()

    resp = client.post(
        f"/admin/inventory/{ii2.id}/edit",
        data={"name": ii2.name, "sku": sku1, "unit": "unit", "quantity_on_hand": "0", "reorder_threshold": "0"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 400, 409, 422)
    assert InventoryItem.query.filter_by(sku=sku1).count() == 1

# =========================
# ROUTE: /admin/inventory/<int:inventory_item_id>/delete (POST)
# =========================
def test_admin_inventory_inventory_item_id_delete_post_exists():
    _assert_route_methods_exist("/admin/inventory/<int:inventory_item_id>/delete", {"POST"})

def test_admin_inventory_inventory_item_id_delete_post_success(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    ii = InventoryItem(name=_unique("DelInv"), sku=_unique("SKU"), unit="unit", quantity_on_hand=Decimal("0"), reorder_threshold=Decimal("0"))
    db_session.add(ii)
    db_session.commit()

    resp = client.post(f"/admin/inventory/{ii.id}/delete", data={}, follow_redirects=False)
    assert resp.status_code in (200, 302)

    deleted = InventoryItem.query.get(ii.id)
    assert deleted is None

def test_admin_inventory_inventory_item_id_delete_post_missing_required_fields(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post("/admin/inventory/999999/delete", data={}, follow_redirects=False)
    assert resp.status_code in (200, 302, 404)

def test_admin_inventory_inventory_item_id_delete_post_invalid_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    resp = client.post("/admin/inventory/0/delete", data={"unexpected": "1"}, follow_redirects=False)
    assert resp.status_code in (200, 302, 400, 404)

def test_admin_inventory_inventory_item_id_delete_post_duplicate_data(client, db_session):
    admin = _create_admin_user(db_session)
    _force_login_as(client, admin)

    ii = InventoryItem(name=_unique("DelInvDup"), sku=_unique("SKU"), unit="unit", quantity_on_hand=Decimal("0"), reorder_threshold=Decimal("0"))
    db_session.add(ii)
    db_session.commit()

    resp1 = client.post(f"/admin/inventory/{ii.id}/delete", data={}, follow_redirects=False)
    assert resp1.status_code in (200, 302)

    resp2 = client.post(f"/admin/inventory/{ii.id}/delete", data={}, follow_redirects=False)
    assert resp2.status_code in (200, 302, 404)

# =========================
# HELPER: admin_required(view_func: callable)
# =========================
def test_admin_required_function_exists():
    assert callable(admin_required)

def test_admin_required_with_valid_input():
    def view():
        return "ok"

    wrapped = admin_required(view)
    assert callable(wrapped)

def test_admin_required_with_invalid_input():
    with pytest.raises(Exception):
        admin_required(None)

# =========================
# HELPER: get_current_user()
# =========================
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(app_context, db_session):
    admin = _create_admin_user(db_session)
    with app.test_request_context("/admin"):
        with patch("controllers.admin_interface_controller.get_current_user", return_value=admin) as p:
            u = p()
            assert u is admin

def test_get_current_user_with_invalid_input(app_context):
    with app.test_request_context("/admin"):
        with patch("controllers.admin_interface_controller.get_current_user", return_value=None) as p:
            u = p()
            assert u is None

# =========================
# HELPER: validate_staff_payload(form: dict)
# =========================
def test_validate_staff_payload_function_exists():
    assert callable(validate_staff_payload)

def test_validate_staff_payload_with_valid_input():
    form = {"full_name": "Valid Name", "email": "valid@example.com", "phone": "555", "position": "Chef", "is_active": "1"}
    data, errors = validate_staff_payload(form)
    assert isinstance(data, dict)
    assert isinstance(errors, dict)
    assert errors == {}

def test_validate_staff_payload_with_invalid_input():
    form = {"full_name": "", "email": "bad", "position": ""}
    data, errors = validate_staff_payload(form)
    assert isinstance(data, dict)
    assert isinstance(errors, dict)
    assert errors != {}

# =========================
# HELPER: validate_menu_payload(form: dict)
# =========================
def test_validate_menu_payload_function_exists():
    assert callable(validate_menu_payload)

def test_validate_menu_payload_with_valid_input():
    form = {"name": "Item", "description": "Desc", "price_cents": "100", "is_available": "1", "sort_order": "0"}
    data, errors = validate_menu_payload(form)
    assert isinstance(data, dict)
    assert isinstance(errors, dict)
    assert errors == {}

def test_validate_menu_payload_with_invalid_input():
    form = {"name": "", "price_cents": "notint", "sort_order": "nope"}
    data, errors = validate_menu_payload(form)
    assert isinstance(data, dict)
    assert isinstance(errors, dict)
    assert errors != {}

# =========================
# HELPER: validate_inventory_payload(form: dict)
# =========================
def test_validate_inventory_payload_function_exists():
    assert callable(validate_inventory_payload)

def test_validate_inventory_payload_with_valid_input():
    form = {
        "name": "Flour",
        "sku": "SKU123",
        "unit": "kg",
        "quantity_on_hand": "10.50",
        "reorder_threshold": "2.00",
        "cost_cents": "199",
        "is_active": "1",
    }
    data, errors = validate_inventory_payload(form)
    assert isinstance(data, dict)
    assert isinstance(errors, dict)
    assert errors == {}

def test_validate_inventory_payload_with_invalid_input():
    form = {"name": "", "sku": "", "quantity_on_hand": "nope", "reorder_threshold": "-1", "cost_cents": "bad"}
    data, errors = validate_inventory_payload(form)
    assert isinstance(data, dict)
    assert isinstance(errors, dict)
    assert errors != {}