from app import db
from datetime import datetime

class CustomerHelpRequest(db.Model):
    __tablename__ = 'customer_help_requests'

    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.Integer, nullable=False)
    request_type = db.Column(db.String(40), nullable=False)
    message = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    def mark_resolved(self, resolved_at):
        self.status = 'resolved'
        self.resolved_at = resolved_at
        db.session.commit()