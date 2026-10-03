# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from flask import Blueprint, abort, flash, jsonify, make_response, redirect, request, url_for
from flask_babel import gettext as _

from .. import constants
from ..admin import admin_required
from ..render_template import render_title_template
from ..usermanagement import login_required_if_no_ano, user_login_required
from ..cw_login import current_user
from .comments import (
    add_comment,
    delete_comment,
    recent_comments,
    set_hidden,
    update_comment,
    user_name,
)
from .branding import delete_asset, get_asset, save_upload
from .css_sanitize import sanitize_css
from .heroes import add_hero, delete_hero, list_heroes, move_hero, search_books, shelf_choices
from .login_collage import book_for_slot, catalog_payload, cover_response, covers_enabled, thumbnail_response
from .reading import scan_all
from .ratings.service import enqueue_ratings, hardcover_token, save_hardcover_token, save_manual_rating
from .store import get_setting, set_setting
from .sidebar import sidebar_lists
from .heroes import hero_slides
from .home import _hero_book_ids, discover_cards
from .home_rows import create_custom, delete_custom, editor_rows, page_rows, save_override

library_ui_bp = Blueprint("library_ui", __name__)


@library_ui_bp.route("/library/suggest")
@login_required_if_no_ano
def suggest_books():
    query = (request.args.get("q") or "").strip()
    books = search_books(query, limit=8)
    results = []
    for book in books:
        authors = ", ".join(author.name.replace("|", ", ") for author in book.authors)
        results.append({
            "id": book.id,
            "title": book.title,
            "author": authors,
            "url": url_for("web.show_book", book_id=book.id),
        })
    return jsonify(results)


@library_ui_bp.route("/library/discover/shelf", methods=["POST"])
@login_required_if_no_ano
def discover_shelf():
    from .discover_page import shelf_response

    return shelf_response()


@library_ui_bp.route("/library/discover")
@login_required_if_no_ano
def discover_feed():
    raw = request.args.get("exclude") or ""
    shown = []
    for piece in raw.split(","):
        piece = piece.strip()
        if piece.isdigit():
            shown.append(int(piece))
    return jsonify(discover_cards(3, exclude_ids=shown, hero_ids=_hero_book_ids(hero_slides())))


@library_ui_bp.route("/library/book/<int:book_id>/flags", methods=["POST"])
@user_login_required
def book_flags(book_id):
    from .flags import set_flag

    kind = (request.form.get("kind") or "").strip()
    on = request.form.get("on") == "1"
    return jsonify(set_flag(kind, book_id, on))


@library_ui_bp.route("/library/sidebar")
@login_required_if_no_ano
def sidebar_summary():
    return jsonify(sidebar_lists())


@library_ui_bp.route("/friends")
@user_login_required
def friends_page():
    from .friends import helper_line, initials, list_friends, recent_sends

    people = []
    for friend in list_friends():
        people.append({
            "friend": friend,
            "initials": initials(friend.name),
            "recent": recent_sends(friend.id),
        })
    return render_title_template(
        "library_friends.html",
        title=_("Friends"),
        page="friends",
        people=people,
        helper=helper_line(),
    )


@library_ui_bp.route("/friends/picker")
@user_login_required
def friends_picker():
    from .friends import initials, list_friends

    payload = []
    for friend in list_friends():
        payload.append({
            "id": friend.id,
            "name": friend.name,
            "email": friend.kindle_email,
            "initials": initials(friend.name),
        })
    return jsonify(payload)


@library_ui_bp.route("/friends/save", methods=["POST"])
@user_login_required
def friends_save():
    from .friends import save_friend

    raw_id = (request.form.get("id") or "").strip()
    friend_id = int(raw_id) if raw_id.isdigit() else None
    try:
        friend = save_friend(request.form.get("name"), request.form.get("kindle_email"), friend_id)
    except ValueError as error:
        return jsonify(ok=False, message=str(error)), 400
    return jsonify(ok=True, id=friend.id)


@library_ui_bp.route("/friends/<int:friend_id>/delete", methods=["POST"])
@user_login_required
def friends_delete(friend_id):
    from .friends import delete_friend

    delete_friend(friend_id)
    return jsonify(ok=True)


@library_ui_bp.route("/library/book/<int:book_id>/send-friend", methods=["POST"])
@user_login_required
def send_to_friends(book_id):
    from .friends import send_book

    result = send_book(
        book_id,
        request.form.getlist("friend_id"),
        request.form.get("book_format") or "",
        request.form.get("convert") or "0",
    )
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@library_ui_bp.route("/genres")
@login_required_if_no_ano
def genres_home():
    if not current_user.check_visibility(constants.SIDEBAR_CATEGORY):
        abort(404)
    from .browse import render_genres_home
    return render_genres_home()


@library_ui_bp.route("/genres/<path:name>")
@login_required_if_no_ano
def genre_page(name):
    if not current_user.check_visibility(constants.SIDEBAR_CATEGORY):
        abort(404)
    from .shelf_config import tag_hidden
    folded = (name or "").replace("-", " ").replace("_", " ").strip()
    if tag_hidden(folded):
        return redirect(url_for("library_ui.genres_home"))
    from .browse import render_genre_page
    return render_genre_page(name)


@library_ui_bp.route("/admin/fill-gaps", methods=["GET", "POST"])
@user_login_required
@admin_required
def fill_gaps():
    from .gaps import import_csv, save_book_gap, save_series_gap

    errors = []
    if request.method == "POST":
        action = request.form.get("action") or ""
        if action == "book":
            problem = save_book_gap(
                request.form.get("book_id"),
                request.form.get("label"),
                request.form.get("type"),
                request.form.get("year"),
                request.form.get("source_url"),
            )
            flash(problem or _("Accolade saved."), category="error" if problem else "success")
        elif action == "series":
            save_series_gap(request.form.get("series_id"), request.form.get("description"), request.form.get("source_url"))
            flash(_("Series description saved."), category="success")
        elif action == "import":
            saved, errors = import_csv(request.form.get("csv") or "")
            flash(_("Imported %(count)s rows.", count=saved), category="success")
        return redirect(url_for("library_ui.fill_gaps")) if action != "import" or not errors else _fill_page(errors)
    return _fill_page(errors)


def _fill_page(errors):
    from .gaps import gap_page

    page = gap_page()
    return render_title_template(
        "library_fill_gaps.html",
        title=_("Fill gaps"),
        page="fillgaps",
        books=page["books"],
        series=page["series"],
        text=page["text"],
        errors=errors,
    )


@library_ui_bp.route("/admin/coverage")
@user_login_required
@admin_required
def library_coverage():
    from .coverage import build_report

    return render_title_template(
        "library_coverage.html",
        title=_("Library coverage"),
        page="coverage",
        report=build_report(),
    )


@library_ui_bp.route("/admin/library/css", methods=["GET", "POST"])
@user_login_required
@admin_required
def custom_css():
    if request.method == "POST":
        cleaned = sanitize_css(request.form.get("custom_css", ""))
        set_setting("custom_css", cleaned)
        flash(_("Custom CSS saved."), category="success")
        return redirect(url_for("library_ui.custom_css"))

    return render_title_template(
        "library_ui_css.html",
        title=_("Custom CSS"),
        page="admincss",
        custom_css=get_setting("custom_css", ""),
    )


@library_ui_bp.route("/library/branding/<kind>")
def brand_asset(kind):
    asset = get_asset(kind)
    if asset is None:
        abort(404)
    response = make_response(asset.data)
    response.headers["Content-Type"] = asset.mime
    response.headers["Cache-Control"] = "public, max-age=86400"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@library_ui_bp.route("/login-covers")
def login_covers():
    response = jsonify(catalog_payload())
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@library_ui_bp.route("/library/login-thumb/<int:book_id>")
def login_thumb(book_id):
    return thumbnail_response(book_id)


@library_ui_bp.route("/library/login-cover/<int:slot>")
def login_cover(slot):
    book = book_for_slot(slot)
    if book is None:
        abort(404)
    return cover_response(book)


@library_ui_bp.route("/admin/library/branding", methods=["GET", "POST"])
@user_login_required
@admin_required
def branding():
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "remove_logo":
            delete_asset("logo")
            flash(_("Logo removed."), category="success")
        elif action == "remove_favicon":
            delete_asset("favicon")
            flash(_("Favicon removed."), category="success")
        elif action == "logo":
            error = save_upload("logo", request.files.get("image"))
            flash(error or _("Logo saved."), category="error" if error else "success")
        elif action == "favicon":
            error = save_upload("favicon", request.files.get("image"))
            flash(error or _("Favicon saved."), category="error" if error else "success")
        elif action == "login_covers":
            set_setting("login_covers", "1" if request.form.get("show_login_covers") else "0")
            flash(_("Login covers saved."), category="success")
        else:
            flash(_("Unknown image."), category="error")
        return redirect(url_for("library_ui.branding"))

    return render_title_template(
        "library_ui_branding.html",
        title=_("Logo and Favicon"),
        page="adminbrand",
        login_covers=covers_enabled(),
    )


@library_ui_bp.route("/admin/library/heroes", methods=["GET", "POST"])
@user_login_required
@admin_required
def heroes():
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "add":
            kind = request.form.get("kind", "book")
            target = request.form.get("book_id") if kind == "book" else request.form.get("shelf_id")
            ok = add_hero(kind, target, request.form.get("headline", ""), request.form.get("blurb", ""))
            if ok:
                flash(_("Featured item saved."), category="success")
            else:
                flash(_("Choose a book or a collection first."), category="error")
        elif action == "remove":
            delete_hero(request.form.get("hero_id", "0"))
            flash(_("Featured item removed."), category="success")
        elif action == "up":
            move_hero(request.form.get("hero_id", "0"), -1)
        elif action == "down":
            move_hero(request.form.get("hero_id", "0"), 1)
        return redirect(url_for("library_ui.heroes", q=request.form.get("q", "")))

    query = request.args.get("q", "")
    return render_title_template(
        "library_ui_heroes.html",
        title=_("Featured"),
        page="adminhero",
        heroes=list_heroes(),
        matches=search_books(query),
        shelves=shelf_choices(),
        query=query,
    )


@library_ui_bp.route("/admin/library/rows", methods=["GET", "POST"])
@user_login_required
@admin_required
def home_shelves():
    if request.method == "POST":
        action = request.form.get("action") or "save"
        if action == "remove":
            delete_custom(request.form.get("slug", ""))
            flash(_("Shelf removed."), category="success")
        elif action == "create":
            created = create_custom(
                request.form.get("title", ""),
                request.form.get("subtitle", ""),
                request.form.get("source_kind", ""),
                request.form.get("source_name", ""),
            )
            if created:
                flash(_("Shelf saved."), category="success")
            else:
                flash(_("Could not find that."), category="error")
        else:
            save_override(
                request.form.get("slug", ""),
                request.form.get("title", ""),
                request.form.get("subtitle", ""),
                request.form.get("pinned"),
                request.form.get("hidden"),
                request.form.get("sort_order"),
            )
            flash(_("Shelf saved."), category="success")
        return redirect(url_for("library_ui.home_shelves"))
    return render_title_template(
        "library_ui_rows.html",
        title=_("Home shelves"),
        page="adminrows",
        shelves=editor_rows(),
        live_rows=page_rows(),
    )


@library_ui_bp.route("/series/<int:series_id>/description", methods=["POST"])
@admin_required
def save_series_description(series_id):
    from .series_info import save_manual

    save_manual(series_id, request.form.get("description"), request.form.get("source_url"))
    flash(_("Series description saved."), category="success")
    nxt = (request.form.get("next") or "").strip()
    if nxt.startswith("/admin/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect("/series/%s" % int(series_id))


@library_ui_bp.route("/admin/library/series")
@user_login_required
@admin_required
def series_descriptions():
    from .series_info import editor_rows

    return render_title_template(
        "library_series_admin.html",
        title=_("Series descriptions"),
        page="adminseries",
        series=editor_rows(),
    )


@library_ui_bp.route("/admin/library/scan", methods=["GET", "POST"])
@user_login_required
@admin_required
def scan_reading():
    if request.method == "POST":
        action = request.form.get("action") or "scan"
        if action == "token":
            save_hardcover_token(request.form.get("hardcover_token", ""))
            flash(_("Hardcover token saved."), category="success")
        elif action == "ratings":
            enqueue_ratings(getattr(current_user, "name", None) or "admin", missing_only=True)
            flash(_("Rating rescan started. It runs in the background and only retries books with no rating."), category="success")
        elif action == "moods":
            from .ratings.hardcover import enqueue_moods
            enqueue_moods(getattr(current_user, "name", None) or "admin")
            flash(_("Mood rescan started. It retries books with no Hardcover moods and does not guess."), category="success")
        elif action == "save_rating":
            if save_manual_rating(request.form.get("book_id"), request.form.get("rating")):
                flash(_("Rating saved."), category="success")
            else:
                flash(_("Enter a rating between 1 and 5."), category="error")
        elif action == "accolades":
            from .accolades import enqueue_scan
            enqueue_scan(getattr(current_user, "name", None) or "admin")
            flash(_("Accolade scan started. It runs in the background."), category="success")
        elif action == "accolades_unmatched":
            from .accolades import enqueue_scan
            from .series_info import enqueue_scan as enqueue_series_scan
            enqueue_scan(getattr(current_user, "name", None) or "admin", unmatched_only=True)
            enqueue_series_scan(getattr(current_user, "name", None) or "admin", ignore_miss=True)
            flash(_("Rescan started. It retries unmatched books and series and ignores the miss cache."), category="success")
        elif action == "series_info":
            from .series_info import enqueue_scan as enqueue_series_scan
            enqueue_series_scan(getattr(current_user, "name", None) or "admin")
            flash(_("Series info scan started. It runs in the background."), category="success")
        elif action == "nyt_key":
            from .store import set_setting
            key = (request.form.get("nyt_books_key") or "").strip()
            if key:
                set_setting("nyt_books_key", key)
                flash(_("NYT Books API key saved."), category="success")
            else:
                flash(_("Leave the field blank to keep the saved key."), category="success")
        elif action == "clean_accolades":
            from .accolades import purge_disallowed
            result = purge_disallowed()
            flash(_("Removed %(removed)s generic accolades. %(books)s books still have a recognition.", removed=result["removed"], books=result["books"]), category="success")
        elif action == "save_accolade":
            from .accolades import save_accolade
            try:
                saved = save_accolade(
                    request.form.get("book_id"),
                    request.form.get("type"),
                    request.form.get("label"),
                    request.form.get("year"),
                    request.form.get("source_url"),
                    request.form.get("row_id") or None,
                )
            except (TypeError, ValueError):
                saved = False
            if saved:
                flash(_("Accolade saved."), category="success")
            else:
                flash(_("An accolade needs a book id and a label."), category="error")
        elif action == "delete_accolade":
            from .accolades import delete_accolade
            delete_accolade(request.form.get("row_id"))
            flash(_("Accolade removed."), category="success")
        elif action == "save_quote":
            from .accolades import save_quote
            try:
                saved = save_quote(
                    request.form.get("book_id"),
                    request.form.get("quote"),
                    request.form.get("publication"),
                    request.form.get("author"),
                    request.form.get("url"),
                    request.form.get("row_id") or None,
                )
            except (TypeError, ValueError):
                saved = False
            if saved:
                flash(_("Quote saved."), category="success")
            else:
                flash(_("A quote needs a publication and must stay under 25 words."), category="error")
        elif action == "delete_quote":
            from .accolades import delete_quote
            delete_quote(request.form.get("row_id"))
            flash(_("Quote removed."), category="success")
        else:
            done, total = scan_all()
            flash(_("Scanned %(done)s of %(total)s books.", done=done, total=total), category="success")
        nxt = (request.form.get("next") or "").strip()
        if nxt.startswith("/") and not nxt.startswith("//"):
            return redirect(nxt)
        return redirect(url_for("library_ui.scan_reading"))
    from .accolades import recent_accolades, recent_quotes
    from .store import get_setting

    return render_title_template(
        "library_ui_scan.html",
        title=_("Reading time"),
        page="adminscan",
        accolades=recent_accolades(),
        quotes=recent_quotes(),
        hardcover_token=hardcover_token(),
        nyt_key_set=bool((get_setting("nyt_books_key", "") or "").strip()),
    )


def _back_to_book(book_id):
    return redirect(url_for("web.show_book", book_id=book_id))


@library_ui_bp.route("/library/comment/<int:book_id>", methods=["POST"])
@user_login_required
def add_book_comment(book_id):
    row = add_comment(book_id, current_user.id, request.form.get("body", ""), request.form.get("stars", ""))
    if row is None:
        flash(_("Write a comment first."), category="error")
    else:
        flash(_("Comment saved."), category="success")
    return _back_to_book(book_id)


@library_ui_bp.route("/library/comment/<int:comment_id>/edit", methods=["POST"])
@user_login_required
def edit_book_comment(comment_id):
    row = update_comment(
        comment_id,
        current_user.id,
        request.form.get("body", ""),
        request.form.get("stars", ""),
        is_admin=current_user.role_admin(),
    )
    if row is None:
        flash(_("That comment could not be changed."), category="error")
        return redirect(url_for("web.index"))
    flash(_("Comment saved."), category="success")
    return _back_to_book(row.book_id)


@library_ui_bp.route("/library/comment/<int:comment_id>/delete", methods=["POST"])
@user_login_required
def delete_book_comment(comment_id):
    from .models import LibraryComment
    from .. import ub
    existing = ub.session.query(LibraryComment).filter(LibraryComment.id == comment_id).first()
    book_id = existing.book_id if existing else None
    ok = delete_comment(comment_id, current_user.id, is_admin=current_user.role_admin())
    flash(_("Comment removed.") if ok else _("That comment could not be changed."), category="success" if ok else "error")
    if book_id:
        return _back_to_book(book_id)
    return redirect(url_for("web.index"))


@library_ui_bp.route("/library/comment/<int:comment_id>/hide", methods=["POST"])
@user_login_required
@admin_required
def hide_book_comment(comment_id):
    from .models import LibraryComment
    from .. import ub
    existing = ub.session.query(LibraryComment).filter(LibraryComment.id == comment_id).first()
    hidden = request.form.get("hidden") == "1"
    set_hidden(comment_id, hidden)
    flash(_("Comment hidden.") if hidden else _("Comment visible again."), category="success")
    if request.form.get("next") == "admin":
        return redirect(url_for("library_ui.moderate_comments"))
    if existing:
        return _back_to_book(existing.book_id)
    return redirect(url_for("library_ui.moderate_comments"))


@library_ui_bp.route("/admin/library/comments")
@user_login_required
@admin_required
def moderate_comments():
    return render_title_template(
        "library_ui_comments.html",
        title=_("Comments"),
        page="admincomments",
        comments=recent_comments(),
        comment_author=user_name,
    )


@library_ui_bp.route("/request")
@user_login_required
def request_book():
    from .requests import user_rows

    return render_title_template(
        "library_request.html",
        title=_("Request a Book"),
        page="request",
        requests=user_rows(current_user.id),
    )


@library_ui_bp.route("/request", methods=["POST"])
@user_login_required
def request_book_save():
    from .requests import create_request

    payload = create_request(
        current_user.id,
        request.form.get("title"),
        request.form.get("author"),
        confirmed=request.form.get("confirm") == "1",
    )
    status = 200 if payload.get("ok") else 400
    if payload.get("code") == "duplicate":
        status = 409
    elif payload.get("code") == "limit":
        status = 429
    return jsonify(payload), status


@library_ui_bp.route("/request/<int:request_id>/delete", methods=["POST"])
@user_login_required
def request_book_delete(request_id):
    from .requests import delete_own

    if not delete_own(current_user.id, request_id):
        abort(403)
    return jsonify({"ok": True})


@library_ui_bp.route("/admin/requests")
@user_login_required
@admin_required
def admin_requests():
    from .requests import admin_rows

    return render_title_template(
        "library_requests_admin.html",
        title=_("Book Requests"),
        page="adminrequests",
        request_rows=admin_rows(),
    )


@library_ui_bp.route("/admin/requests/update", methods=["POST"])
@user_login_required
@admin_required
def admin_requests_update():
    from .requests import apply_admin

    action = (request.form.get("action") or "").strip()
    changed = apply_admin(action, request.form.getlist("ids"))
    if action not in ("fulfilled", "declined", "delete"):
        abort(400)
    return jsonify({"ok": True, "ids": changed, "action": action})
