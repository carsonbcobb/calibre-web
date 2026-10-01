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
from .login_collage import book_for_slot, cover_response
from .reading import scan_all
from .ratings.service import fetch_missing, hardcover_token, save_hardcover_token
from .store import get_setting, set_setting

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
        else:
            flash(_("Unknown image."), category="error")
        return redirect(url_for("library_ui.branding"))

    return render_title_template(
        "library_ui_branding.html",
        title=_("Logo and Favicon"),
        page="adminbrand",
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
            count = fetch_missing()
            flash(_("Fetched ratings for %(count)s books.", count=count), category="success")
        else:
            done, total = scan_all()
            flash(_("Scanned %(done)s of %(total)s books.", done=done, total=total), category="success")
        return redirect(url_for("library_ui.scan_reading"))
    return render_title_template(
        "library_ui_scan.html",
        title=_("Reading time"),
        page="adminscan",
        hardcover_token=hardcover_token(),
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
