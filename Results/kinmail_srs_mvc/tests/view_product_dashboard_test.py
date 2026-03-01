import os
import sys
import uuid
from decimal import Decimal
from datetime import datetime
import inspect

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.product import Product
from models.view_product_dashboard_buy_request import ViewProductDashboardBuyRequest
from models.view_product_dashboard_offer import ViewProductDashboardOffer
from controllers.view_product_dashboard_controller import (
    get_current_user_id,
    compute_dashboard_counts,
    sse_format,
)
from views.view_product_dashboard_views import render_dashboard

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

def _create_user(email=None, username=None, password="Password123!"):
    if email is None:
        email = f"{_unique('user')}@example.com"
    if username is None:
        username = _unique("user")
    u = User(email=email, username=username)
    if hasattr(u, "set_password") and callable(getattr(u, "set_password")):
        u.set_password(password)
    else:
        u.password_hash = "hash"
    if hasattr(User, "created_at") and getattr(u, "created_at", None) is None:
        u.created_at = datetime.utcnow()
    db.session.add(u)
    db.session.commit()
    return u

def _create_product(seller_id: int, title=None, price=Decimal("10.00"), status="active"):
    if title is None:
        title = _unique("product")
    p = Product(
        seller_id=seller_id,
        title=title,
        description="desc",
        price=price,
        status=status,
    )
    if hasattr(Product, "created_at") and getattr(p, "created_at", None) is None:
        p.created_at = datetime.utcnow()
    if hasattr(Product, "updated_at") and getattr(p, "updated_at", None) is None:
        p.updated_at = datetime.utcnow()
    db.session.add(p)
    db.session.commit()
    return p

def _create_buy_request(buyer_id: int, product_id: int, quantity=1, status="pending"):
    br = ViewProductDashboardBuyRequest(
        buyer_id=buyer_id,
        product_id=product_id,
        quantity=quantity,
        status=status,
    )
    if hasattr(ViewProductDashboardBuyRequest, "created_at") and getattr(br, "created_at", None) is None:
        br.created_at = datetime.utcnow()
    db.session.add(br)
    db.session.commit()
    return br

def _create_offer(buyer_id: int, product_id: int, offer_price=Decimal("9.50"), status="pending"):
    off = ViewProductDashboardOffer(
        buyer_id=buyer_id,
        product_id=product_id,
        offer_price=offer_price,
        message="msg",
        status=status,
    )
    if hasattr(ViewProductDashboardOffer, "created_at") and getattr(off, "created_at", None) is None:
        off.created_at = datetime.utcnow()
    db.session.add(off)
    db.session.commit()
    return off

# MODEL: User (models/user.py)
def test_user_model_has_required_fields(app_context):
    for field in ["id", "email", "username", "password_hash", "created_at"]:
        assert hasattr(User, field), f"Missing required User field: {field}"

def test_user_set_password(app_context):
    u = User(email=f"{_unique('u')}@example.com", username=_unique("u"))
    assert hasattr(u, "set_password") and callable(getattr(u, "set_password"))
    u.set_password("MySecret123!")
    assert getattr(u, "password_hash", None)
    assert u.password_hash != "MySecret123!"

def test_user_check_password(app_context):
    u = User(email=f"{_unique('u')}@example.com", username=_unique("u"))
    assert hasattr(u, "set_password") and callable(getattr(u, "set_password"))
    assert hasattr(u, "check_password") and callable(getattr(u, "check_password"))
    u.set_password("MySecret123!")
    assert u.check_password("MySecret123!") is True
    assert u.check_password("WrongPassword!") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")
    u1 = User(email=email, username=username)
    if hasattr(u1, "set_password") and callable(getattr(u1, "set_password")):
        u1.set_password("Password123!")
    else:
        u1.password_hash = "hash"
    if hasattr(User, "created_at") and getattr(u1, "created_at", None) is None:
        u1.created_at = datetime.utcnow()
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("otheruser"))
    if hasattr(u2, "set_password") and callable(getattr(u2, "set_password")):
        u2.set_password("Password123!")
    else:
        u2.password_hash = "hash"
    if hasattr(User, "created_at") and getattr(u2, "created_at", None) is None:
        u2.created_at = datetime.utcnow()
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username)
    if hasattr(u3, "set_password") and callable(getattr(u3, "set_password")):
        u3.set_password("Password123!")
    else:
        u3.password_hash = "hash"
    if hasattr(User, "created_at") and getattr(u3, "created_at", None) is None:
        u3.created_at = datetime.utcnow()
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: Product (models/product.py)
def test_product_model_has_required_fields(app_context):
    for field in [
        "id",
        "seller_id",
        "title",
        "description",
        "price",
        "status",
        "created_at",
        "updated_at",
    ]:
        assert hasattr(Product, field), f"Missing required Product field: {field}"

def test_product_unique_constraints(app_context):
    u = _create_user()
    title = _unique("same_title")
    _create_product(seller_id=u.id, title=title, price=Decimal("1.00"))
    _create_product(seller_id=u.id, title=title, price=Decimal("2.00"))
    assert Product.query.filter_by(seller_id=u.id, title=title).count() == 2

# MODEL: ViewProductDashboardBuyRequest (models/view_product_dashboard_buy_request.py)
def test_viewproductdashboardbuyrequest_model_has_required_fields(app_context):
    for field in ["id", "buyer_id", "product_id", "quantity", "status", "created_at"]:
        assert hasattr(ViewProductDashboardBuyRequest, field), f"Missing required BuyRequest field: {field}"

def test_viewproductdashboardbuyrequest_unique_constraints(app_context):
    buyer = _create_user()
    seller = _create_user()
    p = _create_product(seller_id=seller.id)
    _create_buy_request(buyer_id=buyer.id, product_id=p.id, quantity=1)
    _create_buy_request(buyer_id=buyer.id, product_id=p.id, quantity=2)
    assert (
        ViewProductDashboardBuyRequest.query.filter_by(buyer_id=buyer.id, product_id=p.id).count() == 2
    )

# MODEL: ViewProductDashboardOffer (models/view_product_dashboard_offer.py)
def test_viewproductdashboardoffer_model_has_required_fields(app_context):
    for field in ["id", "buyer_id", "product_id", "offer_price", "message", "status", "created_at"]:
        assert hasattr(ViewProductDashboardOffer, field), f"Missing required Offer field: {field}"

def test_viewproductdashboardoffer_unique_constraints(app_context):
    buyer = _create_user()
    seller = _create_user()
    p = _create_product(seller_id=seller.id)
    _create_offer(buyer_id=buyer.id, product_id=p.id, offer_price=Decimal("3.00"))
    _create_offer(buyer_id=buyer.id, product_id=p.id, offer_price=Decimal("4.00"))
    assert ViewProductDashboardOffer.query.filter_by(buyer_id=buyer.id, product_id=p.id).count() == 2

# ROUTE: /dashboard (GET) - dashboard_page
def test_dashboard_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/dashboard"]
    assert rules, "Route /dashboard is missing"
    methods = set()
    for r in rules:
        methods |= set(r.methods or [])
    assert "GET" in methods

def test_dashboard_get_renders_template(client):
    resp = client.get("/dashboard")
    assert resp.status_code in (200, 302, 401)
    if resp.status_code == 200:
        ct = resp.headers.get("Content-Type", "")
        assert "text/html" in ct or "application/xhtml+xml" in ct or ct.startswith("text/")

# ROUTE: /api/dashboard/summary (GET) - get_dashboard_summary
def test_api_dashboard_summary_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/api/dashboard/summary"]
    assert rules, "Route /api/dashboard/summary is missing"
    methods = set()
    for r in rules:
        methods |= set(r.methods or [])
    assert "GET" in methods

def test_api_dashboard_summary_get_renders_template(client):
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code in (200, 401)
    if resp.status_code == 401:
        assert resp.is_json
        data = resp.get_json()
        assert data == {"error": "unauthorized"}
    else:
        assert resp.is_json
        data = resp.get_json()
        assert isinstance(data, dict)

# ROUTE: /api/dashboard/stream (GET) - dashboard_stream
def test_api_dashboard_stream_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/api/dashboard/stream"]
    assert rules, "Route /api/dashboard/stream is missing"
    methods = set()
    for r in rules:
        methods |= set(r.methods or [])
    assert "GET" in methods

def test_api_dashboard_stream_get_renders_template(client):
    resp = client.get("/api/dashboard/stream")
    assert resp.status_code in (200, 401)
    if resp.status_code == 401:
        assert resp.is_json
        data = resp.get_json()
        assert data == {"error": "unauthorized"}
    else:
        ct = resp.headers.get("Content-Type", "")
        assert "text/event-stream" in ct or "text/plain" in ct or ct.startswith("text/")

# HELPER: get_current_user_id(session)
def test_get_current_user_id_function_exists():
    assert callable(get_current_user_id)
    sig = inspect.signature(get_current_user_id)
    assert len(sig.parameters) == 1
    assert "session" in sig.parameters

def test_get_current_user_id_with_valid_input():
    sess = {"user_id": 123}
    result = get_current_user_id(sess)
    assert result == 123

def test_get_current_user_id_with_invalid_input():
    assert get_current_user_id({}) is None
    assert get_current_user_id(None) is None
    assert get_current_user_id({"user_id": "not-an-int"}) is None

# HELPER: compute_dashboard_counts(user_id: int)
def test_compute_dashboard_counts_function_exists():
    assert callable(compute_dashboard_counts)
    sig = inspect.signature(compute_dashboard_counts)
    assert len(sig.parameters) == 1
    assert "user_id" in sig.parameters

def test_compute_dashboard_counts_with_valid_input(app_context):
    seller = _create_user()
    buyer = _create_user()

    p1 = _create_product(seller_id=seller.id, price=Decimal("10.00"))
    p2 = _create_product(seller_id=seller.id, price=Decimal("20.00"))
    _create_product(seller_id=_create_user().id, price=Decimal("30.00"))

    _create_buy_request(buyer_id=buyer.id, product_id=p1.id, quantity=1)
    _create_buy_request(buyer_id=buyer.id, product_id=p2.id, quantity=2)
    _create_buy_request(buyer_id=_create_user().id, product_id=p1.id, quantity=1)

    _create_offer(buyer_id=buyer.id, product_id=p1.id, offer_price=Decimal("9.00"))
    _create_offer(buyer_id=_create_user().id, product_id=p1.id, offer_price=Decimal("8.50"))

    counts = compute_dashboard_counts(seller.id)
    assert isinstance(counts, dict)

    required_keys = {"selling_count", "buy_requests_count", "offers_received_count"}
    missing = required_keys - set(counts.keys())
    assert not missing, f"compute_dashboard_counts must return keys: {sorted(required_keys)}"

    assert counts["selling_count"] == 2
    assert counts["buy_requests_count"] == 0
    assert counts["offers_received_count"] == 2

def test_compute_dashboard_counts_with_invalid_input(app_context):
    with pytest.raises((TypeError, ValueError)):
        compute_dashboard_counts(None)
    with pytest.raises((TypeError, ValueError)):
        compute_dashboard_counts("1")

# HELPER: sse_format(event: str, data: dict)
def test_sse_format_function_exists():
    assert callable(sse_format)
    sig = inspect.signature(sse_format)
    assert len(sig.parameters) == 2
    assert "event" in sig.parameters
    assert "data" in sig.parameters

def test_sse_format_with_valid_input():
    payload = {"a": 1, "b": "x"}
    out = sse_format("summary", payload)
    assert isinstance(out, str)
    assert "event:" in out
    assert "data:" in out
    assert "summary" in out
    assert "\n\n" in out

def test_sse_format_with_invalid_input():
    with pytest.raises((TypeError, ValueError)):
        sse_format(None, {"a": 1})
    with pytest.raises((TypeError, ValueError)):
        sse_format("summary", None)
    with pytest.raises((TypeError, ValueError)):
        sse_format("summary", "not-a-dict")