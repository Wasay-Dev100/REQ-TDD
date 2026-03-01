import sys
import os
import uuid
from decimal import Decimal
from datetime import datetime
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.product import Product
from models.category import Category
from controllers.product_search_controller import (
    _parse_bool,
    _validate_pagination,
    _apply_product_sort,
    _build_product_search_query,
)
from views.product_search_views import render_search_page

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

def _create_category(name=None, slug=None, is_active=True):
    if name is None:
        name = _unique("Category")
    if slug is None:
        slug = _unique("category-slug")
    category = Category(name=name, slug=slug, is_active=is_active)
    db.session.add(category)
    db.session.commit()
    return category

def _create_product(
    name=None,
    description="desc",
    price=Decimal("9.99"),
    is_active=True,
    category_id=None,
):
    if name is None:
        name = _unique("Product")
    if category_id is None:
        category = _create_category()
        category_id = category.id
    product = Product(
        name=name,
        description=description,
        price=price,
        is_active=is_active,
        category_id=category_id,
    )
    db.session.add(product)
    db.session.commit()
    return product

# MODEL: Product (models/product.py)
def test_product_model_has_required_fields(app_context):
    for field in ["id", "name", "description", "price", "is_active", "category_id", "created_at"]:
        assert hasattr(Product, field), f"Product missing required field: {field}"

def test_product_to_dict(app_context):
    cat = _create_category()
    p = _create_product(
        name=_unique("Phone"),
        description="Smart phone",
        price=Decimal("199.90"),
        is_active=True,
        category_id=cat.id,
    )
    assert hasattr(p, "to_dict") and callable(p.to_dict)

    data = p.to_dict()
    assert isinstance(data, dict)

    for key in ["id", "name", "description", "price", "category", "is_active"]:
        assert key in data, f"Product.to_dict missing key: {key}"

    assert data["id"] == p.id
    assert data["name"] == p.name
    assert data["description"] == p.description
    assert data["is_active"] == p.is_active

    assert isinstance(data["price"], str)
    assert data["price"] == "199.90"

    category_data = data["category"]
    assert isinstance(category_data, dict)
    for key in ["id", "name", "slug", "is_active"]:
        assert key in category_data, f"Product.to_dict category missing key: {key}"
    assert category_data["id"] == cat.id

def test_product_unique_constraints(app_context):
    cat = _create_category()
    name = _unique("NonUniqueName")
    p1 = _create_product(name=name, category_id=cat.id)
    p2 = _create_product(name=name, category_id=cat.id)
    assert p1.id != p2.id

# MODEL: Category (models/category.py)
def test_category_model_has_required_fields(app_context):
    for field in ["id", "name", "slug", "is_active", "created_at"]:
        assert hasattr(Category, field), f"Category missing required field: {field}"

def test_category_to_dict(app_context):
    c = _create_category(name=_unique("Books"), slug=_unique("books"))
    assert hasattr(c, "to_dict") and callable(c.to_dict)

    data = c.to_dict()
    assert isinstance(data, dict)

    for key in ["id", "name", "slug", "is_active"]:
        assert key in data, f"Category.to_dict missing key: {key}"

    assert data["id"] == c.id
    assert data["name"] == c.name
    assert data["slug"] == c.slug
    assert data["is_active"] == c.is_active

def test_category_unique_constraints(app_context):
    name = _unique("UniqueCategoryName")
    slug = _unique("unique-category-slug")
    c1 = _create_category(name=name, slug=slug)

    c2 = Category(name=name, slug=_unique("other-slug"), is_active=True)
    db.session.add(c2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    c3 = Category(name=_unique("OtherName"), slug=slug, is_active=True)
    db.session.add(c3)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    assert c1.id is not None

# ROUTE: /products/search (GET) - search_products
def test_products_search_get_exists(client):
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/products/search" in rules

    endpoint = None
    for r in app.url_map.iter_rules():
        if r.rule == "/products/search":
            endpoint = r.endpoint
            methods = r.methods or set()
            assert "GET" in methods
            break
    assert endpoint is not None

def test_products_search_get_renders_template(client):
    resp = client.get("/products/search")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/xhtml+xml", "text/html; charset=utf-8")
    assert len(resp.data) > 0

# ROUTE: /categories (GET) - list_categories
def test_categories_get_exists(client):
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/categories" in rules

    endpoint = None
    for r in app.url_map.iter_rules():
        if r.rule == "/categories":
            endpoint = r.endpoint
            methods = r.methods or set()
            assert "GET" in methods
            break
    assert endpoint is not None

def test_categories_get_renders_template(client):
    resp = client.get("/categories")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/xhtml+xml", "text/html; charset=utf-8")
    assert len(resp.data) > 0

# ROUTE: /categories/<int:category_id>/products (GET) - browse_category_products
def test_categories_category_id_products_get_exists(client):
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/categories/<int:category_id>/products" in rules

    endpoint = None
    for r in app.url_map.iter_rules():
        if r.rule == "/categories/<int:category_id>/products":
            endpoint = r.endpoint
            methods = r.methods or set()
            assert "GET" in methods
            break
    assert endpoint is not None

def test_categories_category_id_products_get_renders_template(client):
    with app.app_context():
        cat = _create_category()
    resp = client.get(f"/categories/{cat.id}/products")
    assert resp.status_code == 200
    assert resp.mimetype in ("text/html", "application/xhtml+xml", "text/html; charset=utf-8")
    assert len(resp.data) > 0

# HELPER: _parse_bool(value)
def test__parse_bool_function_exists():
    assert callable(_parse_bool)

def test__parse_bool_with_valid_input():
    assert _parse_bool(True) is True
    assert _parse_bool(False) is False

    assert _parse_bool("true") is True
    assert _parse_bool("TRUE") is True
    assert _parse_bool("1") is True
    assert _parse_bool("yes") is True
    assert _parse_bool("on") is True

    assert _parse_bool("false") is False
    assert _parse_bool("FALSE") is False
    assert _parse_bool("0") is False
    assert _parse_bool("no") is False
    assert _parse_bool("off") is False

def test__parse_bool_with_invalid_input():
    with pytest.raises((ValueError, TypeError)):
        _parse_bool("maybe")
    with pytest.raises((ValueError, TypeError)):
        _parse_bool(object())

# HELPER: _validate_pagination(limit, offset)
def test__validate_pagination_function_exists():
    assert callable(_validate_pagination)

def test__validate_pagination_with_valid_input():
    limit, offset = _validate_pagination(10, 0)
    assert isinstance(limit, int) and isinstance(offset, int)
    assert limit == 10
    assert offset == 0

    limit2, offset2 = _validate_pagination("25", "5")
    assert (limit2, offset2) == (25, 5)

def test__validate_pagination_with_invalid_input():
    with pytest.raises((ValueError, TypeError)):
        _validate_pagination(-1, 0)
    with pytest.raises((ValueError, TypeError)):
        _validate_pagination(10, -5)
    with pytest.raises((ValueError, TypeError)):
        _validate_pagination("abc", 0)
    with pytest.raises((ValueError, TypeError)):
        _validate_pagination(10, "xyz")

# HELPER: _apply_product_sort(query, sort, search_term)
def test__apply_product_sort_function_exists():
    assert callable(_apply_product_sort)

def test__apply_product_sort_with_valid_input(app_context):
    cat = _create_category()
    _create_product(name=_unique("Alpha"), price=Decimal("10.00"), category_id=cat.id)
    _create_product(name=_unique("Beta"), price=Decimal("5.00"), category_id=cat.id)

    base_query = Product.query
    q1 = _apply_product_sort(base_query, "price_asc", None)
    assert q1 is not None
    assert hasattr(q1, "all") and callable(q1.all)

    q2 = _apply_product_sort(base_query, "price_desc", "")
    assert q2 is not None
    assert hasattr(q2, "all") and callable(q2.all)

    q3 = _apply_product_sort(base_query, "newest", None)
    assert q3 is not None
    assert hasattr(q3, "all") and callable(q3.all)

    q4 = _apply_product_sort(base_query, "relevance", "alpha")
    assert q4 is not None
    assert hasattr(q4, "all") and callable(q4.all)

def test__apply_product_sort_with_invalid_input(app_context):
    base_query = Product.query
    with pytest.raises((ValueError, TypeError)):
        _apply_product_sort(base_query, "not_a_sort", None)
    with pytest.raises((ValueError, TypeError)):
        _apply_product_sort(base_query, "relevance", None)

# HELPER: _build_product_search_query(search_term, category_id, only_active)
def test__build_product_search_query_function_exists():
    assert callable(_build_product_search_query)

def test__build_product_search_query_with_valid_input(app_context):
    cat1 = _create_category()
    cat2 = _create_category()

    p1 = _create_product(
        name="Red Shirt",
        description="A bright red shirt",
        price=Decimal("12.00"),
        is_active=True,
        category_id=cat1.id,
    )
    _create_product(
        name="Blue Shirt",
        description="A blue shirt",
        price=Decimal("13.00"),
        is_active=False,
        category_id=cat1.id,
    )
    _create_product(
        name="Red Hat",
        description="A red hat",
        price=Decimal("7.00"),
        is_active=True,
        category_id=cat2.id,
    )

    q1 = _build_product_search_query("red", None, True)
    assert q1 is not None
    assert hasattr(q1, "all") and callable(q1.all)
    results1 = q1.all()
    ids1 = {p.id for p in results1}
    assert p1.id in ids1

    q2 = _build_product_search_query("", cat1.id, True)
    results2 = q2.all()
    assert all(p.category_id == cat1.id for p in results2)
    assert all(p.is_active is True for p in results2)

    q3 = _build_product_search_query(None, cat1.id, False)
    results3 = q3.all()
    assert all(p.category_id == cat1.id for p in results3)
    assert any(p.is_active is False for p in results3) or any(p.is_active is True for p in results3)

def test__build_product_search_query_with_invalid_input(app_context):
    with pytest.raises((ValueError, TypeError)):
        _build_product_search_query(object(), None, True)
    with pytest.raises((ValueError, TypeError)):
        _build_product_search_query("test", "not-an-int", True)
    with pytest.raises((ValueError, TypeError)):
        _build_product_search_query("test", None, "not-a-bool")