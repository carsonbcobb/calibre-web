# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from datetime import datetime, timedelta, timezone

from flask import g

from ..logger_helper import log
from ..models import LibraryRating
from .goodreads import GoodreadsProvider
from .hardcover import HardcoverProvider
from .openlibrary import OpenLibraryProvider

PROVIDERS = (
    OpenLibraryProvider(),
    HardcoverProvider(),
    GoodreadsProvider(),
)
_SUCCESS_DAYS = 14
_ERROR_DAYS = 2


def active_providers():
    return [provider for provider in PROVIDERS if provider.enabled]


def ensure_ratings(book):
    """Fetch any provider whose cache is missing or old. Failures stay off the page."""
    if book is None:
        return []
    shown = []
    for provider in active_providers():
        if not provider.available():
            continue
        row = _row(book.id, provider.slug)
        if row and not _stale(row):
            if row.rating is not None and not row.error:
                shown.append(row)
            continue
        shown_row = _fetch(book, provider, row)
        if shown_row is not None and shown_row.rating is not None and not shown_row.error:
            shown.append(shown_row)
    _remember(book.id, shown)
    return shown


def rating_bits(book_id):
    rows = _remembered(book_id)
    parts = []
    for row in rows:
        if row.rating is None:
            continue
        text = "%.1f %s" % (float(row.rating), _source_name(row.provider))
        parts.append(text)
    return ", ".join(parts)


def fetch_missing(limit=12):
    from ... import calibre_db, db

    books = (calibre_db.session.query(db.Books)
             .order_by(db.Books.timestamp.desc())
             .limit(limit)
             .all())
    done = 0
    for book in books:
        rows = ensure_ratings(book)
        if any(row.rating is not None and not row.error for row in rows):
            done += 1
    return done


def save_hardcover_token(token):
    from ..store import set_setting
    set_setting("hardcover_token", (token or "").strip())


def hardcover_token():
    from ..store import get_setting
    return get_setting("hardcover_token", "") or ""


def _fetch(book, provider, row):
    from ... import ub

    try:
        result = provider.lookup(book)
        error = ""
        rating = result.value if result else None
        count = result.count if result else None
        url = result.url if result else ""
        if result is None:
            error = "no result"
    except Exception as error_obj:
        log.debug("Rating provider %s failed: %s", provider.slug, error_obj)
        rating = None
        count = None
        url = ""
        error = str(error_obj)[:180]
    if row is None:
        row = LibraryRating(book_id=book.id, provider=provider.slug)
        ub.session.add(row)
    row.rating = rating
    row.rating_count = count
    row.source_url = url or ""
    row.error = "" if rating is not None else error
    row.fetched_at = datetime.now(timezone.utc)
    ub.session_commit()
    return row


def _row(book_id, slug):
    from ... import ub
    return (ub.session.query(LibraryRating)
            .filter(LibraryRating.book_id == int(book_id))
            .filter(LibraryRating.provider == slug)
            .one_or_none())


def _stale(row):
    if not row.fetched_at:
        return True
    fetched = row.fetched_at
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - fetched
    limit = timedelta(days=_ERROR_DAYS if row.error else _SUCCESS_DAYS)
    return age > limit


def _remember(book_id, rows):
    try:
        mapping = getattr(g, "library_rating_map", None)
        if mapping is None:
            mapping = {}
            g.library_rating_map = mapping
        mapping[int(book_id)] = rows
    except Exception:
        pass


def _remembered(book_id):
    try:
        mapping = getattr(g, "library_rating_map", None)
        if mapping is None or int(book_id) not in mapping:
            from ... import ub
            rows = (ub.session.query(LibraryRating)
                    .filter(LibraryRating.rating.isnot(None))
                    .all())
            grouped = {}
            for row in rows:
                if row.error:
                    continue
                grouped.setdefault(row.book_id, []).append(row)
            if mapping:
                mapping.update(grouped)
            else:
                g.library_rating_map = grouped
                mapping = grouped
        return mapping.get(int(book_id), [])
    except Exception:
        return []


def _source_name(slug):
    for provider in PROVIDERS:
        if provider.slug == slug:
            return provider.name
    return slug
