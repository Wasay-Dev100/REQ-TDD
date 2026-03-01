from flask import render_template


def render_login(error=None):
    return render_template("approving_event_proposals_login.html", error=error)


def render_manage_home(user):
    return render_template("approving_event_proposals_manage.html", user=user)


def render_pending_list(user, proposals):
    return render_template(
        "approving_event_proposals_pending_list.html",
        user=user,
        proposals=proposals,
    )


def render_review_page(user, proposal, error=None):
    return render_template(
        "approving_event_proposals_review.html",
        user=user,
        proposal=proposal,
        error=error,
    )