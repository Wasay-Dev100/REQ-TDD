from app import db
from datetime import datetime

class ProductListing(db.Model):
    __tablename__ = 'product_listings'
    id = db.Column(db.Integer, primary_key=True)
    seller_user_id = db.Column(db.Integer, index=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)