from app import db


class CustomerFeedbackAnswer(db.Model):
    __tablename__ = "customer_feedback_answers"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("customer_feedback_submissions.id"), index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("customer_feedback_questions.id"), index=True)
    choice_id = db.Column(db.Integer, db.ForeignKey("customer_feedback_choices.id"), nullable=True)
    free_text = db.Column(db.Text, nullable=True)

    submission = db.relationship("CustomerFeedbackSubmission", backref=db.backref("answers", lazy=True))
    question = db.relationship("CustomerFeedbackQuestion", backref=db.backref("answers", lazy=True))
    choice = db.relationship("CustomerFeedbackChoice", backref=db.backref("answers", lazy=True))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "question_id": self.question_id,
            "choice_id": self.choice_id,
            "free_text": self.free_text,
        }