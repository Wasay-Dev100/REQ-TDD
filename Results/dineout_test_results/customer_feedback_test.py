import os
import sys
import uuid
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User  # required import per global constraints
from models.customer_feedback_question import CustomerFeedbackQuestion
from models.customer_feedback_choice import CustomerFeedbackChoice
from models.customer_feedback_submission import CustomerFeedbackSubmission
from models.customer_feedback_answer import CustomerFeedbackAnswer
from controllers.customer_feedback_controller import customer_feedback_bp
from controllers.customer_feedback_controller import (
    validate_feedback_payload,
    load_active_questions_with_choices,
)
from views.customer_feedback_views import render_feedback_screen

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

def _unique_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def _create_question_with_choices(
    prompt: str | None = None,
    is_active: bool = True,
    display_order: int = 0,
    choices: list[tuple[str, int, int]] | None = None,
):
    if prompt is None:
        prompt = f"How was it? {_unique_id('q')}"
    q = CustomerFeedbackQuestion(prompt=prompt, is_active=is_active, display_order=display_order)
    db.session.add(q)
    db.session.flush()

    created_choices = []
    if choices is None:
        choices = [("Bad", 1, 1), ("Okay", 3, 2), ("Great", 5, 3)]
    for label, value, order in choices:
        c = CustomerFeedbackChoice(
            question_id=q.id,
            label=label,
            value=value,
            display_order=order,
        )
        db.session.add(c)
        created_choices.append(c)

    db.session.commit()
    return q, created_choices

def _post_json(client, path: str, payload: dict):
    return client.post(path, json=payload)

def _get_route_rules():
    return {(r.rule, tuple(sorted(r.methods))) for r in app.url_map.iter_rules()}

# MODEL: CustomerFeedbackQuestion
def test_customerfeedbackquestion_model_has_required_fields(app_context):
    for field in ["id", "prompt", "is_active", "display_order", "created_at"]:
        assert hasattr(CustomerFeedbackQuestion, field), f"Missing field {field} on CustomerFeedbackQuestion"

def test_customerfeedbackquestion_to_dict(app_context):
    q, choices = _create_question_with_choices()
    assert hasattr(q, "to_dict") and callable(getattr(q, "to_dict"))

    d = q.to_dict(include_choices=True)
    assert isinstance(d, dict)
    assert d["id"] == q.id
    assert d["prompt"] == q.prompt
    assert d["display_order"] == q.display_order
    assert "choices" in d
    assert isinstance(d["choices"], list)
    assert len(d["choices"]) == len(choices)

    d2 = q.to_dict(include_choices=False)
    assert isinstance(d2, dict)
    assert d2["id"] == q.id
    assert "choices" not in d2 or d2["choices"] in (None, [])

def test_customerfeedbackquestion_unique_constraints(app_context):
    q1 = CustomerFeedbackQuestion(prompt=_unique_id("prompt"), is_active=True, display_order=1)
    q2 = CustomerFeedbackQuestion(prompt=q1.prompt, is_active=True, display_order=1)
    db.session.add_all([q1, q2])
    db.session.commit()
    assert q1.id is not None and q2.id is not None

# MODEL: CustomerFeedbackChoice
def test_customerfeedbackchoice_model_has_required_fields(app_context):
    for field in ["id", "question_id", "label", "value", "display_order"]:
        assert hasattr(CustomerFeedbackChoice, field), f"Missing field {field} on CustomerFeedbackChoice"

def test_customerfeedbackchoice_to_dict(app_context):
    q, choices = _create_question_with_choices()
    c = choices[0]
    assert hasattr(c, "to_dict") and callable(getattr(c, "to_dict"))
    d = c.to_dict()
    assert isinstance(d, dict)
    for key in ["id", "label", "value", "display_order"]:
        assert key in d
    assert d["id"] == c.id
    assert d["label"] == c.label
    assert d["value"] == c.value
    assert d["display_order"] == c.display_order

def test_customerfeedbackchoice_unique_constraints(app_context):
    q, _ = _create_question_with_choices()
    c1 = CustomerFeedbackChoice(question_id=q.id, label="Same", value=1, display_order=1)
    c2 = CustomerFeedbackChoice(question_id=q.id, label="Same", value=1, display_order=1)
    db.session.add_all([c1, c2])
    db.session.commit()
    assert c1.id is not None and c2.id is not None

# MODEL: CustomerFeedbackSubmission
def test_customerfeedbacksubmission_model_has_required_fields(app_context):
    for field in ["id", "bill_id", "customer_session_id", "overall_rating", "comment", "submitted_at"]:
        assert hasattr(CustomerFeedbackSubmission, field), f"Missing field {field} on CustomerFeedbackSubmission"

def test_customerfeedbacksubmission_to_dict(app_context):
    s = CustomerFeedbackSubmission(
        bill_id=_unique_id("bill"),
        customer_session_id=_unique_id("sess"),
        overall_rating=5,
        comment="Nice",
    )
    db.session.add(s)
    db.session.commit()
    assert hasattr(s, "to_dict") and callable(getattr(s, "to_dict"))
    d = s.to_dict()
    assert isinstance(d, dict)
    for key in ["id", "bill_id", "customer_session_id", "overall_rating", "comment", "submitted_at"]:
        assert key in d
    assert d["id"] == s.id
    assert d["bill_id"] == s.bill_id
    assert d["customer_session_id"] == s.customer_session_id
    assert d["overall_rating"] == s.overall_rating
    assert d["comment"] == s.comment

def test_customerfeedbacksubmission_unique_constraints(app_context):
    bill_id = _unique_id("bill")
    sess_id = _unique_id("sess")
    s1 = CustomerFeedbackSubmission(bill_id=bill_id, customer_session_id=sess_id)
    s2 = CustomerFeedbackSubmission(bill_id=bill_id, customer_session_id=sess_id)
    db.session.add_all([s1, s2])
    db.session.commit()
    assert s1.id is not None and s2.id is not None

# MODEL: CustomerFeedbackAnswer
def test_customerfeedbackanswer_model_has_required_fields(app_context):
    for field in ["id", "submission_id", "question_id", "choice_id", "free_text"]:
        assert hasattr(CustomerFeedbackAnswer, field), f"Missing field {field} on CustomerFeedbackAnswer"

def test_customerfeedbackanswer_to_dict(app_context):
    q, choices = _create_question_with_choices()
    s = CustomerFeedbackSubmission(bill_id=_unique_id("bill"), customer_session_id=_unique_id("sess"))
    db.session.add(s)
    db.session.flush()

    a = CustomerFeedbackAnswer(
        submission_id=s.id,
        question_id=q.id,
        choice_id=choices[0].id,
        free_text=None,
    )
    db.session.add(a)
    db.session.commit()

    assert hasattr(a, "to_dict") and callable(getattr(a, "to_dict"))
    d = a.to_dict()
    assert isinstance(d, dict)
    for key in ["id", "submission_id", "question_id", "choice_id", "free_text"]:
        assert key in d
    assert d["id"] == a.id
    assert d["submission_id"] == s.id
    assert d["question_id"] == q.id
    assert d["choice_id"] == choices[0].id
    assert d["free_text"] is None

def test_customerfeedbackanswer_unique_constraints(app_context):
    q, choices = _create_question_with_choices()
    s = CustomerFeedbackSubmission(bill_id=_unique_id("bill"), customer_session_id=_unique_id("sess"))
    db.session.add(s)
    db.session.flush()

    a1 = CustomerFeedbackAnswer(submission_id=s.id, question_id=q.id, choice_id=choices[0].id)
    a2 = CustomerFeedbackAnswer(submission_id=s.id, question_id=q.id, choice_id=choices[0].id)
    db.session.add_all([a1, a2])
    db.session.commit()
    assert a1.id is not None and a2.id is not None

# ROUTE: /bill/request (POST)
def test_bill_request_post_exists(client):
    rules = _get_route_rules()
    assert any(rule == "/bill/request" and "POST" in methods for rule, methods in rules)

def test_bill_request_post_success(client):
    payload = {"bill_id": _unique_id("bill"), "customer_session_id": _unique_id("sess")}
    resp = _post_json(client, "/bill/request", payload)
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()
    assert data == {"next": "/feedback"}

def test_bill_request_post_missing_required_fields(client):
    payload = {"bill_id": _unique_id("bill")}
    resp = _post_json(client, "/bill/request", payload)
    assert resp.status_code == 400
    assert resp.is_json
    data = resp.get_json()
    assert "error" in data
    assert isinstance(data["error"], str) and data["error"]

def test_bill_request_post_invalid_data(client):
    payload = {"bill_id": "", "customer_session_id": ""}
    resp = _post_json(client, "/bill/request", payload)
    assert resp.status_code == 400
    assert resp.is_json
    data = resp.get_json()
    assert "error" in data
    assert isinstance(data["error"], str) and data["error"]

def test_bill_request_post_duplicate_data(client):
    payload = {"bill_id": _unique_id("bill"), "customer_session_id": _unique_id("sess")}
    resp1 = _post_json(client, "/bill/request", payload)
    resp2 = _post_json(client, "/bill/request", payload)
    assert resp1.status_code == 200
    assert resp2.status_code in (200, 400)
    assert resp2.is_json
    data2 = resp2.get_json()
    assert ("next" in data2) or ("error" in data2)

# ROUTE: /feedback (GET)
def test_feedback_get_exists(client):
    rules = _get_route_rules()
    assert any(rule == "/feedback" and "GET" in methods for rule, methods in rules)

def test_feedback_get_renders_template(client, app_context):
    _create_question_with_choices()
    bill_id = _unique_id("bill")
    sess_id = _unique_id("sess")
    resp = client.get("/feedback", query_string={"bill_id": bill_id, "customer_session_id": sess_id})
    assert resp.status_code == 200
    ct = resp.headers.get("Content-Type", "")
    assert "text/html" in ct

# ROUTE: /api/feedback/questions (GET)
def test_api_feedback_questions_get_exists(client):
    rules = _get_route_rules()
    assert any(rule == "/api/feedback/questions" and "GET" in methods for rule, methods in rules)

def test_api_feedback_questions_get_renders_template(client, app_context):
    q_active, _ = _create_question_with_choices(is_active=True, display_order=2)
    _create_question_with_choices(is_active=False, display_order=1)

    resp = client.get("/api/feedback/questions")
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()
    assert "questions" in data
    assert isinstance(data["questions"], list)
    assert all(isinstance(item, dict) for item in data["questions"])

    for item in data["questions"]:
        for key in ["id", "prompt", "display_order", "choices"]:
            assert key in item
        assert isinstance(item["choices"], list)

    ids = [item["id"] for item in data["questions"]]
    assert q_active.id in ids

# ROUTE: /api/feedback/submit (POST)
def test_api_feedback_submit_post_exists(client):
    rules = _get_route_rules()
    assert any(rule == "/api/feedback/submit" and "POST" in methods for rule, methods in rules)

def test_api_feedback_submit_post_success(client, app_context):
    q, choices = _create_question_with_choices()
    payload = {
        "bill_id": _unique_id("bill"),
        "customer_session_id": _unique_id("sess"),
        "overall_rating": 5,
        "comment": "Great service",
        "answers": [{"question_id": q.id, "choice_id": choices[0].id}],
    }
    resp = _post_json(client, "/api/feedback/submit", payload)
    assert resp.status_code == 201
    assert resp.is_json
    data = resp.get_json()
    assert "submission_id" in data and isinstance(data["submission_id"], int)
    assert data["message"] == "feedback_submitted"

    sub = CustomerFeedbackSubmission.query.filter_by(id=data["submission_id"]).first()
    assert sub is not None
    assert sub.bill_id == payload["bill_id"]
    assert sub.customer_session_id == payload["customer_session_id"]
    assert sub.overall_rating == 5
    assert sub.comment == "Great service"

    ans = CustomerFeedbackAnswer.query.filter_by(submission_id=sub.id, question_id=q.id).first()
    assert ans is not None
    assert ans.choice_id == choices[0].id

def test_api_feedback_submit_post_missing_required_fields(client, app_context):
    _create_question_with_choices()
    payload = {"bill_id": _unique_id("bill"), "customer_session_id": _unique_id("sess")}
    resp = _post_json(client, "/api/feedback/submit", payload)
    assert resp.status_code == 400
    assert resp.is_json
    data = resp.get_json()
    assert "errors" in data
    assert isinstance(data["errors"], list)
    assert len(data["errors"]) >= 1

def test_api_feedback_submit_post_invalid_data(client, app_context):
    q, choices = _create_question_with_choices()
    payload = {
        "bill_id": "",
        "customer_session_id": "",
        "overall_rating": 6,
        "comment": "x" * 2001,
        "answers": [{"question_id": q.id, "choice_id": choices[0].id}],
    }
    resp = _post_json(client, "/api/feedback/submit", payload)
    assert resp.status_code == 400
    assert resp.is_json
    data = resp.get_json()
    assert "errors" in data
    assert isinstance(data["errors"], list)
    assert len(data["errors"]) >= 1

def test_api_feedback_submit_post_duplicate_data(client, app_context):
    q, choices = _create_question_with_choices()
    bill_id = _unique_id("bill")
    sess_id = _unique_id("sess")
    payload = {
        "bill_id": bill_id,
        "customer_session_id": sess_id,
        "overall_rating": 4,
        "comment": "Ok",
        "answers": [{"question_id": q.id, "choice_id": choices[0].id}],
    }
    resp1 = _post_json(client, "/api/feedback/submit", payload)
    resp2 = _post_json(client, "/api/feedback/submit", payload)
    assert resp1.status_code == 201
    assert resp2.status_code in (201, 400)
    assert resp2.is_json
    data2 = resp2.get_json()
    assert ("submission_id" in data2 and "message" in data2) or ("errors" in data2)

# HELPER: validate_feedback_payload(payload: dict, questions: list[CustomerFeedbackQuestion])
def test_validate_feedback_payload_function_exists():
    assert callable(validate_feedback_payload)

def test_validate_feedback_payload_with_valid_input(app_context):
    q, choices = _create_question_with_choices()
    payload = {
        "bill_id": _unique_id("bill"),
        "customer_session_id": _unique_id("sess"),
        "overall_rating": 5,
        "comment": "Nice",
        "answers": [{"question_id": q.id, "choice_id": choices[0].id}],
    }
    ok, errors = validate_feedback_payload(payload, [q])
    assert ok is True
    assert isinstance(errors, list)
    assert errors == []

def test_validate_feedback_payload_with_invalid_input(app_context):
    q, _ = _create_question_with_choices()
    payload = {
        "bill_id": "",
        "customer_session_id": "",
        "overall_rating": 0,
        "comment": "x" * 2001,
        "answers": [{"question_id": q.id}],
    }
    ok, errors = validate_feedback_payload(payload, [q])
    assert ok is False
    assert isinstance(errors, list)
    assert len(errors) >= 1

# HELPER: load_active_questions_with_choices()
def test_load_active_questions_with_choices_function_exists():
    assert callable(load_active_questions_with_choices)

def test_load_active_questions_with_choices_with_valid_input(app_context):
    q1, _ = _create_question_with_choices(is_active=True, display_order=2)
    q2, _ = _create_question_with_choices(is_active=True, display_order=1)
    _create_question_with_choices(is_active=False, display_order=0)

    questions = load_active_questions_with_choices()
    assert isinstance(questions, list)
    assert all(isinstance(q, CustomerFeedbackQuestion) for q in questions)

    ids = [q.id for q in questions]
    assert q1.id in ids
    assert q2.id in ids

    orders = [q.display_order for q in questions]
    assert orders == sorted(orders)

def test_load_active_questions_with_choices_with_invalid_input(app_context):
    CustomerFeedbackChoice.query.delete()
    CustomerFeedbackQuestion.query.delete()
    db.session.commit()

    questions = load_active_questions_with_choices()
    assert isinstance(questions, list)
    assert questions == []