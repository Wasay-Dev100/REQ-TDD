import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import inspect
import pytest
from flask import template_rendered

from app import app, db
from models.view_user_manual_manual_section import ManualSection
from controllers.view_user_manual_controller import (
    ensure_default_manual_sections,
    get_published_sections,
)
from views.view_user_manual_views import render_help_page, serialize_manual

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

class _TemplateCapture:
    def __init__(self, flask_app):
        self._app = flask_app
        self.recorded = []

    def __enter__(self):
        template_rendered.connect(self._record, self._app)
        return self

    def __exit__(self, exc_type, exc, tb):
        template_rendered.disconnect(self._record, self._app)

    def _record(self, sender, template, context, **extra):
        self.recorded.append((template, context))

def _create_section(
    *,
    slug="registration",
    title="Registration",
    content_md="Instructions",
    display_order=1,
    is_published=True,
):
    section = ManualSection(
        slug=slug,
        title=title,
        content_md=content_md,
        display_order=display_order,
        is_published=is_published,
    )
    db.session.add(section)
    db.session.commit()
    return section

def test_manualsection_model_has_required_fields(app_context):
    for field_name in ["id", "slug", "title", "content_md", "display_order", "is_published"]:
        assert hasattr(ManualSection, field_name), f"Missing required field: {field_name}"

def test_manualsection_to_dict(app_context):
    section = _create_section(
        slug="registration",
        title="Registration",
        content_md="Instructions for creating an account.",
        display_order=1,
        is_published=True,
    )
    assert hasattr(section, "to_dict"), "ManualSection.to_dict is required by contract"
    data = section.to_dict()
    assert isinstance(data, dict)
    for key in ["slug", "title", "content_md", "display_order"]:
        assert key in data, f"to_dict() missing key: {key}"
    assert data["slug"] == "registration"
    assert data["title"] == "Registration"
    assert data["content_md"] == "Instructions for creating an account."
    assert data["display_order"] == 1

def test_manualsection_unique_constraints(app_context):
    _create_section(slug="registration", title="Registration", content_md="A", display_order=1)
    dup = ManualSection(
        slug="registration",
        title="Registration 2",
        content_md="B",
        display_order=2,
        is_published=True,
    )
    db.session.add(dup)
    with pytest.raises(Exception):
        db.session.commit()

def test_help_get_exists(client):
    response = client.get("/help")
    assert response.status_code != 404

def test_help_get_renders_template(client):
    with _TemplateCapture(app) as cap:
        response = client.get("/help")
        assert response.status_code == 200
        assert len(cap.recorded) >= 1, "Expected a template to be rendered for /help"
        template_names = [t.name for (t, _ctx) in cap.recorded if getattr(t, "name", None)]
        assert "view_user_manual_help.html" in template_names

def test_api_help_manual_get_exists(client):
    response = client.get("/api/help/manual")
    assert response.status_code != 404

def test_api_help_manual_get_renders_template(client):
    response = client.get("/api/help/manual")
    assert response.status_code == 200
    assert response.content_type is not None
    assert "application/json" in response.content_type.lower()
    payload = response.get_json()
    assert isinstance(payload, dict)
    assert "manual" in payload
    assert isinstance(payload["manual"], dict)
    assert "sections" in payload["manual"]
    assert isinstance(payload["manual"]["sections"], list)

def test_ensure_default_manual_sections_function_exists():
    assert callable(ensure_default_manual_sections)

def test_ensure_default_manual_sections_with_valid_input(app_context):
    ensure_default_manual_sections()
    slugs = {s.slug for s in ManualSection.query.all()}
    required = {"registration", "password_recovery", "product_search", "contacting_sellers"}
    missing = required - slugs
    assert not missing, f"Missing required default manual sections: {sorted(missing)}"

    ensure_default_manual_sections()
    counts = (
        db.session.query(ManualSection.slug, db.func.count(ManualSection.id))
        .group_by(ManualSection.slug)
        .all()
    )
    dupes = [slug for slug, cnt in counts if cnt > 1]
    assert not dupes, f"ensure_default_manual_sections should be idempotent; duplicates: {dupes}"

def test_ensure_default_manual_sections_with_invalid_input(app_context):
    sig = inspect.signature(ensure_default_manual_sections)
    assert len(sig.parameters) == 0, "ensure_default_manual_sections must accept no parameters per contract"
    with pytest.raises(TypeError):
        ensure_default_manual_sections("unexpected")

def test_get_published_sections_function_exists():
    assert callable(get_published_sections)

def test_get_published_sections_with_valid_input(app_context):
    _create_section(slug="registration", title="Registration", content_md="A", display_order=2, is_published=True)
    _create_section(slug="password_recovery", title="Password Recovery", content_md="B", display_order=1, is_published=True)
    _create_section(slug="draft", title="Draft", content_md="C", display_order=3, is_published=False)

    sections = get_published_sections()
    assert isinstance(sections, list)
    assert all(isinstance(s, ManualSection) for s in sections)
    assert all(getattr(s, "is_published") is True for s in sections)

    orders = [s.display_order for s in sections]
    assert orders == sorted(orders), "Published sections must be ordered by display_order ascending"

    slugs = [s.slug for s in sections]
    assert "draft" not in slugs

def test_get_published_sections_with_invalid_input(app_context):
    sig = inspect.signature(get_published_sections)
    assert len(sig.parameters) == 0, "get_published_sections must accept no parameters per contract"
    with pytest.raises(TypeError):
        get_published_sections("unexpected")