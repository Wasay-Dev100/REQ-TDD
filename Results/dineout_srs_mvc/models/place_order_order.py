from app import db
from datetime import datetime, timedelta

class PlaceOrderOrder(db.Model):
    __tablename__ = 'place_order_orders'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, index=True, nullable=False)
    status = db.Column(db.String(20), default='PENDING')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    canceled_at = db.Column(db.DateTime, nullable=True)
    cancel_reason = db.Column(db.String(255), nullable=True)
    total_cents = db.Column(db.Integer, default=0)
    cancel_window_seconds = db.Column(db.Integer, default=60)

    def recalculate_total(self, items):
        self.total_cents = sum(item.line_total_cents for item in items)
        return self.total_cents

    def is_cancelable(self, now_utc):
        cancelable_until = self.created_at + timedelta(seconds=self.cancel_window_seconds)
        return self.status == 'PENDING' and now_utc <= cancelable_until

    def to_dict(self):
        cancelable_until = self.created_at + timedelta(seconds=self.cancel_window_seconds)
        return {
            "order_id": self.id,
            "status": self.status,
            "total_cents": self.total_cents,
            "created_at": self.created_at.isoformat(),
            "cancelable_until": cancelable_until.isoformat(),
            "seconds_remaining_to_cancel": max(0, (cancelable_until - datetime.utcnow()).total_seconds()),
            "items": [item.to_dict() for item in self.items]
        }