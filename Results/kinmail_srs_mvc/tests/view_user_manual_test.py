import os
import sys
import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.view_user_manual_manual_section import ManualSection
from controllers.view_user_manual_controller import (
    seed_default_manual_sections,
    get_published_sections,
)
from views.view_user_manual_views import render_help_page

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

def _unique_slug(prefix="section"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def _create_section(
    *,
    slug=None,
    title="Title",
    content_md="Content",
    display_order=1,
    is_published=True,
):
    if slug is None:
        slug = _unique_slug()
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

class TestManualSectionModel:
    def test_manualsection_model_has_required_fields(self, app_context):
        section = ManualSection(
            slug=_unique_slug(),
            title="Getting Started",
            content_md="Some content",
            display_order=1,
            is_published=True,
        )

        for field in [
            "id",
            "slug",
            "title",
            "content_md",
            "display_order",
            "is_published",
            "created_at",
            "updated_at",
        ]:
            assert hasattr(section, field), f"Missing required field: {field}"

    def test_manualsection_to_dict(self, app_context):
        section = _create_section(
            slug=_unique_slug("to_dict"),
            title="Registration",
            content_md="How to register",
            display_order=10,
            is_published=True,
        )

        assert hasattr(section, "to_dict")
        data = section.to_dict()
        assert isinstance(data, dict)

        for key in [
            "id",
            "slug",
            "title",
            "content_md",
            "display_order",
            "is_published",
            "created_at",
            "updated_at",
        ]:
            assert key in data, f"to_dict() missing key: {key}"

        assert data["id"] == section.id
        assert data["slug"] == section.slug
        assert data["title"] == section.title
        assert data["content_md"] == section.content_md
        assert data["display_order"] == section.display_order
        assert data["is_published"] == section.is_published

        assert data["created_at"] is not None
        assert data["updated_at"] is not None

    def test_manualsection_unique_constraints(self, app_context):
        slug = _unique_slug("unique")
        _create_section(slug=slug, title="A", content_md="A", display_order=1)

        dup = ManualSection(
            slug=slug,
            title="B",
            content_md="B",
            display_order=2,
            is_published=True,
        )
        db.session.add(dup)

        with pytest.raises((IntegrityError, Exception)):
            db.session.commit()

class TestHelpRoutes:
    def test_help_get_exists(self, client):
        response = client.get("/help")
        assert response.status_code != 404

    def test_help_get_renders_template(self, client):
        response = client.get("/help")
        assert response.status_code == 200

        body = (response.data or b"").lower()
        required_phrases = [
            b"registration",
            b"password",
            b"recovery",
            b"search",
            b"contact",
            b"seller",
        ]
        assert any(p in body for p in required_phrases), "Help page missing required manual topics"

class TestApiHelpManualRoutes:
    def test_api_help_manual_get_exists(self, client):
        response = client.get("/api/help/manual")
        assert response.status_code != 404

    def test_api_help_manual_get_renders_template(self, client):
        response = client.get("/api/help/manual")
        assert response.status_code == 200

        content_type = (response.headers.get("Content-Type") or "").lower()
        assert ("application/json" in content_type) or ("text/html" in content_type) or (
            "text/plain" in content_type
        )

        body = (response.data or b"").strip()
        assert len(body) > 0

class TestSeedDefaultManualSectionsHelper:
    def test_seed_default_manual_sections_function_exists(self):
        assert callable(seed_default_manual_sections)

    def test_seed_default_manual_sections_with_valid_input(self, app_context):
        seed_default_manual_sections(db.session)

        sections = ManualSection.query.order_by(ManualSection.display_order.asc()).all()
        assert len(sections) > 0

        slugs = [s.slug for s in sections]
        assert len(slugs) == len(set(slugs)), "Seeded manual sections must have unique slugs"

        combined = " ".join([(s.title or "") + " " + (s.content_md or "") for s in sections]).lower()
        required_topics = ["registration", "password", "recovery", "search", "contact", "seller"]
        assert any(topic in combined for topic in required_topics), "Seeded manual missing required topics"

    def test_seed_default_manual_sections_with_invalid_input(self, app_context):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            seed_default_manual_sections(None)

class TestGetPublishedSectionsHelper:
    def test_get_published_sections_function_exists(self):
        assert callable(get_published_sections)

    def test_get_published_sections_with_valid_input(self, app_context):
        _create_section(
            slug=_unique_slug("pub"),
            title="Published",
            content_md="Visible",
            display_order=2,
            is_published=True,
        )
        _create_section(
            slug=_unique_slug("unpub"),
            title="Draft",
            content_md="Hidden",
            display_order=1,
            is_published=False,
        )
        _create_section(
            slug=_unique_slug("pub2"),
            title="Published 2",
            content_md="Visible 2",
            display_order=3,
            is_published=True,
        )

        sections = get_published_sections(db.session)
        assert isinstance(sections, list)
        assert all(isinstance(s, ManualSection) for s in sections)
        assert all(getattr(s, "is_published", None) is True for s in sections)

        orders = [s.display_order for s in sections]
        assert orders == sorted(orders), "Published sections should be ordered by display_order"

    def test_get_published_sections_with_invalid_input(self, app_context):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            get_published_sections(None)