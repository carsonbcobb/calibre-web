# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from .logger_helper import log


def series_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number == int(number):
        return str(int(number))
    return ("%.2f" % number).rstrip("0").rstrip(".")


def books_in_series(book):
    if book is None or not getattr(book, "series", None):
        return []
    try:
        from .. import calibre_db, db
        series_id = book.series[0].id
        rows = (calibre_db.session.query(db.Books)
                .join(db.books_series_link, db.Books.id == db.books_series_link.c.book)
                .filter(db.books_series_link.c.series == series_id)
                .filter(calibre_db.common_filters(allow_show_archived=True))
                .all())
        rows.sort(key=lambda item: _sort_index(item))
        return rows
    except Exception as error:
        log.debug("Series list unavailable: %s", error)
        return []


def _sort_index(book):
    try:
        return float(book.series_index or 0)
    except (TypeError, ValueError):
        return 0.0
