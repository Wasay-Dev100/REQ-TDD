def render_help_page(sections):
    return render_template('view_user_manual_help.html', sections=sections)

def serialize_manual(sections):
    return {
        'manual': {
            'sections': [section.to_dict() for section in sections]
        }
    }