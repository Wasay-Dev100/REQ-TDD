from app import db

class ChefProfile(db.Model):
    __tablename__ = 'head_chef_order_assignment_chef_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, index=True, nullable=False)
    specialties = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True, index=True)

    def get_specialties_list(self) -> list[str]:
        return self.specialties.split(',')

    def set_specialties_list(self, specialties: list[str]):
        self.specialties = ','.join(specialties)