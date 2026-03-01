from app import db


class CustomerFeedbackChoice(db.Model):
    __tablename__ = "customer_feedback_choices"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("customer_feedback_questions.id"), index=True)
    label = db.Column(db.String(120))
    value = db.Column(db.Integer)
    display_order = db.Column(db.Integer, default=0)

    question = db.relationship("CustomerFeedbackQuestion", backref=db.backref("choices", lazy=True))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "value": self.value,
            "display_order": self.display_order,
        }