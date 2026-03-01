from flask import Blueprint, request, jsonify
from app import db
from models.user import User
from models.category import Category
from models.product import Product
from models.admin_database_management_inventory_item import InventoryItem
from models.admin_database_management_employee import Employee

admin_db = Blueprint('admin_db', __name__, url_prefix='/admin')

def require_admin(current_user: User):
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403

def parse_bool_arg(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() in ['true', '1', 'yes']

def serialize_product(product: Product) -> dict:
    return {
        'id': product.id,
        'name': product.name,
        'sku': product.sku,
        'description': product.description,
        'price_cents': product.price_cents,
        'is_active': product.is_active,
        'category_id': product.category_id,
        'created_at': product.created_at.isoformat(),
        'updated_at': product.updated_at.isoformat()
    }

def serialize_category(category: Category) -> dict:
    return {
        'id': category.id,
        'name': category.name,
        'description': category.description,
        'is_active': category.is_active,
        'created_at': category.created_at.isoformat(),
        'updated_at': category.updated_at.isoformat()
    }

def serialize_inventory_item(item: InventoryItem) -> dict:
    return {
        'id': item.id,
        'product_id': item.product_id,
        'quantity_on_hand': item.quantity_on_hand,
        'reorder_level': item.reorder_level,
        'location': item.location,
        'updated_at': item.updated_at.isoformat()
    }

def serialize_employee(employee: Employee) -> dict:
    return {
        'id': employee.id,
        'user_id': employee.user_id,
        'employee_number': employee.employee_number,
        'first_name': employee.first_name,
        'last_name': employee.last_name,
        'phone': employee.phone,
        'role': employee.role,
        'hourly_rate_cents': employee.hourly_rate_cents,
        'is_active': employee.is_active,
        'hired_at': employee.hired_at.isoformat() if employee.hired_at else None,
        'terminated_at': employee.terminated_at.isoformat() if employee.terminated_at else None,
        'created_at': employee.created_at.isoformat(),
        'updated_at': employee.updated_at.isoformat()
    }

@admin_db.route('/menu/items', methods=['GET'])
def list_menu_items():
    products = Product.query.all()
    return jsonify([serialize_product(product) for product in products])

@admin_db.route('/menu/items', methods=['POST'])
def create_menu_item():
    data = request.json
    new_product = Product(
        name=data['name'],
        sku=data['sku'],
        description=data.get('description'),
        price_cents=data['price_cents'],
        is_active=data.get('is_active', True),
        category_id=data['category_id']
    )
    db.session.add(new_product)
    db.session.commit()
    return jsonify(serialize_product(new_product)), 201

@admin_db.route('/menu/items/<int:product_id>', methods=['GET'])
def get_menu_item(product_id):
    product = Product.query.get_or_404(product_id)
    return jsonify(serialize_product(product))

@admin_db.route('/menu/items/<int:product_id>', methods=['PUT'])
def update_menu_item(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.json
    product.name = data.get('name', product.name)
    product.sku = data.get('sku', product.sku)
    product.description = data.get('description', product.description)
    product.price_cents = data.get('price_cents', product.price_cents)
    product.is_active = data.get('is_active', product.is_active)
    product.category_id = data.get('category_id', product.category_id)
    db.session.commit()
    return jsonify(serialize_product(product))

@admin_db.route('/menu/items/<int:product_id>', methods=['DELETE'])
def delete_menu_item(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Product deleted'})

@admin_db.route('/menu/categories', methods=['GET'])
def list_categories():
    categories = Category.query.all()
    return jsonify([serialize_category(category) for category in categories])

@admin_db.route('/menu/categories', methods=['POST'])
def create_category():
    data = request.json
    new_category = Category(
        name=data['name'],
        description=data.get('description'),
        is_active=data.get('is_active', True)
    )
    db.session.add(new_category)
    db.session.commit()
    return jsonify(serialize_category(new_category)), 201

@admin_db.route('/menu/categories/<int:category_id>', methods=['GET'])
def get_category(category_id):
    category = Category.query.get_or_404(category_id)
    return jsonify(serialize_category(category))

@admin_db.route('/menu/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    category = Category.query.get_or_404(category_id)
    data = request.json
    category.name = data.get('name', category.name)
    category.description = data.get('description', category.description)
    category.is_active = data.get('is_active', category.is_active)
    db.session.commit()
    return jsonify(serialize_category(category))

@admin_db.route('/menu/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    return jsonify({'message': 'Category deleted'})

@admin_db.route('/inventory', methods=['GET'])
def list_inventory():
    inventory_items = InventoryItem.query.all()
    return jsonify([serialize_inventory_item(item) for item in inventory_items])

@admin_db.route('/inventory', methods=['POST'])
def create_inventory_item():
    data = request.json
    new_item = InventoryItem(
        product_id=data['product_id'],
        quantity_on_hand=data.get('quantity_on_hand', 0),
        reorder_level=data.get('reorder_level', 0),
        location=data.get('location')
    )
    db.session.add(new_item)
    db.session.commit()
    return jsonify(serialize_inventory_item(new_item)), 201

@admin_db.route('/inventory/<int:inventory_item_id>', methods=['GET'])
def get_inventory_item(inventory_item_id):
    item = InventoryItem.query.get_or_404(inventory_item_id)
    return jsonify(serialize_inventory_item(item))

@admin_db.route('/inventory/<int:inventory_item_id>', methods=['PUT'])
def update_inventory_item(inventory_item_id):
    item = InventoryItem.query.get_or_404(inventory_item_id)
    data = request.json
    item.quantity_on_hand = data.get('quantity_on_hand', item.quantity_on_hand)
    item.reorder_level = data.get('reorder_level', item.reorder_level)
    item.location = data.get('location', item.location)
    db.session.commit()
    return jsonify(serialize_inventory_item(item))

@admin_db.route('/inventory/<int:inventory_item_id>', methods=['DELETE'])
def delete_inventory_item(inventory_item_id):
    item = InventoryItem.query.get_or_404(inventory_item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': 'Inventory item deleted'})

@admin_db.route('/employees', methods=['GET'])
def list_employees():
    employees = Employee.query.all()
    return jsonify([serialize_employee(employee) for employee in employees])

@admin_db.route('/employees', methods=['POST'])
def create_employee():
    data = request.json
    new_employee = Employee(
        user_id=data['user_id'],
        employee_number=data['employee_number'],
        first_name=data['first_name'],
        last_name=data['last_name'],
        phone=data.get('phone'),
        role=data['role'],
        hourly_rate_cents=data.get('hourly_rate_cents'),
        is_active=data.get('is_active', True),
        hired_at=data.get('hired_at'),
        terminated_at=data.get('terminated_at')
    )
    db.session.add(new_employee)
    db.session.commit()
    return jsonify(serialize_employee(new_employee)), 201

@admin_db.route('/employees/<int:employee_id>', methods=['GET'])
def get_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    return jsonify(serialize_employee(employee))

@admin_db.route('/employees/<int:employee_id>', methods=['PUT'])
def update_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    data = request.json
    employee.first_name = data.get('first_name', employee.first_name)
    employee.last_name = data.get('last_name', employee.last_name)
    employee.phone = data.get('phone', employee.phone)
    employee.role = data.get('role', employee.role)
    employee.hourly_rate_cents = data.get('hourly_rate_cents', employee.hourly_rate_cents)
    employee.is_active = data.get('is_active', employee.is_active)
    employee.hired_at = data.get('hired_at', employee.hired_at)
    employee.terminated_at = data.get('terminated_at', employee.terminated_at)
    db.session.commit()
    return jsonify(serialize_employee(employee))

@admin_db.route('/employees/<int:employee_id>', methods=['DELETE'])
def delete_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    db.session.delete(employee)
    db.session.commit()
    return jsonify({'message': 'Employee deleted'})