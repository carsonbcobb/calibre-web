# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from flask_babel import gettext as _
from sqlalchemy import func, or_

from .logger_helper import log
from .heroes import hero_slides


def render_home():
    from ..render_template import render_title_template

    return render_title_template(
        "library_home.html",
        title=_("Home"),
        page="libraryhome",
        recent_books=recent_books(),
        continue_books=continue_series_books(),
        genre_rows=genre_rows(),
        collections=collection_cards(),
        heroes=hero_slides(),
        discover_picks=discover_books(),
    )


def discover_books(limit=3):
    try:
        from .. import calibre_db, db
        return (calibre_db.session.query(db.Books)
                .filter(db.Books.has_cover == 1)
                .filter(calibre_db.common_filters())
                .order_by(func.random())
                .limit(limit)
                .all())
    except Exception as error:
        log.debug("Discover picks unavailable: %s", error)
        return []


def recent_books(limit=24):
    try:
        from .. import calibre_db, db
        return (calibre_db.session.query(db.Books)
                .filter(calibre_db.common_filters())
                .order_by(db.Books.timestamp.desc())
                .limit(limit)
                .all())
    except Exception as error:
        log.debug("Recent books unavailable: %s", error)
        return []


def genre_rows(row_count=6, per_row=18):
    try:
        from .. import calibre_db, db
        counts = (calibre_db.session.query(db.Tags, func.count(db.Books.id))
                  .join(db.books_tags_link, db.Tags.id == db.books_tags_link.c.tag)
                  .join(db.Books, db.Books.id == db.books_tags_link.c.book)
                  .filter(calibre_db.common_filters())
                  .group_by(db.Tags.id)
                  .order_by(func.count(db.Books.id).desc(), db.Tags.name.asc())
                  .limit(row_count)
                  .all())
        rows = []
        for tag, count in counts:
            books = (calibre_db.session.query(db.Books)
                     .join(db.books_tags_link, db.Books.id == db.books_tags_link.c.book)
                     .filter(db.books_tags_link.c.tag == tag.id)
                     .filter(calibre_db.common_filters())
                     .order_by(db.Books.timestamp.desc())
                     .limit(per_row)
                     .all())
            if books:
                rows.append({"tag": tag, "count": int(count), "books": books})
        return rows
    except Exception as error:
        log.debug("Genre rows unavailable: %s", error)
        return []


def collection_cards():
    try:
        from ..cw_login import current_user

        from .. import calibre_db, db, ub
        user_id = int(current_user.id) if current_user.is_authenticated else -1
        shelves = (ub.session.query(ub.Shelf)
                   .filter(or_(ub.Shelf.is_public == 1, ub.Shelf.user_id == user_id))
                   .order_by(ub.Shelf.name.asc())
                   .all())
        cards = []
        for shelf in shelves:
            link = shelf.books.order_by(ub.BookShelf.order.asc()).first()
            book = None
            if link is not None:
                book = (calibre_db.session.query(db.Books)
                        .filter(db.Books.id == link.book_id)
                        .first())
            count = shelf.books.count()
            if count:
                cards.append({"shelf": shelf, "book": book, "count": count})
        return cards
    except Exception as error:
        log.debug("Collections unavailable: %s", error)
        return []


def continue_series_books(limit=16):
    try:
        from ..cw_login import current_user

        from .. import calibre_db, db, ub
        if not current_user.is_authenticated or getattr(current_user, "is_anonymous", False):
            return []
        reads = (ub.session.query(ub.ReadBook)
                 .filter(ub.ReadBook.user_id == int(current_user.id))
                 .filter(ub.ReadBook.read_status.in_([
                     ub.ReadBook.STATUS_IN_PROGRESS,
                     ub.ReadBook.STATUS_FINISHED,
                 ]))
                 .order_by(ub.ReadBook.last_modified.desc())
                 .all())
        if not reads:
            return []
        books = (calibre_db.session.query(db.Books)
                 .filter(db.Books.id.in_([row.book_id for row in reads]))
                 .all())
        by_id = {book.id: book for book in books}
        chosen = []
        seen = set()
        for row in reads:
            book = by_id.get(row.book_id)
            if book is None or not book.series:
                continue
            series_id = book.series[0].id
            if series_id in seen:
                continue
            seen.add(series_id)
            if row.read_status == ub.ReadBook.STATUS_IN_PROGRESS:
                chosen.append(book)
            else:
                nxt = _next_in_series(series_id, book)
                if nxt is not None:
                    chosen.append(nxt)
            if len(chosen) >= limit:
                break
        return chosen
    except Exception as error:
        log.debug("Continue series unavailable: %s", error)
        return []


def _series_index(book):
    try:
        return float(book.series_index or 0)
    except (TypeError, ValueError):
        return 0.0


def _next_in_series(series_id, finished_book):
    from .. import calibre_db, db

    current = _series_index(finished_book)
    candidates = (calibre_db.session.query(db.Books)
                  .join(db.books_series_link, db.Books.id == db.books_series_link.c.book)
                  .filter(db.books_series_link.c.series == series_id)
                  .filter(calibre_db.common_filters())
                  .all())
    later = [book for book in candidates if _series_index(book) > current + 0.001]
    later.sort(key=_series_index)
    return later[0] if later else None
