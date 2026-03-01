from app import db
from datetime import datetime

class ClubEventImage(db.Model):
    __tablename__ = 'club_event_images'

    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, index=True)
    title = db.Column(db.String(120))
    image_url = db.Column(db.String(500))
    event_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)