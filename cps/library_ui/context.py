# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from .branding import asset_urls
from .css_sanitize import sanitize_css
from .genres import bar_context
from .login_collage import covers_enabled
from .series_books import series_number
from .store import get_setting


def library_context():
    try:
        custom_css = sanitize_css(get_setting("custom_css", ""))
    except Exception:
        custom_css = ""
    try:
        urls = asset_urls()
    except Exception:
        urls = {"logo": "", "favicon": ""}
    return {
        "library_custom_css": custom_css,
        "library_logo_url": urls.get("logo") or "",
        "library_favicon_url": urls.get("favicon") or "",
        "library_login_collage": _login_collage_on(),
        "library_series_number": series_number,
        **bar_context(),
    }


def _login_collage_on():
    try:
        from flask import request
        if request.endpoint not in ("web.login", "web.login_post"):
            return False
        return covers_enabled()
    except Exception:
        return False
