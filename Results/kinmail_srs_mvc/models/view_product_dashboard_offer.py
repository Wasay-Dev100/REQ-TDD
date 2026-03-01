from app import db
from datetime import datetime

class ViewProductDashboardOffer(db.Model):
    __tablename__ = 'offers'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, index=True, nullable=False)
    buyer_id = db.Column(db.Integer, index=True, nullable=False)
    offer_price = db.Column(db.Numeric(10, 2), nullable=False)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)