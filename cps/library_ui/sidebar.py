# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import time

from flask import url_for
from sqlalchemy import func

from .logger_helper import log

_CACHE = {}
_TTL = 60


def sidebar_lists():
    """Cached browse lists and counts for the sidebar. Read only."""
    from ..cw_login import current_user

    key = (
        int(getattr(current_user, "id", 0) or 0),
        str(current_user.filter_language()),
    )
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL:
        return cached[1]
    payload = _load()
    _CACHE[key] = (now, payload)
    if len(_CACHE) > 24:
        oldest = sorted(_CACHE, key=lambda item: _CACHE[item][0])[:-12]
        for item in oldest:
            _CACHE.pop(item, None)
    return payload


def _load():
    payload = {
        "books": None,
        "unread": None,
        "read": None,
        "favorites": None,
        "archived": None,
        "hot": None,
        "downloaded": None,
        "publishers": None,
        "languages": None,
        "ratings": None,
        "formats": None,
        "genres": [],
        "series": [],
        "authors": [],
        "genre_count": None,
        "series_count": None,
    }
    try:
        from .. import calibre_db, db, ub
        from ..cw_login import current_user

        session = calibre_db.session
        filters = calibre_db.common_filters()
        payload["books"] = _count(session.query(func.count(db.Books.id)).filter(filters))
        payload["genres"] = _rows(
            session.query(db.Tags.id, db.Tags.name, func.count(db.Books.id))
            .join(db.books_tags_link, db.Tags.id == db.books_tags_link.c.tag)
            .join(db.Books, db.Books.id == db.books_tags_link.c.book)
            .filter(filters)
            .group_by(db.Tags.id)
            .order_by(func.count(db.Books.id).desc(), db.Tags.name.asc())
            .limit(24),
            "category",
            hide_tags=True,
        )
        payload["series"] = _rows(
            session.query(db.Series.id, db.Series.name, func.count(db.Books.id))
            .join(db.books_series_link, db.Series.id == db.books_series_link.c.series)
            .join(db.Books, db.Books.id == db.books_series_link.c.book)
            .filter(filters)
            .group_by(db.Series.id)
            .order_by(func.max(db.Books.last_modified).desc(), db.Series.name.asc())
            .limit(8),
            "series",
        )
        payload["genre_count"] = _genre_total(session, db, filters)
        payload["series_count"] = _series_total(session, db, filters)
        payload["authors"] = _rows(
            session.query(db.Authors.id, db.Authors.name, func.count(db.Books.id))
            .join(db.books_authors_link, db.Authors.id == db.books_authors_link.c.author)
            .join(db.Books, db.Books.id == db.books_authors_link.c.book)
            .filter(filters)
            .group_by(db.Authors.id)
            .order_by(func.count(db.Books.id).desc(), db.Authors.sort.asc())
            .limit(8),
            "author",
            clean=True,
        )
        payload["favorites"] = _count(
            session.query(func.count(func.distinct(db.Books.id)))
            .join(db.books_ratings_link, db.Books.id == db.books_ratings_link.c.book)
            .join(db.Ratings, db.Ratings.id == db.books_ratings_link.c.rating)
            .filter(db.Ratings.rating > 0)
            .filter(filters)
        )
        payload["publishers"] = _count(
            session.query(func.count(func.distinct(db.Publishers.id)))
            .join(db.books_publishers_link, db.Publishers.id == db.books_publishers_link.c.publisher)
            .join(db.Books, db.Books.id == db.books_publishers_link.c.book)
            .filter(filters)
        )
        payload["languages"] = _count(
            session.query(func.count(func.distinct(db.Languages.id)))
            .join(db.books_languages_link, db.Languages.id == db.books_languages_link.c.lang_code)
            .join(db.Books, db.Books.id == db.books_languages_link.c.book)
            .filter(filters)
        )
        payload["formats"] = _count(
            session.query(func.count(func.distinct(db.Data.format)))
            .join(db.Books, db.Books.id == db.Data.book)
            .filter(filters)
        )
        payload["ratings"] = _count(
            session.query(func.count(func.distinct(db.Ratings.id)))
            .join(db.books_ratings_link, db.Ratings.id == db.books_ratings_link.c.rating)
            .join(db.Books, db.Books.id == db.books_ratings_link.c.book)
            .filter(db.Ratings.rating > 0)
            .filter(filters)
        )
        user_id = int(getattr(current_user, "id", 0) or 0)
        finished = [
            row[0] for row in ub.session.query(ub.ReadBook.book_id).filter(
                ub.ReadBook.user_id == user_id,
                ub.ReadBook.read_status == ub.ReadBook.STATUS_FINISHED,
            ).all()
        ]
        read_count = _count(session.query(func.count(db.Books.id)).filter(db.Books.id.in_(finished)).filter(filters)) if finished else 0
        payload["read"] = read_count
        if payload["books"] is not None and read_count is not None:
            payload["unread"] = max(payload["books"] - read_count, 0)
        archived = [
            row[0] for row in ub.session.query(ub.ArchivedBook.book_id).filter(
                ub.ArchivedBook.user_id == user_id,
                ub.ArchivedBook.is_archived == True,
            ).all()
        ]
        payload["archived"] = _count(session.query(func.count(db.Books.id)).filter(db.Books.id.in_(archived))) if archived else 0
        downloaded = [
            row[0] for row in ub.session.query(ub.Downloads.book_id).filter(ub.Downloads.user_id == user_id).distinct().all()
        ]
        payload["downloaded"] = _count(session.query(func.count(db.Books.id)).filter(db.Books.id.in_(downloaded)).filter(filters)) if downloaded else 0
        hot = [row[0] for row in ub.session.query(ub.Downloads.book_id).distinct().all()]
        payload["hot"] = _count(session.query(func.count(db.Books.id)).filter(db.Books.id.in_(hot)).filter(filters)) if hot else 0
    except Exception as error:
        log.debug("Sidebar lists unavailable: %s", error)
    return payload


def _genre_total(session, db, filters):
    from .home_rows import _canonical

    try:
        rows = (session.query(db.Tags.name, func.count(db.Books.id))
                .join(db.books_tags_link, db.Tags.id == db.books_tags_link.c.tag)
                .join(db.Books, db.Books.id == db.books_tags_link.c.book)
                .filter(filters)
                .group_by(db.Tags.id)
                .all())
    except Exception as error:
        log.debug("Genre count skipped: %s", error)
        return None
    total = 0
    for name, count in rows:
        if _canonical(name) and int(count or 0) >= 3:
            total += 1
    return total


def _series_total(session, db, filters):
    try:
        rows = (session.query(func.count(db.Books.id))
                .select_from(db.Series)
                .join(db.books_series_link, db.Series.id == db.books_series_link.c.series)
                .join(db.Books, db.Books.id == db.books_series_link.c.book)
                .filter(filters)
                .group_by(db.Series.id)
                .all())
    except Exception as error:
        log.debug("Series count skipped: %s", error)
        return None
    return len(rows)


def _count(query):
    try:
        value = query.scalar()
        return int(value or 0)
    except Exception as error:
        log.debug("Sidebar count skipped: %s", error)
        return None


def _rows(query, kind, clean=False, hide_tags=False):
    from .shelf_config import tag_hidden
    found = []
    try:
        for item_id, name, count in query.all():
            label = (name or "").replace("|", ", ") if clean else (name or "")
            if hide_tags and tag_hidden(label):
                continue
            if len(found) >= 8:
                break
            found.append({
                "name": label,
                "count": int(count or 0),
                "url": url_for("web.books_list", data=kind, sort_param="stored", book_id=int(item_id)),
            })
    except Exception as error:
        log.debug("Sidebar list skipped: %s", error)
    return found
