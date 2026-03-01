def render_club_list(clubs):
    return render_template('club_management_club_list.html', clubs=clubs)

def render_club_detail(club, event_images, can_edit):
    return render_template('club_management_club_detail.html', club=club, event_images=event_images, can_edit=can_edit)

def render_club_edit_form(club):
    return render_template('club_management_club_edit.html', club=club)