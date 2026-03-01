from flask import Blueprint, request, jsonify
from app import db
from models.customer_feedback_question import CustomerFeedbackQuestion
from models.customer_feedback_choice import CustomerFeedbackChoice
from models.customer_feedback_submission import CustomerFeedbackSubmission
from models.customer_feedback_answer import CustomerFeedbackAnswer
from views.customer_feedback_views import render_feedback_screen

customer_feedback_bp = Blueprint("customer_feedback_bp", __name__, url_prefix="")


@customer_feedback_bp.route("/bill/request", methods=["POST"])
def request_bill():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid payload"}), 400

    allowed = {"bill_id", "customer_session_id"}
    if any(k not in allowed for k in data.keys()):
        return jsonify({"error": "Invalid payload"}), 400

    bill_id = data.get("bill_id")
    customer_session_id = data.get("customer_session_id")

    if not isinstance(bill_id, str) or not bill_id.strip() or len(bill_id) > 64:
        return jsonify({"error": "Invalid payload"}), 400
    if (
        not isinstance(customer_session_id, str)
        or not customer_session_id.strip()
        or len(customer_session_id) > 64
    ):
        return jsonify({"error": "Invalid payload"}), 400

    return jsonify({"next": "/feedback"}), 200


@customer_feedback_bp.route("/feedback", methods=["GET"])
def feedback_screen():
    bill_id = request.args.get("bill_id")
    customer_session_id = request.args.get("customer_session_id")

    if not isinstance(bill_id, str) or not bill_id.strip() or len(bill_id) > 64:
        return jsonify({"error": "Missing parameters"}), 400
    if (
        not isinstance(customer_session_id, str)
        or not customer_session_id.strip()
        or len(customer_session_id) > 64
    ):
        return jsonify({"error": "Missing parameters"}), 400

    questions = load_active_questions_with_choices()
    questions_dicts = [q.to_dict(include_choices=True) for q in questions]
    return render_feedback_screen(bill_id, customer_session_id, questions_dicts)


@customer_feedback_bp.route("/api/feedback/questions", methods=["GET"])
def get_feedback_questions():
    active_only = request.args.get("active_only", default=1, type=int)
    if active_only not in (0, 1):
        active_only = 1

    if active_only == 1:
        questions = load_active_questions_with_choices()
    else:
        questions = CustomerFeedbackQuestion.query.order_by(CustomerFeedbackQuestion.display_order.asc()).all()

    return jsonify({"questions": [q.to_dict(include_choices=True) for q in questions]}), 200


@customer_feedback_bp.route("/api/feedback/submit", methods=["POST"])
def submit_feedback():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"errors": ["Invalid payload"]}), 400

    allowed = {"bill_id", "customer_session_id", "overall_rating", "comment", "answers"}
    if any(k not in allowed for k in data.keys()):
        return jsonify({"errors": ["Invalid payload"]}), 400

    questions = load_active_questions_with_choices()
    valid, errors = validate_feedback_payload(data, questions)
    if not valid:
        return jsonify({"errors": errors}), 400

    submission = CustomerFeedbackSubmission(
        bill_id=data["bill_id"].strip(),
        customer_session_id=data["customer_session_id"].strip(),
        overall_rating=data.get("overall_rating"),
        comment=data.get("comment"),
    )
    db.session.add(submission)
    db.session.flush()

    for ans in data["answers"]:
        feedback_answer = CustomerFeedbackAnswer(
            submission_id=submission.id,
            question_id=ans["question_id"],
            choice_id=ans.get("choice_id"),
            free_text=ans.get("free_text"),
        )
        db.session.add(feedback_answer)

    db.session.commit()
    return jsonify({"submission_id": submission.id, "message": "feedback_submitted"}), 201


def validate_feedback_payload(payload: dict, questions: list[CustomerFeedbackQuestion]) -> tuple[bool, list[str]]:
    errors: list[str] = []

    if not isinstance(payload, dict):
        return False, ["Invalid payload"]

    bill_id = payload.get("bill_id")
    customer_session_id = payload.get("customer_session_id")
    answers = payload.get("answers")

    if not isinstance(bill_id, str) or not bill_id.strip() or len(bill_id) > 64:
        errors.append("bill_id is required")
    if (
        not isinstance(customer_session_id, str)
        or not customer_session_id.strip()
        or len(customer_session_id) > 64
    ):
        errors.append("customer_session_id is required")

    if not isinstance(answers, list) or len(answers) < 1:
        errors.append("answers is required")
        return (len(errors) == 0, errors)

    overall_rating = payload.get("overall_rating", None)
    if overall_rating is not None:
        if not isinstance(overall_rating, int) or overall_rating < 1 or overall_rating > 5:
            errors.append("overall_rating must be between 1 and 5")

    comment = payload.get("comment", None)
    if comment is not None:
        if not isinstance(comment, str):
            errors.append("comment must be a string")
        elif len(comment) > 2000:
            errors.append("comment is too long")

    question_ids = {q.id for q in questions}
    choices_by_question: dict[int, set[int]] = {}
    for q in questions:
        q_choices = getattr(q, "choices", []) or []
        choices_by_question[q.id] = {c.id for c in q_choices}

    for idx, answer in enumerate(answers):
        if not isinstance(answer, dict):
            errors.append(f"answers[{idx}] must be an object")
            continue

        allowed_keys = {"question_id", "choice_id", "free_text"}
        if any(k not in allowed_keys for k in answer.keys()):
            errors.append(f"answers[{idx}] has invalid fields")
            continue

        if "question_id" not in answer:
            errors.append(f"answers[{idx}].question_id is required")
            continue

        qid = answer.get("question_id")
        if not isinstance(qid, int):
            errors.append(f"answers[{idx}].question_id must be an integer")
            continue
        if qid not in question_ids:
            errors.append(f"Invalid question_id: {qid}")
            continue

        has_choice = "choice_id" in answer and answer.get("choice_id") is not None
        has_text = "free_text" in answer and answer.get("free_text") is not None

        if not has_choice and not has_text:
            errors.append(f"answers[{idx}] must include choice_id or free_text")
            continue

        if has_choice:
            cid = answer.get("choice_id")
            if not isinstance(cid, int):
                errors.append(f"answers[{idx}].choice_id must be an integer")
            else:
                valid_choices = choices_by_question.get(qid, set())
                if cid not in valid_choices:
                    errors.append(f"answers[{idx}].choice_id is invalid for question_id {qid}")

        if has_text:
            ft = answer.get("free_text")
            if not isinstance(ft, str):
                errors.append(f"answers[{idx}].free_text must be a string")
            elif len(ft) > 2000:
                errors.append(f"answers[{idx}].free_text is too long")

    return (len(errors) == 0, errors)


def load_active_questions_with_choices() -> list[CustomerFeedbackQuestion]:
    return (
        CustomerFeedbackQuestion.query.filter_by(is_active=True)
        .order_by(CustomerFeedbackQuestion.display_order.asc(), CustomerFeedbackQuestion.id.asc())
        .all()
    )