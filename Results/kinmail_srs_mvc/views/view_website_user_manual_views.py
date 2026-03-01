def render_help_page(sections: dict[str, dict[str, str]]) -> str:
    return render_template('view_website_user_manual_help.html', sections=sections)