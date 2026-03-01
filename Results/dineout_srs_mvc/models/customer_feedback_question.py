from app import db
from datetime import datetime

class CustomerFeedbackQuestion(db.Model):
    __tablename__ = 'customer_feedback_questions'

    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, include_choices: bool = True) -> dict:
        question_dict = {
            'id': self.id,
            'prompt': self.prompt,
            'display_order': self.display_order
        }
        if include_choices:
            question_dict['choices'] = [choice.to_dict() for choice in self.choices]
        return question_dict