import os
import sys
import uuid
from decimal import Decimal
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.manager_interface_table import ManagerInterfaceTable
from models.manager_interface_order import ManagerInterfaceOrder
from controllers.manager_interface_controller import serialize_table, serialize_order, get_utcnow
from views.manager_interface_views import render_free_tables_page

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

def _unique_int():
    return int(uuid.uuid4().int % 1_000_000_000)

def _create_table(table_number=None, status="free"):
    if table_number is None:
        table_number = _unique_int()
    t = ManagerInterfaceTable(table_number=table_number, status=status)
    db.session.add(t)
    db.session.commit()
    return t

def _create_order(table_id, status="unpaid", total_amount=Decimal("10.00"), paid_at=None):
    o = ManagerInterfaceOrder(
        table_id=table_id,
        status=status,
        total_amount=total_amount,
        paid_at=paid_at,
    )
    db.session.add(o)
    db.session.commit()
    return o

class TestManagerInterfaceTableModel:
    def test_managerinterfacetable_model_has_required_fields(self, app_context):
        table = ManagerInterfaceTable(table_number=_unique_int(), status="free")
        assert hasattr(table, "id")
        assert hasattr(table, "table_number")
        assert hasattr(table, "status")

    def test_managerinterfacetable_is_free(self, app_context):
        t1 = ManagerInterfaceTable(table_number=_unique_int(), status="free")
        assert t1.is_free() is True

        t2 = ManagerInterfaceTable(table_number=_unique_int(), status="occupied")
        assert t2.is_free() is False

    def test_managerinterfacetable_mark_free(self, app_context):
        t = ManagerInterfaceTable(table_number=_unique_int(), status="occupied")
        t.mark_free()
        assert t.status == "free"
        assert t.is_free() is True

    def test_managerinterfacetable_mark_occupied(self, app_context):
        t = ManagerInterfaceTable(table_number=_unique_int(), status="free")
        t.mark_occupied()
        assert t.status == "occupied"
        assert t.is_free() is False

    def test_managerinterfacetable_unique_constraints(self, app_context):
        num = _unique_int()
        t1 = ManagerInterfaceTable(table_number=num, status="free")
        db.session.add(t1)
        db.session.commit()

        t2 = ManagerInterfaceTable(table_number=num, status="free")
        db.session.add(t2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

class TestManagerInterfaceOrderModel:
    def test_managerinterfaceorder_model_has_required_fields(self, app_context):
        order = ManagerInterfaceOrder(
            table_id=_unique_int(),
            status="unpaid",
            total_amount=Decimal("12.34"),
            paid_at=None,
        )
        assert hasattr(order, "id")
        assert hasattr(order, "table_id")
        assert hasattr(order, "status")
        assert hasattr(order, "total_amount")
        assert hasattr(order, "paid_at")

    def test_managerinterfaceorder_is_paid(self, app_context):
        o1 = ManagerInterfaceOrder(
            table_id=_unique_int(),
            status="paid",
            total_amount=Decimal("1.00"),
            paid_at=datetime.now(timezone.utc),
        )
        assert o1.is_paid() is True

        o2 = ManagerInterfaceOrder(
            table_id=_unique_int(),
            status="unpaid",
            total_amount=Decimal("1.00"),
            paid_at=None,
        )
        assert o2.is_paid() is False

    def test_managerinterfaceorder_mark_paid(self, app_context):
        paid_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        o = ManagerInterfaceOrder(
            table_id=_unique_int(),
            status="unpaid",
            total_amount=Decimal("99.99"),
            paid_at=None,
        )
        o.mark_paid(paid_at)
        assert o.status == "paid"
        assert o.paid_at == paid_at
        assert o.is_paid() is True

    def test_managerinterfaceorder_unique_constraints(self, app_context):
        t = _create_table(status="occupied")
        o1 = ManagerInterfaceOrder(table_id=t.id, status="unpaid", total_amount=Decimal("10.00"), paid_at=None)
        o2 = ManagerInterfaceOrder(table_id=t.id, status="unpaid", total_amount=Decimal("10.00"), paid_at=None)
        db.session.add_all([o1, o2])
        db.session.commit()
        assert o1.id is not None
        assert o2.id is not None
        assert o1.id != o2.id

class TestManagerTablesFreeRoute:
    def test_manager_tables_free_get_exists(self, client):
        rules = [r for r in app.url_map.iter_rules() if r.rule == "/manager/tables/free"]
        assert rules, "Route /manager/tables/free is missing"
        assert any("GET" in r.methods for r in rules), "Route /manager/tables/free must accept GET"

        resp = client.get("/manager/tables/free")
        assert resp.status_code != 405

    def test_manager_tables_free_get_renders_template(self, client):
        with app.app_context():
            _create_table(status="free")
            _create_table(status="occupied")

        resp = client.get("/manager/tables/free")
        assert resp.status_code == 200
        assert b"<html" in resp.data.lower() or b"table" in resp.data.lower()

class TestManagerMarkOrderPaidRoute:
    def test_manager_orders_order_id_mark_paid_post_exists(self, client):
        rules = [r for r in app.url_map.iter_rules() if r.rule == "/manager/orders/<int:order_id>/mark_paid"]
        assert rules, "Route /manager/orders/<int:order_id>/mark_paid is missing"
        assert any("POST" in r.methods for r in rules), "Route must accept POST"

        resp = client.post("/manager/orders/1/mark_paid")
        assert resp.status_code != 405

    def test_manager_orders_order_id_mark_paid_post_success(self, client):
        with app.app_context():
            t = _create_table(status="occupied")
            o = _create_order(table_id=t.id, status="unpaid", total_amount=Decimal("20.00"), paid_at=None)
            order_id = o.id

        resp = client.post(f"/manager/orders/{order_id}/mark_paid", data={})
        assert resp.status_code in (200, 201, 204, 302)

        with app.app_context():
            updated = ManagerInterfaceOrder.query.filter_by(id=order_id).first()
            assert updated is not None
            assert updated.is_paid() is True
            assert updated.status == "paid"
            assert updated.paid_at is not None

    def test_manager_orders_order_id_mark_paid_post_missing_required_fields(self, client):
        with app.app_context():
            t = _create_table(status="occupied")
            o = _create_order(table_id=t.id, status="unpaid", total_amount=Decimal("20.00"), paid_at=None)
            order_id = o.id

        resp = client.post(
            f"/manager/orders/{order_id}/mark_paid",
            data={"paid_at": ""},
        )
        assert resp.status_code in (400, 422, 200)

        with app.app_context():
            updated = ManagerInterfaceOrder.query.filter_by(id=order_id).first()
            assert updated is not None
            assert updated.is_paid() is False
            assert updated.paid_at is None

    def test_manager_orders_order_id_mark_paid_post_invalid_data(self, client):
        with app.app_context():
            t = _create_table(status="occupied")
            o = _create_order(table_id=t.id, status="unpaid", total_amount=Decimal("20.00"), paid_at=None)
            order_id = o.id

        resp = client.post(
            f"/manager/orders/{order_id}/mark_paid",
            data={"paid_at": "not-a-datetime"},
        )
        assert resp.status_code in (400, 422, 200)

        with app.app_context():
            updated = ManagerInterfaceOrder.query.filter_by(id=order_id).first()
            assert updated is not None
            assert updated.is_paid() is False
            assert updated.paid_at is None

    def test_manager_orders_order_id_mark_paid_post_duplicate_data(self, client):
        with app.app_context():
            t = _create_table(status="occupied")
            paid_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            o = _create_order(table_id=t.id, status="paid", total_amount=Decimal("20.00"), paid_at=paid_at)
            order_id = o.id

        resp = client.post(f"/manager/orders/{order_id}/mark_paid", data={})
        assert resp.status_code in (200, 204, 302, 409)

        with app.app_context():
            updated = ManagerInterfaceOrder.query.filter_by(id=order_id).first()
            assert updated is not None
            assert updated.is_paid() is True
            assert updated.paid_at is not None

class TestHelperSerializeTable:
    def test_serialize_table_function_exists(self):
        assert callable(serialize_table)

    def test_serialize_table_with_valid_input(self, app_context):
        t = ManagerInterfaceTable(table_number=_unique_int(), status="free")
        data = serialize_table(t)
        assert isinstance(data, dict)
        assert "id" in data
        assert "table_number" in data
        assert "status" in data

    def test_serialize_table_with_invalid_input(self):
        with pytest.raises((TypeError, AttributeError)):
            serialize_table(None)

class TestHelperSerializeOrder:
    def test_serialize_order_function_exists(self):
        assert callable(serialize_order)

    def test_serialize_order_with_valid_input(self, app_context):
        o = ManagerInterfaceOrder(
            table_id=_unique_int(),
            status="unpaid",
            total_amount=Decimal("12.34"),
            paid_at=None,
        )
        data = serialize_order(o)
        assert isinstance(data, dict)
        assert "id" in data
        assert "table_id" in data
        assert "status" in data
        assert "total_amount" in data
        assert "paid_at" in data

    def test_serialize_order_with_invalid_input(self):
        with pytest.raises((TypeError, AttributeError)):
            serialize_order(None)

class TestHelperGetUtcnow:
    def test_get_utcnow_function_exists(self):
        assert callable(get_utcnow)

    def test_get_utcnow_with_valid_input(self):
        now = get_utcnow()
        assert isinstance(now, datetime)

    def test_get_utcnow_with_invalid_input(self):
        with pytest.raises(TypeError):
            get_utcnow(1)

class TestViewRenderFreeTablesPage:
    def test_render_free_tables_page_function_exists(self):
        assert callable(render_free_tables_page)

    def test_render_free_tables_page_with_valid_input(self, app_context):
        tables = [
            ManagerInterfaceTable(table_number=_unique_int(), status="free"),
            ManagerInterfaceTable(table_number=_unique_int(), status="free"),
        ]
        html = render_free_tables_page(tables)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_render_free_tables_page_with_invalid_input(self):
        with pytest.raises((TypeError, AttributeError)):
            render_free_tables_page(None)