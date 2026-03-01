from flask import render_template


def render_feedback_screen(bill_id: str, customer_session_id: str, questions: list[dict]) -> str:
    return render_template(
        "customer_feedback_feedback.html",
        bill_id=bill_id,
        customer_session_id=customer_session_id,
        questions=questions,
    )