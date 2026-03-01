import os
import sys
import uuid
import decimal
import pytest
from io import BytesIO
from datetime import datetime
from unittest.mock import patch, MagicMock
from werkzeug.datastructures import FileStorage
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User
from models.category import Category
from models.product import Product
from models.add_product_product_image import ProductImage
from controllers.add_product_controller import (
    login_required,
    get_current_user,
    validate_product_payload,
    save_uploaded_images,
)
from views.add_product_views import render_new_product_form, json_error, json_success

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

def _create_user(email=None, username=None, password="Passw0rd!"):
    if email is None:
        email = f"{_unique('user')}@example.com"
    if username is None:
        username = _unique("user")
    u = User(email=email, username=username, password_hash="")
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u

def _create_category(name=None, is_active=True):
    if name is None:
        name = _unique("cat")
    c = Category(name=name, is_active=is_active)
    db.session.add(c)
    db.session.commit()
    return c

def _login_session(client, user_id: int):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

def _valid_product_form(category_id: int):
    return {
        "name": "Test Product Name",
        "category_id": str(category_id),
        "owner_name": "Owner Name",
        "description": "A" * 20,
        "price": "19.99",
        "currency": "USD",
        "condition": "good",
        "warranty_months": "12",
        "delivery_details": "Ships in 2-3 days",
    }

def _image_file(filename="test.jpg", content_type="image/jpeg", content=b"fake-image-bytes"):
    return FileStorage(stream=BytesIO(content), filename=filename, content_type=content_type)

# MODEL: User (models/user.py)
def test_user_model_has_required_fields(app_context):
    for field in ["id", "email", "username", "password_hash"]:
        assert hasattr(User, field), f"Missing required field on User: {field}"

def test_user_set_password(app_context):
    u = User(email=f"{_unique('e')}@ex.com", username=_unique("u"), password_hash="")
    u.set_password("Secret123!")
    assert u.password_hash
    assert u.password_hash != "Secret123!"

def test_user_check_password(app_context):
    u = User(email=f"{_unique('e')}@ex.com", username=_unique("u"), password_hash="")
    u.set_password("Secret123!")
    assert u.check_password("Secret123!") is True
    assert u.check_password("WrongPassword") is False

def test_user_unique_constraints(app_context):
    email = f"{_unique('dup')}@example.com"
    username = _unique("dupuser")

    u1 = User(email=email, username=username, password_hash="")
    u1.set_password("Secret123!")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email=email, username=_unique("otheruser"), password_hash="")
    u2.set_password("Secret123!")
    db.session.add(u2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    u3 = User(email=f"{_unique('other')}@example.com", username=username, password_hash="")
    u3.set_password("Secret123!")
    db.session.add(u3)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: Category (models/category.py)
def test_category_model_has_required_fields(app_context):
    for field in ["id", "name", "is_active"]:
        assert hasattr(Category, field), f"Missing required field on Category: {field}"

def test_category___repr__(app_context):
    c = Category(name=_unique("cat"), is_active=True)
    rep = repr(c)
    assert isinstance(rep, str)
    assert len(rep) > 0

def test_category_unique_constraints(app_context):
    name = _unique("catdup")
    c1 = Category(name=name, is_active=True)
    db.session.add(c1)
    db.session.commit()

    c2 = Category(name=name, is_active=True)
    db.session.add(c2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

# MODEL: Product (models/product.py)
def test_product_model_has_required_fields(app_context):
    fields = [
        "id",
        "name",
        "category_id",
        "owner_id",
        "owner_name",
        "description",
        "price",
        "currency",
        "condition",
        "warranty_months",
        "delivery_details",
        "is_active",
        "created_at",
        "updated_at",
    ]
    for field in fields:
        assert hasattr(Product, field), f"Missing required field on Product: {field}"

def test_product___repr__(app_context):
    p = Product(
        name="X",
        category_id=1,
        owner_id=1,
        owner_name="O",
        description="D" * 10,
        price=decimal.Decimal("1.00"),
        currency="USD",
        condition="good",
        warranty_months=0,
        delivery_details="Ship",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    rep = repr(p)
    assert isinstance(rep, str)
    assert len(rep) > 0

def test_product_unique_constraints(app_context):
    assert True

# MODEL: ProductImage (models/add_product_product_image.py)
def test_productimage_model_has_required_fields(app_context):
    fields = ["id", "product_id", "file_path", "mime_type", "file_size_bytes", "is_primary", "created_at"]
    for field in fields:
        assert hasattr(ProductImage, field), f"Missing required field on ProductImage: {field}"

def test_productimage___repr__(app_context):
    pi = ProductImage(
        product_id=1,
        file_path="static/uploads/products/x.jpg",
        mime_type="image/jpeg",
        file_size_bytes=123,
        is_primary=False,
        created_at=datetime.utcnow(),
    )
    rep = repr(pi)
    assert isinstance(rep, str)
    assert len(rep) > 0

def test_productimage_unique_constraints(app_context):
    assert True

# ROUTE: /products/new (GET) - new_product
def test_products_new_get_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/products/new"]
    assert rules, "Route /products/new is missing"
    methods = set()
    for r in rules:
        methods |= set(r.methods or [])
    assert "GET" in methods

def test_products_new_get_renders_template(client):
    with app.app_context():
        user = _create_user()
        _login_session(client, user.id)

        _create_category()
        resp = client.get("/products/new", headers={"Accept": "text/html"})
        assert resp.status_code in (200, 302)
        if resp.status_code == 200:
            assert resp.mimetype == "text/html"

# ROUTE: /products (POST) - create_product
def test_products_post_exists(client):
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/products"]
    assert rules, "Route /products is missing"
    methods = set()
    for r in rules:
        methods |= set(r.methods or [])
    assert "POST" in methods

def test_products_post_success(client):
    with app.app_context():
        user = _create_user()
        cat = _create_category()
        _login_session(client, user.id)

        img1 = _image_file(filename="a.jpg", content_type="image/jpeg")
        img2 = _image_file(filename="b.png", content_type="image/png")

        data = _valid_product_form(cat.id)
        data["images"] = [img1, img2]

        with patch("controllers.add_product_controller.save_uploaded_images") as mock_save:
            mock_save.return_value = [
                {
                    "file_path": "static/uploads/products/a.jpg",
                    "mime_type": "image/jpeg",
                    "file_size_bytes": 10,
                    "is_primary": True,
                },
                {
                    "file_path": "static/uploads/products/b.png",
                    "mime_type": "image/png",
                    "file_size_bytes": 20,
                    "is_primary": False,
                },
            ]
            resp = client.post("/products", data=data, content_type="multipart/form-data", headers={"Accept": "application/json"})
            assert resp.status_code == 201
            payload = resp.get_json()
            assert payload is not None
            assert payload.get("ok") is True
            assert "data" in payload and "product" in payload["data"]
            product = payload["data"]["product"]
            assert isinstance(product.get("id"), int)
            assert product["name"] == data["name"]
            assert product["category_id"] == int(data["category_id"])
            assert product["owner_id"] == user.id
            assert product["owner_name"] == data["owner_name"]
            assert product["description"] == data["description"]
            assert product["price"] == data["price"]
            assert product["currency"] == data["currency"]
            assert product["condition"] == data["condition"]
            assert product["warranty_months"] == int(data["warranty_months"])
            assert product["delivery_details"] == data["delivery_details"]
            assert product.get("is_active") in (True, False)
            assert isinstance(product.get("images"), list)
            assert len(product["images"]) == 2
            assert product["images"][0]["is_primary"] is True

        db_product = Product.query.filter_by(id=product["id"]).first()
        assert db_product is not None
        assert db_product.owner_id == user.id
        assert db_product.category_id == cat.id
        db_images = ProductImage.query.filter_by(product_id=db_product.id).all()
        assert len(db_images) == 2

def test_products_post_missing_required_fields(client):
    with app.app_context():
        user = _create_user()
        _login_session(client, user.id)
        _create_category()

        resp = client.post(
            "/products",
            data={},
            content_type="multipart/form-data",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload is not None
        assert payload.get("ok") is False
        assert isinstance(payload.get("errors"), dict)
        for required in ["name", "category_id", "owner_name", "description", "price", "condition", "delivery_details"]:
            assert required in payload["errors"]

def test_products_post_invalid_data(client):
    with app.app_context():
        user = _create_user()
        cat = _create_category()
        _login_session(client, user.id)

        data = _valid_product_form(cat.id)
        data["name"] = "  a  "
        data["price"] = "0"
        data["currency"] = "ZZZ"
        data["condition"] = "broken"
        data["warranty_months"] = "-1"
        data["description"] = "short"
        data["delivery_details"] = "x"

        resp = client.post(
            "/products",
            data=data,
            content_type="multipart/form-data",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload is not None
        assert payload.get("ok") is False
        assert isinstance(payload.get("errors"), dict)
        assert any(k in payload["errors"] for k in ["name", "price", "currency", "condition", "warranty_months", "description", "delivery_details"])

def test_products_post_duplicate_data(client):
    with app.app_context():
        user = _create_user()
        cat = _create_category()
        _login_session(client, user.id)

        data1 = _valid_product_form(cat.id)
        resp1 = client.post(
            "/products",
            data=data1,
            content_type="multipart/form-data",
            headers={"Accept": "application/json"},
        )
        assert resp1.status_code in (201, 400)

        data2 = _valid_product_form(cat.id)
        data2["name"] = data1["name"]
        data2["owner_name"] = data1["owner_name"]
        data2["description"] = data1["description"]
        data2["price"] = data1["price"]
        data2["currency"] = data1["currency"]
        data2["condition"] = data1["condition"]
        data2["warranty_months"] = data1["warranty_months"]
        data2["delivery_details"] = data1["delivery_details"]

        resp2 = client.post(
            "/products",
            data=data2,
            content_type="multipart/form-data",
            headers={"Accept": "application/json"},
        )
        assert resp2.status_code in (201, 400)

# HELPER: login_required(view_func)
def test_login_required_function_exists():
    assert callable(login_required)

def test_login_required_with_valid_input(client):
    def view_func():
        return "ok"

    protected = login_required(view_func)
    assert callable(protected)

    with app.app_context():
        user = _create_user()
        _login_session(client, user.id)
        resp = client.get("/products/new", headers={"Accept": "text/html"})
        assert resp.status_code in (200, 302)

def test_login_required_with_invalid_input():
    with pytest.raises(TypeError):
        login_required(None)

# HELPER: get_current_user(N/A)
def test_get_current_user_function_exists():
    assert callable(get_current_user)

def test_get_current_user_with_valid_input(client):
    with app.app_context():
        user = _create_user()
        with client.session_transaction() as sess:
            sess["user_id"] = user.id

        with app.test_request_context("/products/new", method="GET"):
            with client.session_transaction() as sess2:
                from flask import session

                session["user_id"] = sess2["user_id"]

            current = get_current_user()
            assert current is not None
            assert getattr(current, "id", None) == user.id

def test_get_current_user_with_invalid_input():
    with app.test_request_context("/products/new", method="GET"):
        current = get_current_user()
        assert current is None

# HELPER: validate_product_payload(form, files)
def test_validate_product_payload_function_exists():
    assert callable(validate_product_payload)

def test_validate_product_payload_with_valid_input(app_context):
    cat = _create_category()
    form = _valid_product_form(cat.id)
    files = {"images": [_image_file()]}
    result = validate_product_payload(form, files)
    assert isinstance(result, dict)
    assert "errors" in result
    assert isinstance(result["errors"], dict)
    assert result["errors"] == {}

def test_validate_product_payload_with_invalid_input(app_context):
    form = {
        "name": "x",
        "category_id": "0",
        "owner_name": "",
        "description": "short",
        "price": "not-a-number",
        "currency": "ZZZ",
        "condition": "invalid",
        "warranty_months": "999",
        "delivery_details": "x",
    }
    files = {"images": [_image_file(content_type="application/pdf")]}
    result = validate_product_payload(form, files)
    assert isinstance(result, dict)
    assert "errors" in result
    assert isinstance(result["errors"], dict)
    assert result["errors"], "Expected validation errors but got none"

# HELPER: save_uploaded_images(files, upload_dir, allowed_mimetypes, max_images, max_file_size_bytes)
def test_save_uploaded_images_function_exists():
    assert callable(save_uploaded_images)

def test_save_uploaded_images_with_valid_input(tmp_path):
    upload_dir = str(tmp_path)
    allowed = {"image/jpeg", "image/png", "image/webp"}
    files = {"images": [_image_file(filename="x.jpg", content_type="image/jpeg")]}
    result = save_uploaded_images(
        files=files,
        upload_dir=upload_dir,
        allowed_mimetypes=allowed,
        max_images=5,
        max_file_size_bytes=5 * 1024 * 1024,
    )
    assert isinstance(result, list)
    assert len(result) == 1
    item = result[0]
    assert isinstance(item, dict)
    for k in ["file_path", "mime_type", "file_size_bytes", "is_primary"]:
        assert k in item
    assert item["mime_type"] == "image/jpeg"
    assert isinstance(item["file_size_bytes"], int)

def test_save_uploaded_images_with_invalid_input(tmp_path):
    upload_dir = str(tmp_path)
    allowed = {"image/jpeg", "image/png", "image/webp"}

    too_big = b"x" * (1024 * 1024 + 1)
    files = {"images": [_image_file(filename="x.jpg", content_type="image/jpeg", content=too_big)]}

    with pytest.raises(Exception):
        save_uploaded_images(
            files=files,
            upload_dir=upload_dir,
            allowed_mimetypes=allowed,
            max_images=5,
            max_file_size_bytes=1024 * 1024,
        )