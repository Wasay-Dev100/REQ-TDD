from app import db

class Product(db.Model):
    __tablename__ = 'products'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), index=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    price_cents = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    is_available = db.Column(db.Boolean, default=True)
    prep_time_minutes = db.Column(db.Integer, nullable=True)