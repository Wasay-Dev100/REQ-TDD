from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import hashlib

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=True)
    middle_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    name = db.Column(db.String(120), nullable=True)  # Alternative name field from view_profile
    gender = db.Column(db.String(20), nullable=True)
    profile_picture_path = db.Column(db.String(255), nullable=True)
    profile_picture_url = db.Column(db.String(255), nullable=True)  # Alternative field name
    contact_number = db.Column(db.String(30), nullable=True)
    birthdate = db.Column(db.Date, nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_email_verified = db.Column(db.Boolean, default=False)
    email_verification_token_hash = db.Column(db.String(255), nullable=True)
    email_verification_sent_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def set_email_verification_token(self, raw_token: str):
        self.email_verification_token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        self.email_verification_sent_at = datetime.utcnow()

    def check_email_verification_token(self, raw_token: str) -> bool:
        if not self.email_verification_token_hash:
            return False
        return self.email_verification_token_hash == hashlib.sha256(raw_token.encode()).hexdigest()

    @staticmethod
    def get_by_login_identifier(identifier: str):
        if identifier is None:
            return None
        identifier = identifier.strip()
        if not identifier:
            return None
        return User.query.filter(
            (User.email == identifier) | (User.username == identifier)
        ).first()

    def to_profile_dict(self):
        return {
            'name': self.name or (f"{self.first_name or ''} {self.last_name or ''}").strip() or None,
            'gender': self.gender,
            'username': self.username,
            'email': self.email,
            'contact_number': self.contact_number,
            'birthdate': self.birthdate.isoformat() if self.birthdate else None,
            'profile_picture_url': self.profile_picture_url or self.profile_picture_path
        }
