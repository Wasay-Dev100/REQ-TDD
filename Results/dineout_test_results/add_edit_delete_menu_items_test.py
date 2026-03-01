import os
import sys
import uuid
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.add_edit_delete_menu_items_menu_item import MenuItem
from controllers.add_edit_delete_menu_items_controller import (
    require_admin,
    validate_menu_item_payload,
    get_menu_item_or_404,
)
from views.add_edit_delete_menu_items_views import render_menu_item_list, render_menu_item_form

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

def _unique_name(prefix="Dish"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_menu_item_in_db(
    *,
    name=None,
    description="Tasty",
    price=Decimal("9.99"),
    is_available=True,
    image_url=None,
):
    if name is None:
        name = _unique_name("MenuItem")
    item = MenuItem(
        name=name,
        description=description,
        price=price,
        is_available=is_available,
        image_url=image_url,
    )
    db.session.add(item)
    db.session.commit()
    return item

def _post_form_create(client, *, name, description="Desc", price="12.50", is_available="y", image_url=""):
    data = {
        "name": name,
        "description": description,
        "price": price,
        "is_available": is_available,
        "image_url": image_url,
    }
    return client.post("/admin/menu-items", data=data)

def _post_form_update(
    client,
    *,
    menu_item_id,
    name,
    description="Updated",
    price="15.00",
    is_available="y",
    image_url="",
):
    data = {
        "name": name,
        "description": description,
        "price": price,
        "is_available": is_available,
        "image_url": image_url,
    }
    return client.post(f"/admin/menu-items/{menu_item_id}", data=data)

def _post_form_delete(client, *, menu_item_id):
    return client.post(f"/admin/menu-items/{menu_item_id}/delete")

def _post_api_create(client, payload: dict):
    return client.post("/api/admin/menu-items", json=payload)

def _put_api_update(client, *, menu_item_id: int, payload: dict):
    return client.put(f"/api/admin/menu-items/{menu_item_id}", json=payload)

def _delete_api_delete(client, *, menu_item_id: int):
    return client.delete(f"/api/admin/menu-items/{menu_item_id}")

def _route_exists(rule: str, method: str) -> bool:
    method = method.upper()
    for r in app.url_map.iter_rules():
        if r.rule == rule and method in r.methods:
            return True
    return False

def _assert_route_exists(rule: str, method: str):
    assert _route_exists(rule, method), f"Missing route {method} {rule}"

def _is_json_response(resp) -> bool:
    ctype = (resp.headers.get("Content-Type") or "").lower()
    return "application/json" in ctype

def _extract_json(resp):
    if hasattr(resp, "get_json"):
        return resp.get_json(silent=True)
    return None

class TestMenuItemModel:
    def test_menuitem_model_has_required_fields(self, app_context):
        required = [
            "id",
            "name",
            "description",
            "price",
            "is_available",
            "image_url",
            "created_at",
            "updated_at",
        ]
        for field in required:
            assert hasattr(MenuItem, field), f"MenuItem missing field: {field}"

    def test_menuitem_to_dict(self, app_context):
        item = _create_menu_item_in_db(
            name=_unique_name("ToDict"),
            description="A",
            price=Decimal("10.25"),
            is_available=False,
            image_url="http://example.com/a.jpg",
        )
        assert hasattr(item, "to_dict")
        data = item.to_dict()
        assert isinstance(data, dict)
        for key in [
            "id",
            "name",
            "description",
            "price",
            "is_available",
            "image_url",
            "created_at",
            "updated_at",
        ]:
            assert key in data

        assert data["id"] == item.id
        assert data["name"] == item.name
        assert data["description"] == item.description
        assert data["is_available"] == item.is_available
        assert data["image_url"] == item.image_url

    def test_menuitem_update_from_dict(self, app_context):
        item = _create_menu_item_in_db(
            name=_unique_name("UpdateFromDict"),
            description="Old",
            price=Decimal("1.00"),
            is_available=True,
            image_url=None,
        )
        assert hasattr(item, "update_from_dict")
        item.update_from_dict(
            {
                "name": _unique_name("NewName"),
                "description": "New",
                "price": Decimal("2.50"),
                "is_available": False,
                "image_url": "http://example.com/new.png",
            }
        )
        db.session.commit()
        refreshed = MenuItem.query.filter_by(id=item.id).first()
        assert refreshed is not None
        assert refreshed.name.startswith("NewName_")
        assert refreshed.description == "New"
        assert Decimal(str(refreshed.price)) == Decimal("2.50")
        assert refreshed.is_available is False
        assert refreshed.image_url == "http://example.com/new.png"

    def test_menuitem_unique_constraints(self, app_context):
        name = _unique_name("Unique")
        _create_menu_item_in_db(name=name, price=Decimal("3.33"))
        dup = MenuItem(name=name, description="Dup", price=Decimal("4.44"), is_available=True)
        db.session.add(dup)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

class TestAdminMenuItemsListGet:
    def test_admin_menu_items_get_exists(self, client):
        _assert_route_exists("/admin/menu-items", "GET")

    def test_admin_menu_items_get_renders_template(self, client):
        resp = client.get("/admin/menu-items")
        assert resp.status_code in (200, 302, 401, 403)
        if resp.status_code == 200:
            assert resp.data is not None
            assert len(resp.data) > 0

class TestAdminMenuItemsNewGet:
    def test_admin_menu_items_new_get_exists(self, client):
        _assert_route_exists("/admin/menu-items/new", "GET")

    def test_admin_menu_items_new_get_renders_template(self, client):
        resp = client.get("/admin/menu-items/new")
        assert resp.status_code in (200, 302, 401, 403)
        if resp.status_code == 200:
            assert resp.data is not None
            assert len(resp.data) > 0

class TestAdminMenuItemsCreatePost:
    def test_admin_menu_items_post_exists(self, client):
        _assert_route_exists("/admin/menu-items", "POST")

    def test_admin_menu_items_post_success(self, client, app_context):
        name = _unique_name("CreateForm")
        resp = _post_form_create(client, name=name, description="Nice", price="11.10", is_available="y")
        assert resp.status_code in (200, 201, 302, 400, 401, 403)
        if resp.status_code in (200, 201, 302):
            created = MenuItem.query.filter_by(name=name).first()
            assert created is not None
            assert created.name == name

    def test_admin_menu_items_post_missing_required_fields(self, client, app_context):
        resp = client.post("/admin/menu-items", data={"description": "No name/price"})
        assert resp.status_code in (200, 400, 401, 403, 422)
        assert MenuItem.query.count() == 0

    def test_admin_menu_items_post_invalid_data(self, client, app_context):
        name = _unique_name("InvalidPrice")
        resp = _post_form_create(client, name=name, description="Bad", price="not-a-number")
        assert resp.status_code in (200, 400, 401, 403, 422)
        assert MenuItem.query.filter_by(name=name).first() is None

    def test_admin_menu_items_post_duplicate_data(self, client, app_context):
        name = _unique_name("DupForm")
        _create_menu_item_in_db(name=name, price=Decimal("5.00"))
        resp = _post_form_create(client, name=name, description="Dup", price="6.00")
        assert resp.status_code in (200, 302, 400, 401, 403, 409, 422)
        assert MenuItem.query.filter_by(name=name).count() == 1

class TestAdminMenuItemsEditGet:
    def test_admin_menu_items_menu_item_id_edit_get_exists(self, client):
        _assert_route_exists("/admin/menu-items/<int:menu_item_id>/edit", "GET")

    def test_admin_menu_items_menu_item_id_edit_get_renders_template(self, client, app_context):
        item = _create_menu_item_in_db(name=_unique_name("EditGet"), price=Decimal("7.77"))
        resp = client.get(f"/admin/menu-items/{item.id}/edit")
        assert resp.status_code in (200, 302, 401, 403, 404)
        if resp.status_code == 200:
            assert resp.data is not None
            assert len(resp.data) > 0

class TestAdminMenuItemsUpdatePost:
    def test_admin_menu_items_menu_item_id_post_exists(self, client):
        _assert_route_exists("/admin/menu-items/<int:menu_item_id>", "POST")

    def test_admin_menu_items_menu_item_id_post_success(self, client, app_context):
        item = _create_menu_item_in_db(name=_unique_name("UpdateForm"), price=Decimal("8.00"))
        new_name = _unique_name("UpdatedFormName")
        resp = _post_form_update(client, menu_item_id=item.id, name=new_name, description="NewD", price="9.25")
        assert resp.status_code in (200, 302, 400, 401, 403, 404, 422)
        if resp.status_code in (200, 302):
            updated = MenuItem.query.filter_by(id=item.id).first()
            assert updated is not None
            assert updated.name == new_name
            assert Decimal(str(updated.price)) == Decimal("9.25")

    def test_admin_menu_items_menu_item_id_post_missing_required_fields(self, client, app_context):
        item = _create_menu_item_in_db(name=_unique_name("UpdateMissing"), price=Decimal("8.00"))
        resp = client.post(f"/admin/menu-items/{item.id}", data={"description": "No name/price"})
        assert resp.status_code in (200, 400, 401, 403, 404, 422)
        unchanged = MenuItem.query.filter_by(id=item.id).first()
        assert unchanged is not None
        assert unchanged.name == item.name

    def test_admin_menu_items_menu_item_id_post_invalid_data(self, client, app_context):
        item = _create_menu_item_in_db(name=_unique_name("UpdateInvalid"), price=Decimal("8.00"))
        resp = _post_form_update(client, menu_item_id=item.id, name=item.name, price="bad-price")
        assert resp.status_code in (200, 400, 401, 403, 404, 422)
        unchanged = MenuItem.query.filter_by(id=item.id).first()
        assert unchanged is not None
        assert Decimal(str(unchanged.price)) == Decimal("8.00")

    def test_admin_menu_items_menu_item_id_post_duplicate_data(self, client, app_context):
        item1 = _create_menu_item_in_db(name=_unique_name("DupTarget"), price=Decimal("1.00"))
        item2 = _create_menu_item_in_db(name=_unique_name("DupSource"), price=Decimal("2.00"))
        resp = _post_form_update(client, menu_item_id=item2.id, name=item1.name, price="2.00")
        assert resp.status_code in (200, 302, 400, 401, 403, 404, 409, 422)
        still = MenuItem.query.filter_by(id=item2.id).first()
        assert still is not None
        assert still.name != item1.name

class TestAdminMenuItemsDeletePost:
    def test_admin_menu_items_menu_item_id_delete_post_exists(self, client):
        _assert_route_exists("/admin/menu-items/<int:menu_item_id>/delete", "POST")

    def test_admin_menu_items_menu_item_id_delete_post_success(self, client, app_context):
        item = _create_menu_item_in_db(name=_unique_name("DeleteForm"), price=Decimal("3.00"))
        resp = _post_form_delete(client, menu_item_id=item.id)
        assert resp.status_code in (200, 302, 400, 401, 403, 404)
        if resp.status_code in (200, 302):
            assert MenuItem.query.filter_by(id=item.id).first() is None

    def test_admin_menu_items_menu_item_id_delete_post_missing_required_fields(self, client, app_context):
        resp = client.post("/admin/menu-items/999999/delete", data={})
        assert resp.status_code in (200, 302, 400, 401, 403, 404)

    def test_admin_menu_items_menu_item_id_delete_post_invalid_data(self, client, app_context):
        resp = client.post("/admin/menu-items/not-an-int/delete", data={})
        assert resp.status_code in (404, 405)

    def test_admin_menu_items_menu_item_id_delete_post_duplicate_data(self, client, app_context):
        item = _create_menu_item_in_db(name=_unique_name("DeleteDup"), price=Decimal("4.00"))
        resp1 = _post_form_delete(client, menu_item_id=item.id)
        assert resp1.status_code in (200, 302, 400, 401, 403, 404)
        resp2 = _post_form_delete(client, menu_item_id=item.id)
        assert resp2.status_code in (200, 302, 400, 401, 403, 404)

class TestApiAdminMenuItemsListGet:
    def test_api_admin_menu_items_get_exists(self, client):
        _assert_route_exists("/api/admin/menu-items", "GET")

    def test_api_admin_menu_items_get_renders_template(self, client, app_context):
        _create_menu_item_in_db(name=_unique_name("ApiList"), price=Decimal("1.23"))
        resp = client.get("/api/admin/menu-items")
        assert resp.status_code in (200, 302, 401, 403)
        if resp.status_code == 200:
            if _is_json_response(resp):
                data = _extract_json(resp)
                assert data is not None
            else:
                assert resp.data is not None
                assert len(resp.data) > 0

class TestApiAdminMenuItemsCreatePost:
    def test_api_admin_menu_items_post_exists(self, client):
        _assert_route_exists("/api/admin/menu-items", "POST")

    def test_api_admin_menu_items_post_success(self, client, app_context):
        name = _unique_name("ApiCreate")
        payload = {
            "name": name,
            "description": "API",
            "price": "10.00",
            "is_available": True,
            "image_url": "http://example.com/x.png",
        }
        resp = _post_api_create(client, payload)
        assert resp.status_code in (200, 201, 302, 400, 401, 403, 409, 422)
        if resp.status_code in (200, 201):
            created = MenuItem.query.filter_by(name=name).first()
            assert created is not None

    def test_api_admin_menu_items_post_missing_required_fields(self, client, app_context):
        resp = _post_api_create(client, {"description": "missing"})
        assert resp.status_code in (400, 401, 403, 422)
        assert MenuItem.query.count() == 0

    def test_api_admin_menu_items_post_invalid_data(self, client, app_context):
        name = _unique_name("ApiInvalid")
        resp = _post_api_create(client, {"name": name, "price": "bad"})
        assert resp.status_code in (400, 401, 403, 422)
        assert MenuItem.query.filter_by(name=name).first() is None

    def test_api_admin_menu_items_post_duplicate_data(self, client, app_context):
        name = _unique_name("ApiDup")
        _create_menu_item_in_db(name=name, price=Decimal("5.00"))
        resp = _post_api_create(client, {"name": name, "price": "6.00"})
        assert resp.status_code in (400, 401, 403, 409, 422)
        assert MenuItem.query.filter_by(name=name).count() == 1

class TestApiAdminMenuItemsGetItem:
    def test_api_admin_menu_items_menu_item_id_get_exists(self, client):
        _assert_route_exists("/api/admin/menu-items/<int:menu_item_id>", "GET")

    def test_api_admin_menu_items_menu_item_id_get_renders_template(self, client, app_context):
        item = _create_menu_item_in_db(name=_unique_name("ApiGet"), price=Decimal("2.22"))
        resp = client.get(f"/api/admin/menu-items/{item.id}")
        assert resp.status_code in (200, 302, 401, 403, 404)
        if resp.status_code == 200:
            if _is_json_response(resp):
                data = _extract_json(resp)
                assert data is not None
                if isinstance(data, dict) and "id" in data:
                    assert data["id"] == item.id
            else:
                assert resp.data is not None
                assert len(resp.data) > 0

class TestApiAdminMenuItemsUpdatePut:
    def test_api_admin_menu_items_menu_item_id_put_exists(self, client):
        _assert_route_exists("/api/admin/menu-items/<int:menu_item_id>", "PUT")

class TestApiAdminMenuItemsDelete:
    def test_api_admin_menu_items_menu_item_id_delete_exists(self, client):
        _assert_route_exists("/api/admin/menu-items/<int:menu_item_id>", "DELETE")

class TestRequireAdminHelper:
    def test_require_admin_function_exists(self):
        assert callable(require_admin)

    def test_require_admin_with_valid_input(self):
        class DummyUser:
            is_admin = True

        result = require_admin(DummyUser())
        assert isinstance(result, bool)
        assert result is True

    def test_require_admin_with_invalid_input(self):
        result_none = require_admin(None)
        assert isinstance(result_none, bool)
        assert result_none is False

        class DummyUser:
            is_admin = False

        result_false = require_admin(DummyUser())
        assert isinstance(result_false, bool)
        assert result_false is False

class TestValidateMenuItemPayloadHelper:
    def test_validate_menu_item_payload_function_exists(self):
        assert callable(validate_menu_item_payload)

    def test_validate_menu_item_payload_with_valid_input(self):
        ok, errors = validate_menu_item_payload(
            {
                "name": _unique_name("Payload"),
                "description": "D",
                "price": "12.34",
                "is_available": True,
                "image_url": "http://example.com/a.png",
            },
            partial=False,
        )
        assert isinstance(ok, bool)
        assert isinstance(errors, dict)
        assert ok is True
        assert errors == {} or len(errors) == 0

    def test_validate_menu_item_payload_with_invalid_input(self):
        ok, errors = validate_menu_item_payload({"name": "", "price": "bad"}, partial=False)
        assert isinstance(ok, bool)
        assert isinstance(errors, dict)
        assert ok is False
        assert len(errors) > 0

class TestGetMenuItemOr404Helper:
    def test_get_menu_item_or_404_function_exists(self):
        assert callable(get_menu_item_or_404)

    def test_get_menu_item_or_404_with_valid_input(self, app_context):
        item = _create_menu_item_in_db(name=_unique_name("Or404"), price=Decimal("1.11"))
        found = get_menu_item_or_404(item.id)
        assert found is not None
        assert isinstance(found, MenuItem)
        assert found.id == item.id

    def test_get_menu_item_or_404_with_invalid_input(self, app_context):
        with pytest.raises(Exception):
            get_menu_item_or_404(99999999)