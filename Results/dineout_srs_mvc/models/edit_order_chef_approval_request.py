from app import db
from datetime import datetime

class EditOrderChefApprovalRequest(db.Model):
    __tablename__ = 'chef_approval_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, index=True)
    requested_by_user_id = db.Column(db.Integer, index=True)
    approved_by_user_id = db.Column(db.Integer, nullable=True, index=True)
    status = db.Column(db.String(20), index=True)
    reason = db.Column(db.String(255))
    change_set_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    decided_at = db.Column(db.DateTime, nullable=True)

    def is_pending(self):
        return self.status == 'pending'