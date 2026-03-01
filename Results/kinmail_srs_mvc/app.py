from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-email-password'
app.config['MAIL_DEFAULT_SENDER'] = 'your-email@gmail.com'

db = SQLAlchemy(app)
mail = Mail(app)

# Import blueprints after db and mail initialization
from controllers.add_product_controller import add_product_bp
from controllers.contact_developer_controller import contact_developer_bp
from controllers.contact_the_developer_controller import contact_the_developer_bp
from controllers.login_controller import login_bp
from controllers.product_search_controller import product_search_bp
from controllers.register_to_the_website_controller import register_to_the_website_bp
from controllers.user_login_controller import user_login_bp
from controllers.user_registration_controller import user_registration_bp
from controllers.view_product_dashboard_controller import view_product_dashboard
from controllers.view_product_details_controller import view_product_details_bp
from controllers.view_profile_controller import view_profile_bp
from controllers.view_user_manual_controller import view_user_manual_bp
from controllers.view_website_user_manual_controller import view_website_user_manual_bp

# Register all blueprints
app.register_blueprint(add_product_bp)
app.register_blueprint(contact_developer_bp)
app.register_blueprint(contact_the_developer_bp)
app.register_blueprint(login_bp)
app.register_blueprint(product_search_bp)
app.register_blueprint(register_to_the_website_bp)
app.register_blueprint(user_login_bp)
app.register_blueprint(user_registration_bp)
app.register_blueprint(view_product_dashboard)
app.register_blueprint(view_product_details_bp)
app.register_blueprint(view_profile_bp)
app.register_blueprint(view_user_manual_bp)
app.register_blueprint(view_website_user_manual_bp)

if __name__ == '__main__':
    app.run(debug=True)
