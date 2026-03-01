from app import db
from datetime import datetime

class CancellationRequest(db.Model):
    __tablename__ = 'head_chef_order_assignment_cancellation_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    request_type = db.Column(db.String(20), index=True, nullable=False)
    order_id = db.Column(db.Integer, index=True, nullable=False)
    order_dish_id = db.Column(db.Integer, nullable=True, index=True)
    requested_by_user_id = db.Column(db.Integer, index=True, nullable=False)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending', index=True)
    reviewed_by_user_id = db.Column(db.Integer, nullable=True, index=True)
    reviewed_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def approve(self, reviewer_user_id: int):
        self.status = 'approved'
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = datetime.utcnow()

    def reject(self, reviewer_user_id: int):
        self.status = 'rejected'
        self.reviewed_by_user_id = reviewer_user_id
        self.reviewed_at = datetime.utcnow()