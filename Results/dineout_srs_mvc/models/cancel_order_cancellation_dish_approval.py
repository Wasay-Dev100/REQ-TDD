from app import db


class CancelOrderCancellationDishApproval(db.Model):
    __tablename__ = "cancellation_dish_approvals"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    cancellation_request_id = db.Column(db.Integer, index=True)
    order_item_id = db.Column(db.Integer, index=True)
    decision = db.Column(db.String(20), index=True)
    decided_by_user_id = db.Column(db.Integer, nullable=True, index=True)
    decided_at = db.Column(db.DateTime, nullable=True, index=True)
    note = db.Column(db.String(255), nullable=True)

    def is_decided(self):
        return self.decision != "PENDING"