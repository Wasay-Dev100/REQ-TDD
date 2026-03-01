from datetime import datetime
from decimal import Decimal

from app import db


class HallManagerOperationsBill(db.Model):
    __tablename__ = "hall_manager_operations_bills"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    firebase_bill_id = db.Column(db.String(128), unique=True, index=True)
    order_id = db.Column(db.Integer, unique=True, index=True)
    amount_due = db.Column(db.Numeric(10, 2))
    amount_paid = db.Column(db.Numeric(10, 2), nullable=True)
    status = db.Column(db.String(30), index=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    paid_by_user_id = db.Column(db.Integer, nullable=True, index=True)
    payment_method = db.Column(db.String(30), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def mark_paid(self, paid_by_user_id: int | None, payment_method: str | None, amount_paid: float | None):
        self.status = "paid"
        self.paid_at = datetime.utcnow()
        self.paid_by_user_id = paid_by_user_id
        self.payment_method = payment_method
        if amount_paid is None:
            self.amount_paid = self.amount_due
        else:
            self.amount_paid = Decimal(str(amount_paid))
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "id": int(self.id) if self.id is not None else None,
            "firebase_bill_id": self.firebase_bill_id,
            "order_id": int(self.order_id) if self.order_id is not None else None,
            "amount_due": str(self.amount_due) if self.amount_due is not None else "0.00",
            "amount_paid": str(self.amount_paid) if self.amount_paid is not None else None,
            "status": self.status,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "paid_by_user_id": int(self.paid_by_user_id) if self.paid_by_user_id is not None else None,
            "payment_method": self.payment_method,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }