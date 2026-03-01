from flask import jsonify, render_template

def render_product_detail_page(context):
    return render_template('view_product_details_detail.html', **context)

def jsonify_product_detail(context):
    return jsonify(context)