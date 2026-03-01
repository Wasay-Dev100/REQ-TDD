from datetime import datetime

from app import db


class HallManagerOperationsOrder(db.Model):
    __tablename__ = "hall_manager_operations_orders"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    firebase_order_id = db.Column(db.String(128), unique=True, index=True)
    table_id = db.Column(db.Integer, index=True)
    status = db.Column(db.String(30), index=True)
    total_amount = db.Column(db.Numeric(10, 2))
    currency = db.Column(db.String(3))
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": int(self.id) if self.id is not None else None,
            "firebase_order_id": self.firebase_order_id,
            "table_id": int(self.table_id) if self.table_id is not None else None,
            "status": self.status,
            "total_amount": str(self.total_amount) if self.total_amount is not None else "0.00",
            "currency": self.currency,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }