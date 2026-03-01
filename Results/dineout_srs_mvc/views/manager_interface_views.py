def render_free_tables_page(tables) -> str:
    table_list_html = "".join(
        [
            f'<li>Table {table["table_number"]} is {table["status"]}</li>'
            for table in tables
        ]
    )
    return f"""
    <html>
    <head><title>Free Tables</title></head>
    <body>
        <h1>Free Tables</h1>
        <ul>
            {table_list_html}
        </ul>
    </body>
    </html>
    """