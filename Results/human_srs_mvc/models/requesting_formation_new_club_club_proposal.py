from app import db
from datetime import datetime

class ClubProposal(db.Model):
    __tablename__ = 'club_proposals'

    id = db.Column(db.Integer, primary_key=True)
    proposer_user_id = db.Column(db.Integer, index=True, nullable=False)
    club_name = db.Column(db.String(120), unique=True, nullable=False)
    club_category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    objectives = db.Column(db.Text, nullable=False)
    proposed_activities = db.Column(db.Text, nullable=False)
    faculty_advisor_name = db.Column(db.String(120), nullable=False)
    faculty_advisor_email = db.Column(db.String(120), nullable=False)
    co_founders = db.Column(db.Text, nullable=False)
    expected_members_count = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='submitted', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'proposer_user_id': self.proposer_user_id,
            'club_name': self.club_name,
            'club_category': self.club_category,
            'description': self.description,
            'objectives': self.objectives,
            'proposed_activities': self.proposed_activities,
            'faculty_advisor_name': self.faculty_advisor_name,
            'faculty_advisor_email': self.faculty_advisor_email,
            'co_founders': self.co_founders,
            'expected_members_count': self.expected_members_count,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }