from flask import Flask
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['MAIL_DEFAULT_SENDER'] = 'noreply@example.com'
app.config['MAIL_SERVER'] = 'smtp.example.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@example.com'
app.config['MAIL_PASSWORD'] = 'your-email-password'

db = SQLAlchemy(app)
mail = Mail(app)

# Import blueprints after db and mail initialization
from controllers.approving_new_club_requests_controller import approving_new_club_requests_bp
from controllers.club_management_controller import club_management_bp
from controllers.event_registration_controller import event_registration_bp
from controllers.event_scheduling_and_approval_controller import event_scheduling_and_approval_bp
from controllers.profile_viewing_controller import profile_viewing_bp

# Register all blueprints
app.register_blueprint(approving_new_club_requests_bp)
app.register_blueprint(club_management_bp)
app.register_blueprint(event_registration_bp)
app.register_blueprint(event_scheduling_and_approval_bp)
app.register_blueprint(profile_viewing_bp)

if __name__ == '__main__':
    app.run(debug=True)
