import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch

from app import app, db
from controllers.view_website_user_manual_controller import view_website_user_manual_bp
from controllers.view_website_user_manual_controller import get_user_manual_sections
from views.view_website_user_manual_views import render_help_page

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

    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()

def test_help_get_exists(client):
    response = client.get("/help")
    assert response.status_code != 404

def test_help_get_renders_template(client):
    with patch(
        "controllers.view_website_user_manual_controller.render_template",
        autospec=True,
        return_value="OK",
    ) as mock_render_template:
        response = client.get("/help")
        assert response.status_code == 200
        assert response.get_data(as_text=True) == "OK"
        assert mock_render_template.call_count == 1
        args, kwargs = mock_render_template.call_args
        assert args[0] == "view_website_user_manual_help.html"
        assert "sections" in kwargs
        assert isinstance(kwargs["sections"], dict)

def test_get_user_manual_sections_function_exists():
    assert callable(get_user_manual_sections)

def test_get_user_manual_sections_with_valid_input():
    sections = get_user_manual_sections()
    assert isinstance(sections, dict)

    required_keys = {"registration", "password_recovery", "product_search", "contacting_sellers"}
    missing = required_keys - set(sections.keys())
    assert not missing, f"Missing required user manual sections: {sorted(missing)}"

    for key in required_keys:
        assert isinstance(sections[key], dict), f"Section '{key}' must be a dict[str, str]"
        assert sections[key], f"Section '{key}' must not be empty"
        for sub_key, sub_val in sections[key].items():
            assert isinstance(sub_key, str) and sub_key.strip(), f"Section '{key}' has invalid subsection key"
            assert isinstance(sub_val, str) and sub_val.strip(), f"Section '{key}' has invalid subsection content"

def test_get_user_manual_sections_with_invalid_input():
    with pytest.raises(TypeError):
        get_user_manual_sections("unexpected")

def test_render_help_page_function_exists_and_returns_str():
    assert callable(render_help_page)
    result = render_help_page(
        {
            "registration": {"step1": "Create an account"},
            "password_recovery": {"step1": "Use password reset"},
            "product_search": {"step1": "Search products"},
            "contacting_sellers": {"step1": "Message the seller"},
        }
    )
    assert isinstance(result, str)