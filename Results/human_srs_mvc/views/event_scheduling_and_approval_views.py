from flask import render_template


def render_propose_event_form(club, current_user):
    return render_template(
        "event_scheduling_and_approval_propose_event.html",
        club=club,
        club_id=club.id,
        current_user=current_user,
    )


def render_event_requests_list(event_requests, current_user, filters):
    return render_template(
        "event_scheduling_and_approval_event_requests.html",
        event_requests=event_requests,
        current_user=current_user,
        filters=filters or {},
    )


def render_event_request_detail(event_request, current_user):
    return render_template(
        "event_scheduling_and_approval_event_request_detail.html",
        event_request=event_request,
        current_user=current_user,
    )