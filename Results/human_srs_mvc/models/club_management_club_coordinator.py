from app import db
from datetime import datetime

class ClubCoordinator(db.Model):
    __tablename__ = 'club_coordinators'

    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, index=True)
    user_id = db.Column(db.Integer, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)