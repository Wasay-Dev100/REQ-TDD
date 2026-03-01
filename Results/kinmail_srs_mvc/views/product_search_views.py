def render_product_search_page(query, category_id, page, per_page, total, products, message, categories):
    return f"""
    <h1>Product Search</h1>
    <form method="get" action="/products/search">
        <input type="text" name="keyword" value="{query}" placeholder="Search products...">
        <select name="category_id">
            <option value="">All Categories</option>
            {''.join(f'<option value="{c.id}" {"selected" if c.id == category_id else ""}>{c.name}</option>' for c in categories)}
        </select>
        <button type="submit">Search</button>
    </form>
    <p>{message}</p>
    <ul>
        {''.join(f'<li>{p.name} - ${p.price}</li>' for p in products)}
    </ul>
    <p>Page {page} of {total // per_page + (1 if total % per_page > 0 else 0)}</p>
    """

def render_product_browse_page(category_id, page, per_page, total, products, message, categories):
    return f"""
    <h1>Browse Products</h1>
    <form method="get" action="/products">
        <select name="category_id">
            <option value="">All Categories</option>
            {''.join(f'<option value="{c.id}" {"selected" if c.id == category_id else ""}>{c.name}</option>' for c in categories)}
        </select>
        <button type="submit">Browse</button>
    </form>
    <p>{message}</p>
    <ul>
        {''.join(f'<li>{p.name} - ${p.price}</li>' for p in products)}
    </ul>
    <p>Page {page} of {total // per_page + (1 if total % per_page > 0 else 0)}</p>
    """

def render_category_list_page(categories):
    return f"""
    <h1>Categories</h1>
    <ul>
        {''.join(f'<li>{c.name}</li>' for c in categories)}
    </ul>
    """