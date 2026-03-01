from app import db


class ManagerInterfaceOrder(db.Model):
    __tablename__ = "orders"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer)
    status = db.Column(db.String(20))
    total_amount = db.Column(db.Numeric(10, 2))
    paid_at = db.Column(db.DateTime, nullable=True)

    def is_paid(self) -> bool:
        return (self.status or "").lower() == "paid" or self.paid_at is not None

    def mark_paid(self, paid_at):
        self.status = "paid"
        self.paid_at = paid_at