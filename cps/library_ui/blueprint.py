# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from flask import Blueprint, flash, redirect, request, url_for
from flask_babel import gettext as _

from ..admin import admin_required
from ..render_template import render_title_template
from ..usermanagement import user_login_required
from .css_sanitize import sanitize_css
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
