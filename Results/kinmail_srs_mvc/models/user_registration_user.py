from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import hashlib

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=False)
    gender = db.Column(db.Enum('male', 'female', 'other', 'prefer_not_to_say', name='gender_enum'), nullable=False)
    profile_picture_path = db.Column(db.String(255), nullable=True)
    contact_number = db.Column(db.String(20), nullable=False)
    birthdate = db.Column(db.Date, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_email_verified = db.Column(db.Boolean, default=False)
    email_verification_token_hash = db.Column(db.String(255), nullable=True)
    email_verification_sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def set_email_verification_token(self, raw_token: str):
        self.email_verification_token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    def check_email_verification_token(self, raw_token: str) -> bool:
        return self.email_verification_token_hash == hashlib.sha256(raw_token.encode()).hexdigest()