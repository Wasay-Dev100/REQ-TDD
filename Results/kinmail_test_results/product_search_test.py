import os
import sys
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.product import Product
from models.category import Category
from controllers.product_search_controller import (
    parse_pagination_args,
    build_product_search_query,
    serialize_paginated_products,
)
from views.product_search_views import render_search_page, render_category_browse_page

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

def _unique_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _create_category(name=None, slug=None, is_active=True):
    if name is None:
        name = _unique_name("Category")
    if slug is None:
        slug = _unique_name("category-slug")
    c = Category(name=name, slug=slug, is_active=is_active)
    db.session.add(c)
    db.session.commit()
    return c

def _create_product(
    *,
    name=None,
    description="desc",
    price=Decimal("9.99"),
    is_active=True,
    category_id=None,
):
    if name is None:
        name = _unique_name("Product")
    p = Product(
        name=name,
        description=description,
        price=price,
        is_active=is_active,
        category_id=category_id,
    )
    db.session.add(p)
    db.session.commit()
    return p

class TestProductModel:
    def test_product_model_has_required_fields(self, app_context):
        for field in ["id", "name", "description", "price", "is_active", "category_id", "created_at"]:
            assert hasattr(Product, field), f"Missing Product field: {field}"

    def test_product_to_dict(self, app_context):
        cat = _create_category()
        p = _create_product(
            name=_unique_name("Phone"),
            description="Smart phone",
            price=Decimal("199.99"),
            is_active=True,
            category_id=cat.id,
        )
        assert hasattr(p, "to_dict") and callable(getattr(p, "to_dict"))
        data = p.to_dict()
        assert isinstance(data, dict)
        assert data.get("id") == p.id
        assert data.get("name") == p.name
        assert data.get("description") == p.description
        assert str(data.get("price")) == str(p.price)
        assert data.get("is_active") == p.is_active
        assert data.get("category_id") == p.category_id
        assert "created_at" in data

    def test_product_unique_constraints(self, app_context):
        cat = _create_category()
        name = _unique_name("NonUniqueName")
        p1 = _create_product(name=name, category_id=cat.id)
        p2 = _create_product(name=name, category_id=cat.id)
        assert p1.id != p2.id
        assert p1.name == p2.name

class TestCategoryModel:
    def test_category_model_has_required_fields(self, app_context):
        for field in ["id", "name", "slug", "is_active"]:
            assert hasattr(Category, field), f"Missing Category field: {field}"

    def test_category_to_dict(self, app_context):
        c = _create_category(name=_unique_name("Books"), slug=_unique_name("books"))
        assert hasattr(c, "to_dict") and callable(getattr(c, "to_dict"))
        data = c.to_dict()
        assert isinstance(data, dict)
        assert data.get("id") == c.id
        assert data.get("name") == c.name
        assert data.get("slug") == c.slug
        assert data.get("is_active") == c.is_active

    def test_category_unique_constraints(self, app_context):
        name = _unique_name("UniqueCategory")
        slug = _unique_name("unique-category")
        c1 = _create_category(name=name, slug=slug)

        c2 = Category(name=name, slug=_unique_name("other-slug"), is_active=True)
        db.session.add(c2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        c3 = Category(name=_unique_name("OtherName"), slug=slug, is_active=True)
        db.session.add(c3)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        assert c1.id is not None

class TestRoutes:
    def test_search_get_exists(self, client):
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert "/search" in rules
        resp = client.get("/search")
        assert resp.status_code != 405

    def test_search_get_renders_template(self, client):
        resp = client.get("/search")
        assert resp.status_code == 200
        assert resp.mimetype in ("text/html", "application/json")

    def test_categories_get_exists(self, client):
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert "/categories" in rules
        resp = client.get("/categories")
        assert resp.status_code != 405

    def test_categories_get_renders_template(self, client):
        resp = client.get("/categories")
        assert resp.status_code == 200
        assert resp.mimetype in ("text/html", "application/json")

    def test_categories_slug_products_get_exists(self, client):
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert "/categories/<string:slug>/products" in rules
        resp = client.get("/categories/some-slug/products")
        assert resp.status_code != 405

    def test_categories_slug_products_get_renders_template(self, client):
        resp = client.get("/categories/some-slug/products")
        assert resp.status_code in (200, 404)
        assert resp.mimetype in ("text/html", "application/json")

class TestHelperParsePaginationArgs:
    def test_parse_pagination_args_function_exists(self):
        assert callable(parse_pagination_args)

    def test_parse_pagination_args_with_valid_input(self):
        page, per_page = parse_pagination_args({"page": "2", "per_page": "15"})
        assert isinstance(page, int) and isinstance(per_page, int)
        assert page == 2
        assert per_page == 15

    def test_parse_pagination_args_with_invalid_input(self):
        page, per_page = parse_pagination_args({"page": "abc", "per_page": "-5"})
        assert isinstance(page, int) and isinstance(per_page, int)
        assert page >= 1
        assert per_page >= 1

class TestHelperBuildProductSearchQuery:
    def test_build_product_search_query_function_exists(self):
        assert callable(build_product_search_query)

    def test_build_product_search_query_with_valid_input(self, app_context):
        cat = _create_category()
        _create_product(name="Red Apple", description="Fresh fruit", category_id=cat.id, is_active=True)
        _create_product(name="Green Apple", description="Sour fruit", category_id=cat.id, is_active=True)
        _create_product(name="Banana", description="Yellow fruit", category_id=cat.id, is_active=True)

        query = build_product_search_query(q="apple", category_id=str(cat.id), category_slug=None)
        assert query is not None
        assert hasattr(query, "all") and callable(query.all)

        results = query.all()
        assert isinstance(results, list)
        names = [getattr(p, "name", "") for p in results]
        assert any("Apple" in n for n in names)

    def test_build_product_search_query_with_invalid_input(self, app_context):
        cat = _create_category()
        _create_product(name="Desk Lamp", description="Light", category_id=cat.id, is_active=True)

        query = build_product_search_query(q=None, category_id="not-an-int", category_slug=None)
        assert query is not None
        assert hasattr(query, "all") and callable(query.all)
        results = query.all()
        assert isinstance(results, list)

class TestHelperSerializePaginatedProducts:
    def test_serialize_paginated_products_function_exists(self):
        assert callable(serialize_paginated_products)

    def test_serialize_paginated_products_with_valid_input(self, app_context):
        cat = _create_category()
        p1 = _create_product(name=_unique_name("ItemA"), category_id=cat.id)
        p2 = _create_product(name=_unique_name("ItemB"), category_id=cat.id)

        pagination = Product.query.order_by(Product.id.asc()).paginate(page=1, per_page=1, error_out=False)
        data = serialize_paginated_products(pagination)

        assert isinstance(data, dict)
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 1
        assert "page" in data and "per_page" in data
        assert data["page"] == 1
        assert data["per_page"] == 1

        item = data["items"][0]
        assert isinstance(item, dict)
        assert item.get("id") in (p1.id, p2.id)

    def test_serialize_paginated_products_with_invalid_input(self):
        with pytest.raises((TypeError, AttributeError)):
            serialize_paginated_products(None)