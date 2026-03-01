from datetime import datetime
from app import db

class ClubProposal(db.Model):
    __tablename__ = 'club_proposals'

    id = db.Column(db.Integer, primary_key=True)
    proposed_name = db.Column(db.String(120), unique=True)
    description = db.Column(db.Text)
    mission_statement = db.Column(db.Text)
    proposed_by_user_id = db.Column(db.Integer, index=True)
    status = db.Column(db.String(30), default='PENDING_COORDINATOR', index=True)
    coordinator_reviewed_by_user_id = db.Column(db.Integer, nullable=True, index=True)
    coordinator_reviewed_at = db.Column(db.DateTime, nullable=True)
    coordinator_decision = db.Column(db.String(20), nullable=True)
    coordinator_notes = db.Column(db.Text, nullable=True)
    admin_reviewed_by_user_id = db.Column(db.Integer, nullable=True, index=True)
    admin_reviewed_at = db.Column(db.DateTime, nullable=True)
    admin_decision = db.Column(db.String(20), nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def can_be_seen_by_admin(self):
        return self.status == 'APPROVED_BY_COORDINATOR'

    def apply_coordinator_decision(self, reviewer_user, decision, notes):
        self.coordinator_reviewed_by_user_id = reviewer_user.id
        self.coordinator_reviewed_at = datetime.utcnow()
        self.coordinator_decision = decision
        self.coordinator_notes = notes
        self.status = 'APPROVED_BY_COORDINATOR' if decision == 'APPROVE' else 'REJECTED_BY_COORDINATOR'
        db.session.commit()

    def apply_admin_decision(self, reviewer_user, decision, notes):
        self.admin_reviewed_by_user_id = reviewer_user.id
        self.admin_reviewed_at = datetime.utcnow()
        self.admin_decision = decision
        self.admin_notes = notes
        self.status = 'APPROVED_BY_ADMIN' if decision == 'APPROVE' else 'REJECTED_BY_ADMIN'
        db.session.commit()