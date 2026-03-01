from app import db
from datetime import datetime

class Seller(db.Model):
    __tablename__ = 'sellers'

    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(160), nullable=False)
    rating_average = db.Column(db.Float, nullable=True)
    rating_count = db.Column(db.Integer, default=0)
    support_email = db.Column(db.String(120), nullable=True)
    support_phone = db.Column(db.String(40), nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_seller_details_dict(self):
        return {
            "id": self.id,
            "display_name": self.display_name,
            "rating_average": self.rating_average,
            "rating_count": self.rating_count,
            "is_verified": self.is_verified,
            "support_email": self.support_email,
            "support_phone": self.support_phone
        }