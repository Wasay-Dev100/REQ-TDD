from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    gender = db.Column(db.String(20))
    username = db.Column(db.String(80), unique=True)
    email = db.Column(db.String(120), unique=True)
    contact_number = db.Column(db.String(30))
    birthdate = db.Column(db.Date)
    profile_picture_url = db.Column(db.String(255))
    password_hash = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_profile_dict(self):
        return {
            'name': self.name,
            'gender': self.gender,
            'username': self.username,
            'email': self.email,
            'contact_number': self.contact_number,
            'birthdate': self.birthdate,
            'profile_picture_url': self.profile_picture_url
        }