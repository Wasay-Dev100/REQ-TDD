from datetime import datetime

from app import db


class HallManagerOperationsNotification(db.Model):
    __tablename__ = "hall_manager_operations_notifications"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    firebase_event_id = db.Column(db.String(128), unique=True, index=True)
    event_type = db.Column(db.String(50), index=True)
    order_id = db.Column(db.Integer, nullable=True, index=True)
    table_id = db.Column(db.Integer, nullable=True, index=True)
    message = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, index=True, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": int(self.id) if self.id is not None else None,
            "firebase_event_id": self.firebase_event_id,
            "event_type": self.event_type,
            "order_id": int(self.order_id) if self.order_id is not None else None,
            "table_id": int(self.table_id) if self.table_id is not None else None,
            "message": self.message,
            "is_read": bool(self.is_read),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }