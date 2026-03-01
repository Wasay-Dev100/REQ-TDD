import os
import sys
import uuid
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.request_bill_order import Order
from models.request_bill_bill_request import BillRequest
from models.request_bill_payment import Payment
from controllers.request_bill_controller import request_bill_bp
from controllers.request_bill_controller import (
    notify_hall_manager_bill_requested,
    print_bill,
    serialize_manager_bill_request,
)
from views.request_bill_views import render_manager_bill_requests

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

def _unique_order_no(prefix="ORD"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def _create_order(
    *,
    order_no=None,
    table_no="T1",
    total_amount=Decimal("12.50"),
    status="open",
    created_at=None,
):
    if order_no is None:
        order_no = _unique_order_no()
    if created_at is None:
        created_at = datetime.utcnow()
    order = Order(
        order_no=order_no,
        table_no=table_no,
        total_amount=total_amount,
        status=status,
        created_at=created_at,
    )
    db.session.add(order)
    db.session.commit()
    return order

def _create_bill_request(*, order_id, status="pending", requested_at=None):
    if requested_at is None:
        requested_at = datetime.utcnow()
    br = BillRequest(order_id=order_id, requested_at=requested_at, status=status)
    db.session.add(br)
    db.session.commit()
    return br

def _create_payment(*, order_id, amount=Decimal("12.50"), method="cash", reference=None, paid_at=None):
    if paid_at is None:
        paid_at = datetime.utcnow()
    p = Payment(order_id=order_id, amount=amount, method=method, reference=reference, paid_at=paid_at)
    db.session.add(p)
    db.session.commit()
    return p

class TestOrderModel:
    def test_order_model_has_required_fields(self, app_context):
        for field in ["id", "order_no", "table_no", "total_amount", "status", "created_at"]:
            assert hasattr(Order, field), f"Order missing required field: {field}"

    def test_order_mark_bill_requested(self, app_context):
        order = _create_order(status="open")
        assert hasattr(order, "mark_bill_requested")
        order.mark_bill_requested()
        db.session.commit()
        assert order.status is not None
        assert str(order.status).lower() in {"bill_requested", "requested", "bill-requested", "bill requested"}

    def test_order_mark_paid(self, app_context):
        order = _create_order(status="bill_requested")
        assert hasattr(order, "mark_paid")
        order.mark_paid()
        db.session.commit()
        assert order.status is not None
        assert str(order.status).lower() in {"paid"}

    def test_order_is_payable(self, app_context):
        order = _create_order(status="bill_requested")
        assert hasattr(order, "is_payable")
        result = order.is_payable()
        assert isinstance(result, bool)

    def test_order_unique_constraints(self, app_context):
        order_no = _unique_order_no("UNIQ")
        _create_order(order_no=order_no)
        dup = Order(
            order_no=order_no,
            table_no="T2",
            total_amount=Decimal("9.99"),
            status="open",
            created_at=datetime.utcnow(),
        )
        db.session.add(dup)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

class TestBillRequestModel:
    def test_billrequest_model_has_required_fields(self, app_context):
        for field in ["id", "order_id", "requested_at", "status"]:
            assert hasattr(BillRequest, field), f"BillRequest missing required field: {field}"

    def test_billrequest_mark_processed(self, app_context):
        order = _create_order(status="bill_requested")
        br = _create_bill_request(order_id=order.id, status="pending")
        assert hasattr(br, "mark_processed")
        br.mark_processed()
        db.session.commit()
        assert br.status is not None
        assert str(br.status).lower() in {"processed", "done", "completed"}

    def test_billrequest_unique_constraints(self, app_context):
        order = _create_order()
        _create_bill_request(order_id=order.id, status="pending")
        _create_bill_request(order_id=order.id, status="pending")
        assert BillRequest.query.filter_by(order_id=order.id).count() == 2

class TestPaymentModel:
    def test_payment_model_has_required_fields(self, app_context):
        for field in ["id", "order_id", "amount", "method", "reference", "paid_at"]:
            assert hasattr(Payment, field), f"Payment missing required field: {field}"

    def test_payment_unique_constraints(self, app_context):
        order = _create_order(status="bill_requested")
        _create_payment(order_id=order.id, amount=Decimal("12.50"), method="cash", reference="R1")
        _create_payment(order_id=order.id, amount=Decimal("12.50"), method="cash", reference="R1")
        assert Payment.query.filter_by(order_id=order.id).count() == 2

class TestRequestBillRoute:
    def test_orders_order_id_request_bill_post_exists(self, client):
        rules = [r for r in app.url_map.iter_rules() if r.rule == "/orders/<int:order_id>/request-bill"]
        assert rules, "Route /orders/<int:order_id>/request-bill not registered"
        assert any("POST" in r.methods for r in rules), "Route /orders/<int:order_id>/request-bill must accept POST"

    def test_orders_order_id_request_bill_post_success(self, client):
        with app.app_context():
            order = _create_order(status="open", total_amount=Decimal("20.00"), table_no="A1")

        with patch("controllers.request_bill_controller.notify_hall_manager_bill_requested") as mock_notify:
            response = client.post(f"/orders/{order.id}/request-bill", data={})
            assert response.status_code in {200, 201, 302}
            with app.app_context():
                refreshed = Order.query.filter_by(id=order.id).first()
                assert refreshed is not None
                assert str(refreshed.status).lower() in {
                    "bill_requested",
                    "requested",
                    "bill-requested",
                    "bill requested",
                    "paid",
                }
                br = BillRequest.query.filter_by(order_id=order.id).order_by(BillRequest.id.desc()).first()
                assert br is not None
            assert mock_notify.called, "SRS requires notifying hall manager when bill is requested"

    def test_orders_order_id_request_bill_post_missing_required_fields(self, client):
        with app.app_context():
            order = _create_order(status="open")

        response = client.post(f"/orders/{order.id}/request-bill", data={"unexpected": "x"})
        assert response.status_code in {200, 400, 422}

    def test_orders_order_id_request_bill_post_invalid_data(self, client):
        response = client.post("/orders/999999999/request-bill", data={})
        assert response.status_code in {404, 400}

    def test_orders_order_id_request_bill_post_duplicate_data(self, client):
        with app.app_context():
            order = _create_order(status="open")

        client.post(f"/orders/{order.id}/request-bill", data={})
        response2 = client.post(f"/orders/{order.id}/request-bill", data={})
        assert response2.status_code in {200, 201, 302, 400, 409}
        with app.app_context():
            count = BillRequest.query.filter_by(order_id=order.id).count()
            assert count >= 1

class TestManagerBillRequestsRoute:
    def test_manager_bill_requests_get_exists(self, client):
        rules = [r for r in app.url_map.iter_rules() if r.rule == "/manager/bill-requests"]
        assert rules, "Route /manager/bill-requests not registered"
        assert any("GET" in r.methods for r in rules), "Route /manager/bill-requests must accept GET"

    def test_manager_bill_requests_get_renders_template(self, client):
        with app.app_context():
            order = _create_order(status="bill_requested", table_no="B2", total_amount=Decimal("33.33"))
            _create_bill_request(order_id=order.id, status="pending")

        response = client.get("/manager/bill-requests")
        assert response.status_code == 200
        body = (response.data or b"").lower()
        assert b"order" in body or b"table" in body or b"total" in body

class TestProcessPaymentRoute:
    def test_manager_orders_order_id_pay_post_exists(self, client):
        rules = [r for r in app.url_map.iter_rules() if r.rule == "/manager/orders/<int:order_id>/pay"]
        assert rules, "Route /manager/orders/<int:order_id>/pay not registered"
        assert any("POST" in r.methods for r in rules), "Route /manager/orders/<int:order_id>/pay must accept POST"

    def test_manager_orders_order_id_pay_post_success(self, client):
        with app.app_context():
            order = _create_order(status="bill_requested", total_amount=Decimal("45.00"))

        response = client.post(
            f"/manager/orders/{order.id}/pay",
            data={"amount": "45.00", "method": "cash", "reference": "REF123"},
        )
        assert response.status_code in {200, 201, 302}
        with app.app_context():
            refreshed = Order.query.filter_by(id=order.id).first()
            assert refreshed is not None
            assert str(refreshed.status).lower() in {"paid"}
            payment = Payment.query.filter_by(order_id=order.id).order_by(Payment.id.desc()).first()
            assert payment is not None
            assert payment.amount is not None

    def test_manager_orders_order_id_pay_post_missing_required_fields(self, client):
        with app.app_context():
            order = _create_order(status="bill_requested", total_amount=Decimal("10.00"))

        response = client.post(f"/manager/orders/{order.id}/pay", data={})
        assert response.status_code in {200, 400, 422}

    def test_manager_orders_order_id_pay_post_invalid_data(self, client):
        with app.app_context():
            order = _create_order(status="bill_requested", total_amount=Decimal("10.00"))

        response = client.post(
            f"/manager/orders/{order.id}/pay",
            data={"amount": "not-a-number", "method": "cash"},
        )
        assert response.status_code in {200, 400, 422}

    def test_manager_orders_order_id_pay_post_duplicate_data(self, client):
        with app.app_context():
            order = _create_order(status="bill_requested", total_amount=Decimal("12.00"))

        r1 = client.post(
            f"/manager/orders/{order.id}/pay",
            data={"amount": "12.00", "method": "cash", "reference": "DUPREF"},
        )
        assert r1.status_code in {200, 201, 302}

        r2 = client.post(
            f"/manager/orders/{order.id}/pay",
            data={"amount": "12.00", "method": "cash", "reference": "DUPREF"},
        )
        assert r2.status_code in {200, 201, 302, 400, 409}
        with app.app_context():
            count = Payment.query.filter_by(order_id=order.id).count()
            assert count >= 1

class TestHelpersNotifyHallManager:
    def test_notify_hall_manager_bill_requested_function_exists(self):
        assert callable(notify_hall_manager_bill_requested)

    def test_notify_hall_manager_bill_requested_with_valid_input(self, app_context):
        order = _create_order(status="open")
        br = _create_bill_request(order_id=order.id, status="pending")
        result = notify_hall_manager_bill_requested(order, br)
        assert result is None or isinstance(result, (bool, str, dict))

    def test_notify_hall_manager_bill_requested_with_invalid_input(self):
        with pytest.raises(Exception):
            notify_hall_manager_bill_requested(None, None)

class TestHelpersPrintBill:
    def test_print_bill_function_exists(self):
        assert callable(print_bill)

    def test_print_bill_with_valid_input(self, app_context):
        order = _create_order(status="bill_requested", table_no="C3", total_amount=Decimal("99.99"))
        bill_text = print_bill(order)
        assert isinstance(bill_text, str)
        assert bill_text.strip() != ""
        lowered = bill_text.lower()
        assert "order" in lowered or "table" in lowered or "total" in lowered

    def test_print_bill_with_invalid_input(self):
        with pytest.raises(Exception):
            print_bill(None)

class TestHelpersSerializeManagerBillRequest:
    def test_serialize_manager_bill_request_function_exists(self):
        assert callable(serialize_manager_bill_request)

    def test_serialize_manager_bill_request_with_valid_input(self, app_context):
        order = _create_order(status="bill_requested", table_no="D4", total_amount=Decimal("10.10"))
        br = _create_bill_request(order_id=order.id, status="pending")
        payload = serialize_manager_bill_request(order, br)
        assert isinstance(payload, dict)
        keys = set(payload.keys())
        expected = {"order_no", "table_no", "total_amount"}
        assert expected.issubset(keys), "SRS requires order no, table no, and total payable amount for manager view"

    def test_serialize_manager_bill_request_with_invalid_input(self):
        with pytest.raises(Exception):
            serialize_manager_bill_request(None, None)