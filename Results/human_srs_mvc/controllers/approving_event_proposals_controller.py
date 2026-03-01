from functools import wraps

from flask import Blueprint
from flask import abort
from flask import redirect
from flask import request
from flask import session
from flask import url_for

from app import db
from models.approving_event_proposals_event_proposal import EventProposal
from models.user import User
from views.approving_event_proposals_views import render_login
from views.approving_event_proposals_views import render_manage_home
from views.approving_event_proposals_views import render_pending_list
from views.approving_event_proposals_views import render_review_page

approving_event_proposals = Blueprint("approving_event_proposals", __name__, url_prefix="")


def get_current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        return None
    return User.query.filter_by(id=user_id_int).first()


def login_required(view_func):
    if view_func is None or not callable(view_func):
        raise TypeError("view_func must be callable")

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("approving_event_proposals.login"))
        return view_func(*args, **kwargs)

    return wrapper


def coordinator_required(view_func):
    if view_func is None or not callable(view_func):
        raise TypeError("view_func must be callable")

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("approving_event_proposals.login"))
        if not user.is_coordinator():
            abort(403)
        return view_func(*args, **kwargs)

    return wrapper


def require_manage_access(user):
    if user is None:
        return False
    if not hasattr(user, "is_coordinator"):
        return False
    return bool(user.is_coordinator())


def get_pending_proposals():
    return (
        EventProposal.query.filter_by(status="PENDING")
        .order_by(EventProposal.created_at.asc())
        .all()
    )


def get_proposal_or_404(proposal_id):
    try:
        proposal_id_int = int(proposal_id)
    except (TypeError, ValueError):
        abort(404)
    proposal = EventProposal.query.filter_by(id=proposal_id_int).first()
    if not proposal:
        abort(404)
    return proposal


@approving_event_proposals.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        username = str(username).strip()
        password = str(password)

        if not username or not password:
            return render_login(error="Invalid credentials"), 400

        user = User.query.filter_by(username=username).first()
        if not user:
            return render_login(error="Invalid credentials"), 401

        try:
            ok = user.check_password(password)
        except TypeError:
            ok = False

        if not ok:
            return render_login(error="Invalid credentials"), 401

        session["user_id"] = int(user.id)
        return redirect(url_for("approving_event_proposals.manage_home"))

    return render_login()


@approving_event_proposals.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return redirect(url_for("approving_event_proposals.login"))


@approving_event_proposals.route("/manage", methods=["GET"])
@login_required
def manage_home():
    user = get_current_user()
    if not user:
        return redirect(url_for("approving_event_proposals.login"))
    return render_manage_home(user)


@approving_event_proposals.route("/manage/pending-event-requests", methods=["GET"])
@login_required
@coordinator_required
def list_pending_event_requests():
    user = get_current_user()
    proposals = get_pending_proposals()
    return render_pending_list(user, proposals)


@approving_event_proposals.route("/manage/pending-event-requests/<int:proposal_id>", methods=["GET"])
@login_required
@coordinator_required
def review_event_request(proposal_id):
    user = get_current_user()
    proposal = get_proposal_or_404(proposal_id)
    return render_review_page(user, proposal)


@approving_event_proposals.route(
    "/manage/pending-event-requests/<int:proposal_id>/approve",
    methods=["POST"],
)
@login_required
@coordinator_required
def approve_event_request(proposal_id):
    proposal = get_proposal_or_404(proposal_id)
    user = get_current_user()
    proposal.approve(user, request.form.get("comment"))
    db.session.commit()
    return redirect(url_for("approving_event_proposals.list_pending_event_requests"))


@approving_event_proposals.route(
    "/manage/pending-event-requests/<int:proposal_id>/reject",
    methods=["POST"],
)
@login_required
@coordinator_required
def reject_event_request(proposal_id):
    proposal = get_proposal_or_404(proposal_id)
    user = get_current_user()
    proposal.reject(user, request.form.get("comment"))
    db.session.commit()
    return redirect(url_for("approving_event_proposals.list_pending_event_requests"))