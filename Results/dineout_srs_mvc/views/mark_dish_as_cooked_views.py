from flask import render_template

def render_food_ready_screen(order):
    return render_template('mark_dish_as_cooked_food_ready.html', order=order)