from app import db
from datetime import datetime

class Club(db.Model):
    __tablename__ = 'clubs'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, index=True)
    name = db.Column(db.String(120), unique=True, index=True)
    description = db.Column(db.Text)
    members_list = db.Column(db.Text)
    contact_name = db.Column(db.String(120))
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def touch_updated_at(self):
        self.updated_at = datetime.utcnow()