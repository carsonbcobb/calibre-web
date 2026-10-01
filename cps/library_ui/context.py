# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from .css_sanitize import sanitize_css
from .store import get_setting


def library_context():
    try:
        custom_css = sanitize_css(get_setting("custom_css", ""))
    except Exception:
        custom_css = ""
    return {
        "library_custom_css": custom_css,
    }
