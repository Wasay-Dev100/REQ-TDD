from flask import Flask
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'

db = SQLAlchemy(app)
mail = Mail(app)

# Import blueprints after db and mail initialization
from controllers.add_edit_delete_menu_items_controller import add_edit_delete_menu_items_bp
from controllers.add_edit_delete_staff_members_controller import add_edit_delete_staff_members_bp
from controllers.admin_database_management_controller import admin_database_management_bp
from controllers.admin_interface_controller import admin_interface_bp  # noqa: E402
from controllers.admin_management_controller import admin_management_bp
from controllers.cancel_order_controller import cancel_order_bp
from controllers.chef_order_queue_controller import chef_order_queue_bp
from controllers.customer_feedback_controller import customer_feedback_bp
from controllers.customer_help_controller import customer_help_bp
from controllers.customer_order_management_controller import customer_order_management_bp
from controllers.customer_order_management_controller import customer_order_management_bp  # noqa: E402
from controllers.edit_order_controller import edit_order_bp
from controllers.hall_manager_operations_controller import hall_manager_operations_bp
from controllers.head_chef_order_assignment_controller import head_chef_order_assignment_bp
from controllers.manager_interface_controller import manager_interface_bp
from controllers.mark_dish_as_cooked_controller import mark_dish_as_cooked_bp
from controllers.place_order_controller import place_order_bp
from controllers.request_bill_controller import request_bill_bp

# Register all blueprints
app.register_blueprint(add_edit_delete_menu_items_bp)
app.register_blueprint(add_edit_delete_staff_members_bp)
app.register_blueprint(admin_database_management_bp)
app.register_blueprint(admin_interface_bp)
app.register_blueprint(admin_management_bp)
app.register_blueprint(cancel_order_bp)
app.register_blueprint(chef_order_queue_bp)
app.register_blueprint(customer_feedback_bp)
app.register_blueprint(customer_help_bp)
app.register_blueprint(customer_order_management_bp)
app.register_blueprint(edit_order_bp)
app.register_blueprint(hall_manager_operations_bp)
app.register_blueprint(head_chef_order_assignment_bp)
app.register_blueprint(manager_interface_bp)
app.register_blueprint(mark_dish_as_cooked_bp)
app.register_blueprint(place_order_bp)
app.register_blueprint(request_bill_bp)

if __name__ == '__main__':
    app.run(debug=True)
