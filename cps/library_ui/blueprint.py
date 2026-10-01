# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from flask import Blueprint, abort, flash, make_response, redirect, request, url_for
from flask_babel import gettext as _

from ..admin import admin_required
from ..render_template import render_title_template
from ..usermanagement import user_login_required
from .branding import delete_asset, get_asset, save_upload
from .css_sanitize import sanitize_css
from .login_collage import book_for_slot, cover_response
from .store import get_setting, set_setting

library_ui_bp = Blueprint("library_ui", __name__)


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
