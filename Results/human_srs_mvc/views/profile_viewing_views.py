from flask import render_template


def render_profile_page(user_dict, registered_events):
    if not isinstance(user_dict, dict):
        raise TypeError("user_dict_must_be_dict")
    if registered_events is None:
        registered_events = []
    if not isinstance(registered_events, list):
        raise TypeError("registered_events_must_be_list")
    return render_template(
        "profile_viewing_profile.html",
        user_dict=user_dict,
        registered_events=registered_events,
    )