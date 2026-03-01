import os
import sys
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.product import Product
from models.category import Category
from controllers.view_product_details_controller import fetch_product_or_404, build_product_details_dto

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

def _create_user(email=None, username=None, password="P@ssw0rd!"):
    if email is None:
        email = f"{_unique('user')}@example.com"
    if username is None:
        username = _unique("user")
    user = User(email=email, username=username, password_hash="")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

def _create_category(name=None, slug=None, parent_id=None):
    if name is None:
        name = _unique("cat")
    if slug is None:
        slug = _unique("cat-slug")
    category = Category(name=name, slug=slug, parent_id=parent_id)
    db.session.add(category)
    db.session.commit()
    return category

def _create_product(
    *,
    seller_id: int,
    category_id: int,
    is_active: bool = True,
    sku: str | None = None,
    sale_price=None,
):
    if sku is None:
        sku = _unique("SKU")
    product = Product(
        name=_unique("Product"),
        sku=sku,
        category_id=category_id,
        seller_id=seller_id,
        short_description="Short desc",
        description="Full description",
        currency="USD",
        list_price=Decimal("100.00"),
        sale_price=sale_price,
        stock_quantity=10,
        condition="new",
        brand="BrandX",
        model_number="ModelY",
        weight_kg=Decimal("1.250"),
        dimensions_cm="10x20x30",
        delivery_method="standard",
        delivery_fee=Decimal("5.00"),
        delivery_estimated_min_days=2,
        delivery_estimated_max_days=5,
        ships_from="Warehouse A",
        return_policy="30-day returns",
        warranty_type="manufacturer",
        warranty_period_months=12,
        warranty_details="Warranty details text",
        is_active=is_active,
    )
    db.session.add(product)
    db.session.commit()
    return product

def test_user_model_has_required_fields():
    for field in ["id", "email", "username", "password_hash"]:
        assert hasattr(User, field), f"User model missing required field: {field}"

def test_user_set_password():
    user = User(email=f"{_unique('u')}@example.com", username=_unique("u"), password_hash="")
    user.set_password("secret123")
    assert user.password_hash
    assert user.password_hash != "secret123"

def test_user_check_password():
    user = User(email=f"{_unique('u')}@example.com", username=_unique("u"), password_hash="")
    user.set_password("secret123")
    assert user.check_password("secret123") is True
    assert user.check_password("wrong") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")

    u1 = User(email=email, username=username, password_hash="")
    u1.set_password("pw1")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("otheruser"), password_hash="")
    u2.set_password("pw2")
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, password_hash="")
    u3.set_password("pw3")
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

def test_product_model_has_required_fields():
    required = [
        "id",
        "name",
        "sku",
        "category_id",
        "seller_id",
        "short_description",
        "description",
        "currency",
        "list_price",
        "sale_price",
        "stock_quantity",
        "condition",
        "brand",
        "model_number",
        "weight_kg",
        "dimensions_cm",
        "delivery_method",
        "delivery_fee",
        "delivery_estimated_min_days",
        "delivery_estimated_max_days",
        "ships_from",
        "return_policy",
        "warranty_type",
        "warranty_period_months",
        "warranty_details",
        "is_active",
        "created_at",
        "updated_at",
    ]
    for field in required:
        assert hasattr(Product, field), f"Product model missing required field: {field}"

def test_product_get_effective_price(app_context):
    seller = _create_user()
    category = _create_category()

    p1 = _create_product(seller_id=seller.id, category_id=category.id, sale_price=None)
    price1 = p1.get_effective_price()
    assert isinstance(price1, Decimal)
    assert price1 == Decimal("100.00")

    p2 = _create_product(seller_id=seller.id, category_id=category.id, sku=_unique("SKU2"), sale_price=Decimal("80.00"))
    price2 = p2.get_effective_price()
    assert isinstance(price2, Decimal)
    assert price2 == Decimal("80.00")

def test_product_unique_constraints(app_context):
    seller = _create_user()
    category = _create_category()
    sku = _unique("SKU")

    _create_product(seller_id=seller.id, category_id=category.id, sku=sku)

    p2 = Product(
        name=_unique("Product"),
        sku=sku,
        category_id=category.id,
        seller_id=seller.id,
        short_description="Short desc",
        description="Full description",
        currency="USD",
        list_price=Decimal("100.00"),
        sale_price=None,
        stock_quantity=10,
        condition="new",
        brand="BrandX",
        model_number="ModelY",
        weight_kg=Decimal("1.250"),
        dimensions_cm="10x20x30",
        delivery_method="standard",
        delivery_fee=Decimal("5.00"),
        delivery_estimated_min_days=2,
        delivery_estimated_max_days=5,
        ships_from="Warehouse A",
        return_policy="30-day returns",
        warranty_type="manufacturer",
        warranty_period_months=12,
        warranty_details="Warranty details text",
        is_active=True,
    )
    db.session.add(p2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

def test_category_model_has_required_fields():
    for field in ["id", "name", "slug", "parent_id"]:
        assert hasattr(Category, field), f"Category model missing required field: {field}"

def test_category_unique_constraints(app_context):
    name = _unique("catname")
    slug = _unique("catslug")

    c1 = Category(name=name, slug=slug, parent_id=None)
    db.session.add(c1)
    db.session.commit()

    c2 = Category(name=name, slug=_unique("otherslug"), parent_id=None)
    db.session.add(c2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    c3 = Category(name=_unique("othername"), slug=slug, parent_id=None)
    db.session.add(c3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

def test_products_product_id_get_exists(client):
    seller = None
    category = None
    with app.app_context():
        seller = _create_user()
        category = _create_category()
        product = _create_product(seller_id=seller.id, category_id=category.id, is_active=True)
        product_id = product.id

    resp = client.get(f"/products/{product_id}")
    assert resp.status_code != 404

def test_products_product_id_get_renders_template(client):
    with app.app_context():
        seller = _create_user()
        category = _create_category()
        product = _create_product(seller_id=seller.id, category_id=category.id, is_active=True)
        product_id = product.id

    with patch("flask.templating._render") as mock_render:
        mock_render.return_value = "OK"
        resp = client.get(f"/products/{product_id}")
        assert resp.status_code == 200
        assert mock_render.called is True
        template_name = mock_render.call_args[0][0]
        context = mock_render.call_args[0][1]
        assert template_name == "view_product_details_product_details.html"
        assert "product_details" in context

def test_api_products_product_id_get_exists(client):
    with app.app_context():
        seller = _create_user()
        category = _create_category()
        product = _create_product(seller_id=seller.id, category_id=category.id, is_active=True)
        product_id = product.id

    resp = client.get(f"/api/products/{product_id}")
    assert resp.status_code != 404

def test_api_products_product_id_get_renders_template(client):
    with app.app_context():
        seller = _create_user()
        category = _create_category()
        product = _create_product(seller_id=seller.id, category_id=category.id, is_active=True)
        product_id = product.id

    resp = client.get(f"/api/products/{product_id}")
    assert resp.status_code == 200
    assert resp.is_json is True
    data = resp.get_json()
    assert isinstance(data, dict)

def test_fetch_product_or_404_function_exists():
    assert callable(fetch_product_or_404) is True

def test_fetch_product_or_404_with_valid_input(app_context):
    seller = _create_user()
    category = _create_category()
    product = _create_product(seller_id=seller.id, category_id=category.id, is_active=True)

    fetched = fetch_product_or_404(product.id)
    assert fetched is not None
    assert isinstance(fetched, Product)
    assert fetched.id == product.id

def test_fetch_product_or_404_with_invalid_input(app_context):
    with pytest.raises(Exception):
        fetch_product_or_404(999999)

def test_build_product_details_dto_function_exists():
    assert callable(build_product_details_dto) is True

def test_build_product_details_dto_with_valid_input(app_context):
    seller = _create_user()
    category = _create_category()
    product = _create_product(seller_id=seller.id, category_id=category.id, is_active=True)

    dto = build_product_details_dto(product)
    assert isinstance(dto, dict)

    for key in ["product_id", "general", "seller", "description", "pricing", "delivery", "warranty"]:
        assert key in dto, f"DTO missing required top-level key: {key}"

    assert dto["product_id"] == product.id

    general = dto["general"]
    for key in ["name", "sku", "category", "brand", "model_number", "condition", "is_active"]:
        assert key in general, f"DTO.general missing required key: {key}"

    category_dto = general["category"]
    for key in ["id", "name", "slug"]:
        assert key in category_dto, f"DTO.general.category missing required key: {key}"

    seller_dto = dto["seller"]
    for key in ["id", "username", "email"]:
        assert key in seller_dto, f"DTO.seller missing required key: {key}"

    description = dto["description"]
    for key in ["short_description", "full_description", "weight_kg", "dimensions_cm"]:
        assert key in description, f"DTO.description missing required key: {key}"

    pricing = dto["pricing"]
    for key in ["currency", "list_price", "sale_price", "effective_price", "stock_quantity"]:
        assert key in pricing, f"DTO.pricing missing required key: {key}"

    delivery = dto["delivery"]
    for key in ["method", "fee", "estimated_min_days", "estimated_max_days", "ships_from", "return_policy"]:
        assert key in delivery, f"DTO.delivery missing required key: {key}"

    warranty = dto["warranty"]
    for key in ["type", "period_months", "details"]:
        assert key in warranty, f"DTO.warranty missing required key: {key}"

def test_build_product_details_dto_with_invalid_input(app_context):
    with pytest.raises(Exception):
        build_product_details_dto(None)