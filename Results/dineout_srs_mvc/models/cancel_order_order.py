from app import db
from datetime import datetime

class CancelOrderOrder(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, index=True, nullable=False)
    status = db.Column(db.String(30), index=True, nullable=False)
    served_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, index=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    def is_cancellable(self):
        return self.status != 'SERVED' and self.served_at is None