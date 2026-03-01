import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.customer_help_request import CustomerHelpRequest
from controllers.customer_help_controller import validate_help_request_payload, notify_hall_manager
from views.customer_help_views import render_help_page

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

def _unique_request_payload():
    # request_type length constraint is String(30)
    token = uuid.uuid4().hex[:8]
    return {
        "table_number": 1,
        "request_type": f"help_{token}",
        "message": f"Need assistance {token}",
    }

def _create_help_request_in_db(payload=None, status="open"):
    if payload is None:
        payload = _unique_request_payload()
    created_at = datetime.now(timezone.utc)
    req = CustomerHelpRequest(
        table_number=payload["table_number"],
        request_type=payload["request_type"],
        message=payload.get("message"),
        status=status,
        created_at=created_at,
        resolved_at=None,
    )
    db.session.add(req)
    db.session.commit()
    return req

class TestCustomerHelpRequestModel:
    def test_customerhelprequest_model_has_required_fields(self, app_context):
        required_fields = [
            "id",
            "table_number",
            "request_type",
            "message",
            "status",
            "created_at",
            "resolved_at",
        ]
        for field in required_fields:
            assert hasattr(CustomerHelpRequest, field), f"Missing field: {field}"

    def test_customerhelprequest_mark_resolved(self, app_context):
        req = _create_help_request_in_db()
        resolved_at = datetime.now(timezone.utc)

        assert hasattr(req, "mark_resolved") and callable(req.mark_resolved)

        req.mark_resolved(resolved_at)
        db.session.commit()

        refreshed = CustomerHelpRequest.query.filter_by(id=req.id).first()
        assert refreshed is not None
        assert refreshed.resolved_at is not None
        assert refreshed.resolved_at == resolved_at
        assert refreshed.status is not None
        assert str(refreshed.status).lower() in {"resolved", "closed", "done"}

    def test_customerhelprequest_to_dict(self, app_context):
        payload = _unique_request_payload()
        req = _create_help_request_in_db(payload=payload, status="open")

        assert hasattr(req, "to_dict") and callable(req.to_dict)

        data = req.to_dict()
        assert isinstance(data, dict)

        for key in ["id", "table_number", "request_type", "message", "status", "created_at", "resolved_at"]:
            assert key in data, f"to_dict missing key: {key}"

        assert data["id"] == req.id
        assert data["table_number"] == payload["table_number"]
        assert data["request_type"] == payload["request_type"]
        assert data["message"] == payload["message"]
        assert data["status"] == req.status

    def test_customerhelprequest_unique_constraints(self, app_context):
        payload = _unique_request_payload()
        req1 = _create_help_request_in_db(payload=payload)
        req2 = _create_help_request_in_db(payload=payload)
        assert req1.id != req2.id
        assert CustomerHelpRequest.query.filter_by(request_type=payload["request_type"]).count() == 2

class TestHelpRoutes:
    def test_help_get_exists(self, client):
        response = client.get("/help")
        assert response.status_code != 404

    def test_help_get_renders_template(self, client):
        response = client.get("/help")
        assert response.status_code == 200
        assert response.mimetype in {"text/html", "text/html; charset=utf-8"}
        assert len(response.data) > 0

class TestCreateHelpRequestRoute:
    def test_api_help_requests_post_exists(self, client):
        response = client.post("/api/help/requests", json=_unique_request_payload())
        assert response.status_code != 404

    def test_api_help_requests_post_success(self, client, app_context):
        payload = _unique_request_payload()
        with patch("controllers.customer_help_controller.notify_hall_manager") as mock_notify:
            response = client.post("/api/help/requests", json=payload)
            assert response.status_code in {200, 201}

            data = response.get_json(silent=True)
            assert isinstance(data, dict)

            returned_id = data.get("id") or data.get("request", {}).get("id")
            assert returned_id is not None

            created = CustomerHelpRequest.query.filter_by(id=returned_id).first()
            assert created is not None
            assert created.table_number == payload["table_number"]
            assert created.request_type == payload["request_type"]
            assert created.message == payload["message"]
            assert created.status is not None
            assert str(created.status).lower() in {"open", "pending", "new"}

            mock_notify.assert_called_once()

    def test_api_help_requests_post_missing_required_fields(self, client):
        response = client.post("/api/help/requests", json={"message": "hi"})
        assert response.status_code in {400, 422}

        data = response.get_json(silent=True)
        assert isinstance(data, dict)

    def test_api_help_requests_post_invalid_data(self, client):
        payload = _unique_request_payload()
        payload["table_number"] = "not-an-int"
        response = client.post("/api/help/requests", json=payload)
        assert response.status_code in {400, 422}

    def test_api_help_requests_post_duplicate_data(self, client, app_context):
        payload = _unique_request_payload()
        with patch("controllers.customer_help_controller.notify_hall_manager"):
            r1 = client.post("/api/help/requests", json=payload)
            r2 = client.post("/api/help/requests", json=payload)

        assert r1.status_code in {200, 201}
        assert r2.status_code in {200, 201, 400, 409, 422}

        count = CustomerHelpRequest.query.filter_by(
            table_number=payload["table_number"],
            request_type=payload["request_type"],
            message=payload["message"],
        ).count()
        assert count in {1, 2}

class TestGetHelpRequestRoute:
    def test_api_help_requests_request_id_get_exists(self, client, app_context):
        req = _create_help_request_in_db()
        response = client.get(f"/api/help/requests/{req.id}")
        assert response.status_code != 404

    def test_api_help_requests_request_id_get_renders_template(self, client, app_context):
        req = _create_help_request_in_db()
        response = client.get(f"/api/help/requests/{req.id}")
        assert response.status_code == 200

        # Accept either HTML template rendering or JSON response
        if response.mimetype and "json" in response.mimetype:
            data = response.get_json(silent=True)
            assert isinstance(data, dict)
            returned_id = data.get("id") or data.get("request", {}).get("id")
            assert returned_id == req.id
        else:
            assert response.mimetype in {"text/html", "text/html; charset=utf-8"}
            assert len(response.data) > 0

class TestResolveHelpRequestRoute:
    def test_api_help_requests_request_id_resolve_post_exists(self, client, app_context):
        req = _create_help_request_in_db()
        response = client.post(f"/api/help/requests/{req.id}/resolve", json={})
        assert response.status_code != 404

    def test_api_help_requests_request_id_resolve_post_success(self, client, app_context):
        req = _create_help_request_in_db()
        response = client.post(f"/api/help/requests/{req.id}/resolve", json={})
        assert response.status_code in {200, 204}

        refreshed = CustomerHelpRequest.query.filter_by(id=req.id).first()
        assert refreshed is not None
        assert refreshed.resolved_at is not None
        assert refreshed.status is not None
        assert str(refreshed.status).lower() in {"resolved", "closed", "done"}

    def test_api_help_requests_request_id_resolve_post_missing_required_fields(self, client, app_context):
        req = _create_help_request_in_db()
        response = client.post(f"/api/help/requests/{req.id}/resolve")
        assert response.status_code in {200, 204, 400, 415}

    def test_api_help_requests_request_id_resolve_post_invalid_data(self, client, app_context):
        req = _create_help_request_in_db()
        response = client.post(f"/api/help/requests/{req.id}/resolve", json={"resolved_at": "not-a-datetime"})
        assert response.status_code in {200, 204, 400, 422}

    def test_api_help_requests_request_id_resolve_post_duplicate_data(self, client, app_context):
        req = _create_help_request_in_db()
        r1 = client.post(f"/api/help/requests/{req.id}/resolve", json={})
        r2 = client.post(f"/api/help/requests/{req.id}/resolve", json={})

        assert r1.status_code in {200, 204}
        assert r2.status_code in {200, 204, 400, 409, 422}

        refreshed = CustomerHelpRequest.query.filter_by(id=req.id).first()
        assert refreshed is not None
        assert refreshed.resolved_at is not None
        assert str(refreshed.status).lower() in {"resolved", "closed", "done"}

class TestValidateHelpRequestPayloadHelper:
    def test_validate_help_request_payload_function_exists(self):
        assert callable(validate_help_request_payload)

    def test_validate_help_request_payload_with_valid_input(self):
        payload = _unique_request_payload()
        result = validate_help_request_payload(payload)
        assert isinstance(result, dict)
        assert result.get("table_number") == payload["table_number"]
        assert result.get("request_type") == payload["request_type"]
        assert result.get("message") == payload["message"]

    def test_validate_help_request_payload_with_invalid_input(self):
        with pytest.raises((ValueError, TypeError, KeyError)):
            validate_help_request_payload({"table_number": "x"})

class TestNotifyHallManagerHelper:
    def test_notify_hall_manager_function_exists(self):
        assert callable(notify_hall_manager)

    def test_notify_hall_manager_with_valid_input(self, app_context):
        req = _create_help_request_in_db()
        # Should not raise for valid input; external side effects should be handled internally
        notify_hall_manager(req)

    def test_notify_hall_manager_with_invalid_input(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            notify_hall_manager(None)