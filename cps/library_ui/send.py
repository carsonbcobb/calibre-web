# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Preferred format for the existing Send to eReader mail path."""


def send_choice(book):
    """Return the first mail format dict, or None when this reader cannot send."""
    if book is None:
        return None
    from ..cw_login import current_user
    if not getattr(current_user, "is_authenticated", False):
        return None
    if getattr(current_user, "is_anonymous", False):
        return None
    if not current_user.role_download():
        return None
    from ..helper import check_send_to_ereader
    try:
        options = check_send_to_ereader(book) or []
    except Exception:
        return None
    return options[0] if options else None
