from app import db
from datetime import datetime


class Order(db.Model):
    __tablename__ = "orders"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(32), unique=True, nullable=False)
    table_no = db.Column(db.String(16), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def mark_bill_requested(self):
        self.status = "bill_requested"

    def mark_paid(self):
        self.status = "paid"

    def is_payable(self) -> bool:
        return self.status == "bill_requested"