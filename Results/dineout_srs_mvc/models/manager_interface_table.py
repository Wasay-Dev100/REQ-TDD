from app import db

class ManagerInterfaceTable(db.Model):
    __tablename__ = 'tables'
    
    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.Integer, unique=True)
    status = db.Column(db.String(20))

    def is_free(self):
        return self.status == 'free'

    def mark_free(self):
        self.status = 'free'
        db.session.commit()

    def mark_occupied(self):
        self.status = 'occupied'
        db.session.commit()