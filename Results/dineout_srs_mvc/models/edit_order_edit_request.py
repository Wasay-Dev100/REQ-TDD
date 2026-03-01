from app import db
from datetime import datetime

class EditOrderEditRequest(db.Model):
    __tablename__ = 'edit_order_edit_requests'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, index=True)
    order_item_id = db.Column(db.Integer, nullable=True, index=True)
    product_id = db.Column(db.Integer, nullable=True, index=True)
    action = db.Column(db.String(30), index=True)
    from_quantity = db.Column(db.Integer, nullable=True)
    to_quantity = db.Column(db.Integer, nullable=True)
    requested_by_user_id = db.Column(db.Integer, index=True)
    approved_by_user_id = db.Column(db.Integer, nullable=True, index=True)
    status = db.Column(db.String(30), default='pending', index=True)
    reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    decided_at = db.Column(db.DateTime, nullable=True)

    def requires_approval(self):
        return self.action in ['decrease_quantity', 'remove_item']

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'order_item_id': self.order_item_id,
            'product_id': self.product_id,
            'action': self.action,
            'from_quantity': self.from_quantity,
            'to_quantity': self.to_quantity,
            'requested_by_user_id': self.requested_by_user_id,
            'approved_by_user_id': self.approved_by_user_id,
            'status': self.status,
            'reason': self.reason,
            'created_at': self.created_at,
            'decided_at': self.decided_at
        }