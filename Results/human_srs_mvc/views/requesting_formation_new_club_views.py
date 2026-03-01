def render_clubs_home(current_user):
    return render_template('requesting_formation_new_club_clubs_home.html', current_user=current_user)

def render_propose_new_club_form(current_user, errors, form_data):
    return render_template('requesting_formation_new_club_propose_new_club.html', current_user=current_user, errors=errors, form_data=form_data)

def render_club_proposal_detail(proposal):
    return render_template('requesting_formation_new_club_proposal_detail.html', proposal=proposal)