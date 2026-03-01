import os
import sys
import uuid
import re
from decimal import Decimal
from datetime import datetime
import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.view_product_details_product import Product
from models.view_product_details_seller import Seller
from models.view_product_details_product_offer import ProductOffer
from controllers.view_product_details_controller import (
    select_primary_offer,
    build_product_details_payload,
)
from views.view_product_details_views import render_product_details_page

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

def _create_product(*, sku=None, name=None, is_active=True):
    now = datetime.utcnow()
    return Product(
        sku=sku or _unique("SKU"),
        name=name or _unique("Product"),
        brand="BrandX",
        category="CategoryY",
        condition="new",
        description="A product description",
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )

def _create_seller(*, display_name=None):
    now = datetime.utcnow()
    return Seller(
        display_name=display_name or _unique("Seller"),
        rating_average=4.5,
        rating_count=10,
        support_email="support@example.com",
        support_phone="+10000000000",
        is_verified=True,
        created_at=now,
    )

def _create_offer(*, product_id, seller_id, is_active=True, sale_price=Decimal("9.99")):
    now = datetime.utcnow()
    return ProductOffer(
        product_id=product_id,
        seller_id=seller_id,
        currency="USD",
        list_price=Decimal("19.99"),
        sale_price=sale_price,
        stock_quantity=5,
        delivery_fee=Decimal("0.00"),
        delivery_estimate_days_min=2,
        delivery_estimate_days_max=5,
        warranty_months=12,
        warranty_terms="Manufacturer warranty",
        return_policy="30-day returns",
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )

class TestProductModel:
    def test_product_model_has_required_fields(self):
        for field in [
            "id",
            "sku",
            "name",
            "brand",
            "category",
            "condition",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]:
            assert hasattr(Product, field), f"Missing Product field: {field}"

    def test_product_to_general_details_dict(self, app_context):
        p = _create_product()
        db.session.add(p)
        db.session.commit()

        assert hasattr(p, "to_general_details_dict")
        data = p.to_general_details_dict()
        assert isinstance(data, dict)

        for key in ["id", "sku", "name", "brand", "category", "condition", "is_active"]:
            assert key in data, f"Missing key in general details: {key}"

        assert data["id"] == p.id
        assert data["sku"] == p.sku
        assert data["name"] == p.name
        assert data["brand"] == p.brand
        assert data["category"] == p.category
        assert data["condition"] == p.condition
        assert data["is_active"] == p.is_active

    def test_product_to_description_dict(self, app_context):
        p = _create_product()
        p.description = "Detailed description"
        db.session.add(p)
        db.session.commit()

        assert hasattr(p, "to_description_dict")
        data = p.to_description_dict()
        assert isinstance(data, dict)
        assert "text" in data
        assert data["text"] == p.description

    def test_product_unique_constraints(self, app_context):
        sku = _unique("SKU_UNIQ")
        p1 = _create_product(sku=sku, name=_unique("P1"))
        p2 = _create_product(sku=sku, name=_unique("P2"))
        db.session.add(p1)
        db.session.commit()

        db.session.add(p2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

class TestSellerModel:
    def test_seller_model_has_required_fields(self):
        for field in [
            "id",
            "display_name",
            "rating_average",
            "rating_count",
            "support_email",
            "support_phone",
            "is_verified",
            "created_at",
        ]:
            assert hasattr(Seller, field), f"Missing Seller field: {field}"

    def test_seller_to_seller_details_dict(self, app_context):
        s = _create_seller()
        db.session.add(s)
        db.session.commit()

        assert hasattr(s, "to_seller_details_dict")
        data = s.to_seller_details_dict()
        assert isinstance(data, dict)

        for key in [
            "id",
            "display_name",
            "rating_average",
            "rating_count",
            "is_verified",
            "support_email",
            "support_phone",
        ]:
            assert key in data, f"Missing key in seller details: {key}"

        assert data["id"] == s.id
        assert data["display_name"] == s.display_name
        assert data["rating_average"] == s.rating_average
        assert data["rating_count"] == s.rating_count
        assert data["is_verified"] == s.is_verified
        assert data["support_email"] == s.support_email
        assert data["support_phone"] == s.support_phone

    def test_seller_unique_constraints(self, app_context):
        name = _unique("SellerSameName")
        s1 = _create_seller(display_name=name)
        s2 = _create_seller(display_name=name)
        db.session.add_all([s1, s2])
        db.session.commit()
        assert s1.id is not None
        assert s2.id is not None

class TestProductOfferModel:
    def test_productoffer_model_has_required_fields(self):
        for field in [
            "id",
            "product_id",
            "seller_id",
            "currency",
            "list_price",
            "sale_price",
            "stock_quantity",
            "delivery_fee",
            "delivery_estimate_days_min",
            "delivery_estimate_days_max",
            "warranty_months",
            "warranty_terms",
            "return_policy",
            "is_active",
            "created_at",
            "updated_at",
        ]:
            assert hasattr(ProductOffer, field), f"Missing ProductOffer field: {field}"

    def test_productoffer_to_pricing_delivery_warranty_dict(self, app_context):
        p = _create_product()
        s = _create_seller()
        db.session.add_all([p, s])
        db.session.commit()

        offer = _create_offer(product_id=p.id, seller_id=s.id)
        db.session.add(offer)
        db.session.commit()

        assert hasattr(offer, "to_pricing_delivery_warranty_dict")
        data = offer.to_pricing_delivery_warranty_dict()
        assert isinstance(data, dict)

        for top_key in ["pricing", "delivery", "warranty"]:
            assert top_key in data, f"Missing top-level key: {top_key}"

        pricing = data["pricing"]
        delivery = data["delivery"]
        warranty = data["warranty"]

        for key in ["currency", "list_price", "sale_price"]:
            assert key in pricing, f"Missing pricing key: {key}"
        for key in ["delivery_fee", "estimate_days_min", "estimate_days_max"]:
            assert key in delivery, f"Missing delivery key: {key}"
        for key in ["warranty_months", "warranty_terms"]:
            assert key in warranty, f"Missing warranty key: {key}"

        assert pricing["currency"] == offer.currency
        assert isinstance(pricing["sale_price"], str)
        assert re.match(r"^-?\d+\.\d{2}$", pricing["sale_price"]) is not None
        if pricing["list_price"] is not None:
            assert re.match(r"^-?\d+\.\d{2}$", pricing["list_price"]) is not None

        assert isinstance(delivery["delivery_fee"], str)
        assert re.match(r"^-?\d+\.\d{2}$", delivery["delivery_fee"]) is not None
        assert delivery["estimate_days_min"] == offer.delivery_estimate_days_min
        assert delivery["estimate_days_max"] == offer.delivery_estimate_days_max

        assert warranty["warranty_months"] == offer.warranty_months
        assert warranty["warranty_terms"] == offer.warranty_terms

    def test_productoffer_unique_constraints(self, app_context):
        p = _create_product()
        s = _create_seller()
        db.session.add_all([p, s])
        db.session.commit()

        o1 = _create_offer(product_id=p.id, seller_id=s.id, sale_price=Decimal("9.99"))
        o2 = _create_offer(product_id=p.id, seller_id=s.id, sale_price=Decimal("8.99"))
        db.session.add_all([o1, o2])
        db.session.commit()
        assert o1.id is not None
        assert o2.id is not None

class TestRoutes:
    def test_products_product_id_get_exists(self, client):
        rules = [r for r in app.url_map.iter_rules() if r.rule == "/products/<int:product_id>"]
        assert rules, "Route /products/<int:product_id> is missing"
        assert any("GET" in r.methods for r in rules), "Route /products/<int:product_id> does not accept GET"

    def test_products_product_id_get_renders_template(self, client):
        with app.app_context():
            p = _create_product(is_active=True)
            s = _create_seller()
            db.session.add_all([p, s])
            db.session.commit()
            offer = _create_offer(product_id=p.id, seller_id=s.id, is_active=True)
            db.session.add(offer)
            db.session.commit()

        resp = client.get(f"/products/{p.id}")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")
        data = resp.get_json()
        assert isinstance(data, dict)

        for key in ["product", "seller", "pricing", "delivery", "warranty"]:
            assert key in data, f"Missing response key: {key}"

        assert data["product"]["id"] == p.id
        assert data["product"]["sku"] == p.sku
        assert data["product"]["name"] == p.name

        assert re.match(r"^-?\d+\.\d{2}$", data["pricing"]["sale_price"]) is not None
        assert re.match(r"^-?\d+\.\d{2}$", data["delivery"]["delivery_fee"]) is not None

    def test_products_product_id_view_get_exists(self, client):
        rules = [r for r in app.url_map.iter_rules() if r.rule == "/products/<int:product_id>/view"]
        assert rules, "Route /products/<int:product_id>/view is missing"
        assert any("GET" in r.methods for r in rules), "Route /products/<int:product_id>/view does not accept GET"

    def test_products_product_id_view_get_renders_template(self, client):
        with app.app_context():
            p = _create_product(is_active=True)
            s = _create_seller()
            db.session.add_all([p, s])
            db.session.commit()
            offer = _create_offer(product_id=p.id, seller_id=s.id, is_active=True)
            db.session.add(offer)
            db.session.commit()

        resp = client.get(f"/products/{p.id}/view")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/html")
        assert len(resp.data) > 0

class TestHelpersSelectPrimaryOffer:
    def test_select_primary_offer_function_exists(self):
        assert callable(select_primary_offer)

    def test_select_primary_offer_with_valid_input(self, app_context):
        p = _create_product()
        s = _create_seller()
        db.session.add_all([p, s])
        db.session.commit()

        o1 = _create_offer(product_id=p.id, seller_id=s.id, sale_price=Decimal("10.00"))
        o2 = _create_offer(product_id=p.id, seller_id=s.id, sale_price=Decimal("9.00"))
        db.session.add_all([o1, o2])
        db.session.commit()

        selected = select_primary_offer([o1, o2])
        assert selected is not None
        assert isinstance(selected, ProductOffer)

    def test_select_primary_offer_with_invalid_input(self):
        assert select_primary_offer([]) is None
        assert select_primary_offer(None) is None

class TestHelpersBuildProductDetailsPayload:
    def test_build_product_details_payload_function_exists(self):
        assert callable(build_product_details_payload)

    def test_build_product_details_payload_with_valid_input(self, app_context):
        p = _create_product()
        s = _create_seller()
        db.session.add_all([p, s])
        db.session.commit()

        offer = _create_offer(product_id=p.id, seller_id=s.id)
        db.session.add(offer)
        db.session.commit()

        payload = build_product_details_payload(p, offer)
        assert isinstance(payload, dict)

        for key in ["product", "seller", "pricing", "delivery", "warranty"]:
            assert key in payload, f"Missing payload key: {key}"

        assert isinstance(payload["product"], dict)
        assert isinstance(payload["seller"], dict)
        assert isinstance(payload["pricing"], dict)
        assert isinstance(payload["delivery"], dict)
        assert isinstance(payload["warranty"], dict)

        for key in ["id", "sku", "name", "brand", "category", "condition", "is_active"]:
            assert key in payload["product"], f"Missing product key: {key}"

        for key in [
            "id",
            "display_name",
            "rating_average",
            "rating_count",
            "is_verified",
            "support_email",
            "support_phone",
        ]:
            assert key in payload["seller"], f"Missing seller key: {key}"

        for key in ["currency", "list_price", "sale_price"]:
            assert key in payload["pricing"], f"Missing pricing key: {key}"
        for key in ["delivery_fee", "estimate_days_min", "estimate_days_max"]:
            assert key in payload["delivery"], f"Missing delivery key: {key}"
        for key in ["warranty_months", "warranty_terms"]:
            assert key in payload["warranty"], f"Missing warranty key: {key}"

        assert payload["product"]["id"] == p.id
        assert payload["product"]["sku"] == p.sku
        assert payload["product"]["name"] == p.name

        assert re.match(r"^-?\d+\.\d{2}$", payload["pricing"]["sale_price"]) is not None
        if payload["pricing"]["list_price"] is not None:
            assert re.match(r"^-?\d+\.\d{2}$", payload["pricing"]["list_price"]) is not None
        assert re.match(r"^-?\d+\.\d{2}$", payload["delivery"]["delivery_fee"]) is not None

    def test_build_product_details_payload_with_invalid_input(self, app_context):
        p = _create_product()
        s = _create_seller()
        db.session.add_all([p, s])
        db.session.commit()

        offer = _create_offer(product_id=p.id, seller_id=s.id)
        db.session.add(offer)
        db.session.commit()

        with pytest.raises(Exception):
            build_product_details_payload(None, offer)

        with pytest.raises(Exception):
            build_product_details_payload(p, None)