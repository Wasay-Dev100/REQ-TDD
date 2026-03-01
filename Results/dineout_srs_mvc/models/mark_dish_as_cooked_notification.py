from app import db
from datetime import datetime

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    recipient_role = db.Column(db.String(30))
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), index=True)
    type = db.Column(db.String(50))
    message = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime, nullable=True)

    def mark_read(self):
        self.read_at = datetime.utcnow()