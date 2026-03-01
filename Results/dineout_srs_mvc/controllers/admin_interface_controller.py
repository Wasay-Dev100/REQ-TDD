from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, request, url_for

from app import db
from models.admin_interface_inventory_item import InventoryItem
from models.admin_interface_menu_item import MenuItem
from models.admin_interface_staff_member import StaffMember
from models.user import User
from views.admin_interface_views import (
    render_admin_home,
    render_inventory_form,
    render_inventory_list,
    render_menu_form,
    render_menu_list,
    render_staff_form,
    render_staff_list,
)

admin_interface_bp = Blueprint("admin_interface", __name__)


def require_admin(current_user):
    if current_user is None or not getattr(current_user, "is_admin", lambda: False)():
        flash("Admin access required", "danger")
        return redirect(url_for("admin_interface.admin_home"))
    return None


def get_current_user() -> User:
    user = User.query.order_by(User.id.asc()).first()
    if user is None:
        user = User(email="admin@example.com", username="admin", role="admin", is_active=True)
        user.set_password("password")
        db.session.add(user)
        db.session.commit()
    return user


def validate_staff_payload(form) -> dict:
    errors = {}
    full_name = (form.get("full_name") or "").strip()
    email = (form.get("email") or "").strip()
    position = (form.get("position") or "").strip()

    if not full_name:
        errors["full_name"] = "Full name is required."
    if not email:
        errors["email"] = "Email is required."
    if not position:
        errors["position"] = "Position is required."

    hourly_rate_raw = (form.get("hourly_rate") or "").strip()
    if hourly_rate_raw:
        try:
            Decimal(hourly_rate_raw)
        except (InvalidOperation, TypeError):
            errors["hourly_rate"] = "Hourly rate must be a number."
    return errors


def validate_menu_payload(form) -> dict:
    errors = {}
    name = (form.get("name") or "").strip()
    price_raw = (form.get("price") or "").strip()

    if not name:
        errors["name"] = "Name is required."
    if not price_raw:
        errors["price"] = "Price is required."
    else:
        try:
            Decimal(price_raw)
        except (InvalidOperation, TypeError):
            errors["price"] = "Price must be a number."
    return errors


def validate_inventory_payload(form) -> dict:
    errors = {}
    name = (form.get("name") or "").strip()
    unit = (form.get("unit") or "").strip()

    if not name:
        errors["name"] = "Name is required."
    if not unit:
        errors["unit"] = "Unit is required."

    for key in ("quantity", "reorder_level"):
        raw = (form.get(key) or "").strip()
        if raw == "":
            continue
        try:
            Decimal(raw)
        except (InvalidOperation, TypeError):
            errors[key] = f"{key} must be a number."
    return errors


@admin_interface_bp.route("/admin", methods=["GET"])
def admin_home():
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp
    return render_admin_home(current_user)


@admin_interface_bp.route("/admin/staff", methods=["GET"])
def staff_list():
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp
    staff_members = StaffMember.query.order_by(StaffMember.id.asc()).all()
    return render_staff_list(current_user, staff_members)


@admin_interface_bp.route("/admin/staff/new", methods=["GET", "POST"])
def staff_create():
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp

    if request.method == "POST":
        errors = validate_staff_payload(request.form)
        if not errors:
            hourly_rate_raw = (request.form.get("hourly_rate") or "").strip()
            staff_member = StaffMember(
                full_name=(request.form.get("full_name") or "").strip(),
                email=(request.form.get("email") or "").strip(),
                phone=(request.form.get("phone") or "").strip() or None,
                position=(request.form.get("position") or "").strip(),
                hourly_rate=(Decimal(hourly_rate_raw) if hourly_rate_raw else None),
                is_active=True,
            )
            db.session.add(staff_member)
            db.session.commit()
            flash("Staff member created successfully", "success")
            return redirect(url_for("admin_interface.staff_list"))
        return render_staff_form(current_user, None, errors, "create")

    return render_staff_form(current_user, None, {}, "create")


@admin_interface_bp.route("/admin/staff/<int:staff_id>/edit", methods=["GET", "POST"])
def staff_update(staff_id):
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp

    staff_member = StaffMember.query.get_or_404(staff_id)
    if request.method == "POST":
        errors = validate_staff_payload(request.form)
        if not errors:
            hourly_rate_raw = (request.form.get("hourly_rate") or "").strip()
            staff_member.full_name = (request.form.get("full_name") or "").strip()
            staff_member.email = (request.form.get("email") or "").strip()
            staff_member.phone = (request.form.get("phone") or "").strip() or None
            staff_member.position = (request.form.get("position") or "").strip()
            staff_member.hourly_rate = Decimal(hourly_rate_raw) if hourly_rate_raw else None
            db.session.commit()
            flash("Staff member updated successfully", "success")
            return redirect(url_for("admin_interface.staff_list"))
        return render_staff_form(current_user, staff_member, errors, "edit")

    return render_staff_form(current_user, staff_member, {}, "edit")


@admin_interface_bp.route("/admin/staff/<int:staff_id>/delete", methods=["POST"])
def staff_delete(staff_id):
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp

    staff_member = StaffMember.query.get_or_404(staff_id)
    db.session.delete(staff_member)
    db.session.commit()
    flash("Staff member deleted successfully", "success")
    return redirect(url_for("admin_interface.staff_list"))


@admin_interface_bp.route("/admin/menu", methods=["GET"])
def menu_list():
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp

    menu_items = MenuItem.query.order_by(MenuItem.id.asc()).all()
    return render_menu_list(current_user, menu_items)


@admin_interface_bp.route("/admin/menu/new", methods=["GET", "POST"])
def menu_create():
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp

    if request.method == "POST":
        errors = validate_menu_payload(request.form)
        if not errors:
            menu_item = MenuItem(
                name=(request.form.get("name") or "").strip(),
                description=(request.form.get("description") or "").strip() or None,
                price=Decimal((request.form.get("price") or "0").strip()),
                is_available=True,
            )
            db.session.add(menu_item)
            db.session.commit()
            flash("Menu item created successfully", "success")
            return redirect(url_for("admin_interface.menu_list"))
        return render_menu_form(current_user, None, errors, "create")

    return render_menu_form(current_user, None, {}, "create")


@admin_interface_bp.route("/admin/menu/<int:menu_item_id>/edit", methods=["GET", "POST"])
def menu_update(menu_item_id):
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp

    menu_item = MenuItem.query.get_or_404(menu_item_id)
    if request.method == "POST":
        errors = validate_menu_payload(request.form)
        if not errors:
            menu_item.name = (request.form.get("name") or "").strip()
            menu_item.description = (request.form.get("description") or "").strip() or None
            menu_item.price = Decimal((request.form.get("price") or "0").strip())
            db.session.commit()
            flash("Menu item updated successfully", "success")
            return redirect(url_for("admin_interface.menu_list"))
        return render_menu_form(current_user, menu_item, errors, "edit")

    return render_menu_form(current_user, menu_item, {}, "edit")


@admin_interface_bp.route("/admin/menu/<int:menu_item_id>/delete", methods=["POST"])
def menu_delete(menu_item_id):
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp

    menu_item = MenuItem.query.get_or_404(menu_item_id)
    db.session.delete(menu_item)
    db.session.commit()
    flash("Menu item deleted successfully", "success")
    return redirect(url_for("admin_interface.menu_list"))


@admin_interface_bp.route("/admin/inventory", methods=["GET"])
def inventory_list():
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp

    inventory_items = InventoryItem.query.order_by(InventoryItem.id.asc()).all()
    return render_inventory_list(current_user, inventory_items)


@admin_interface_bp.route("/admin/inventory/new", methods=["GET", "POST"])
def inventory_create():
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp

    if request.method == "POST":
        errors = validate_inventory_payload(request.form)
        if not errors:
            quantity_raw = (request.form.get("quantity") or "").strip()
            reorder_raw = (request.form.get("reorder_level") or "").strip()
            inventory_item = InventoryItem(
                name=(request.form.get("name") or "").strip(),
                unit=(request.form.get("unit") or "").strip(),
                quantity=Decimal(quantity_raw) if quantity_raw else Decimal("0"),
                reorder_level=Decimal(reorder_raw) if reorder_raw else Decimal("0"),
                is_active=True,
            )
            db.session.add(inventory_item)
            db.session.commit()
            flash("Inventory item created successfully", "success")
            return redirect(url_for("admin_interface.inventory_list"))
        return render_inventory_form(current_user, None, errors, "create")

    return render_inventory_form(current_user, None, {}, "create")


@admin_interface_bp.route("/admin/inventory/<int:inventory_item_id>/edit", methods=["GET", "POST"])
def inventory_update(inventory_item_id):
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp

    inventory_item = InventoryItem.query.get_or_404(inventory_item_id)
    if request.method == "POST":
        errors = validate_inventory_payload(request.form)
        if not errors:
            quantity_raw = (request.form.get("quantity") or "").strip()
            reorder_raw = (request.form.get("reorder_level") or "").strip()
            inventory_item.name = (request.form.get("name") or "").strip()
            inventory_item.unit = (request.form.get("unit") or "").strip()
            inventory_item.quantity = Decimal(quantity_raw) if quantity_raw else Decimal("0")
            inventory_item.reorder_level = Decimal(reorder_raw) if reorder_raw else Decimal("0")
            db.session.commit()
            flash("Inventory item updated successfully", "success")
            return redirect(url_for("admin_interface.inventory_list"))
        return render_inventory_form(current_user, inventory_item, errors, "edit")

    return render_inventory_form(current_user, inventory_item, {}, "edit")


@admin_interface_bp.route("/admin/inventory/<int:inventory_item_id>/delete", methods=["POST"])
def inventory_delete(inventory_item_id):
    current_user = get_current_user()
    resp = require_admin(current_user)
    if resp is not None:
        return resp

    inventory_item = InventoryItem.query.get_or_404(inventory_item_id)
    db.session.delete(inventory_item)
    db.session.commit()
    flash("Inventory item deleted successfully", "success")
    return redirect(url_for("admin_interface.inventory_list"))