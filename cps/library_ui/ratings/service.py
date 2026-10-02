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
from .google import GoogleBooksProvider
from .goodreads import GoodreadsProvider
from .hardcover import HardcoverProvider
from .openlibrary import OpenLibraryProvider

PROVIDERS = (
    HardcoverProvider(),
    OpenLibraryProvider(),
    GoogleBooksProvider(),
    GoodreadsProvider(),
)
_SUCCESS_DAYS = 30
_ERROR_DAYS = 7


def active_providers():
    return [provider for provider in PROVIDERS if provider.enabled]


def ensure_ratings(book, force_errors=False):
    """Fetch any provider whose cache is missing or old. Failures stay off the page."""
    if book is None:
        return []
    shown = []
    for provider in active_providers():
        if not provider.available():
            continue
        row = _row(book.id, provider.slug)
        if row and row.provider == "manual":
            continue
        if row and row.rating is not None and not row.error and not _stale(row):
            shown.append(row)
            continue
        if row and not _stale(row) and not (force_errors and row.error):
            continue
        shown_row = _fetch(book, provider, row)
        if shown_row is not None and shown_row.rating is not None and not shown_row.error:
            shown.append(shown_row)
    _remember(book.id, shown)
    return shown


def rating_info(book_id):
    """Best rating on a 5 star scale, or None when nothing is stored.

    A manual override wins. Otherwise the provider with the most ratings wins.
    """
    rows = [row for row in _remembered(book_id) if row.rating is not None and not row.error]
    if not rows:
        return None
    manual = [row for row in rows if row.provider == "manual"]
    chosen = manual[0] if manual else max(rows, key=lambda row: ((row.rating_count or 0), _five(row.rating) or 0))
    value = _five(chosen.rating)
    if not value:
        return None
    return {
        "value": value,
        "count": chosen.rating_count,
        "source": _source_name(chosen.provider),
        "label": "%.1f" % value,
    }


def best_rating_map():
    """book id to the rating the shelves should use. Reads only the cache."""
    from ... import ub

    try:
        rows = ub.session.query(LibraryRating).filter(LibraryRating.rating.isnot(None)).all()
    except Exception:
        ub.session.rollback()
        return {}
    grouped = {}
    for row in rows:
        if row.error:
            continue
        grouped.setdefault(row.book_id, []).append(row)
    found = {}
    for book_id, items in grouped.items():
        manual = [row for row in items if row.provider == "manual"]
        chosen = manual[0] if manual else max(items, key=lambda row: ((row.rating_count or 0), _five(row.rating) or 0))
        value = _five(chosen.rating)
        if not value:
            continue
        found[book_id] = {
            "value": value,
            "count": chosen.rating_count,
            "source": _source_name(chosen.provider),
        }
    return found


def rating_bits(book_id):
    info = rating_info(book_id)
    return info["label"] if info else ""


def fetch_missing(limit=12):
    """Kept for older callers. Prefer the background rescan."""
    return _scan_ratings(None, None, missing_only=True, limit=limit)


def enqueue_ratings(user_name, missing_only=True):
    from flask import current_app
    from ...services.worker import WorkerThread

    application = current_app._get_current_object()
    WorkerThread.add(user_name or "admin", ratings_task(application, missing_only), hidden=False)


def ratings_task(application, missing_only):
    from ...services.worker import STAT_CANCELLED, STAT_ENDED, CalibreTask

    class _Task(CalibreTask):
        def __init__(self, app_obj, only_missing):
            super(_Task, self).__init__("Rescan missing ratings" if only_missing else "Scan ratings")
            self.application = app_obj
            self.missing_only = only_missing

        def run(self, worker_thread):
            with self.application.app_context():
                total, matched, unmatched = _scan_ratings(self, self.application, self.missing_only)
            self.progress = 1
            self.message = "Rated %s of %s books. %s still unmatched." % (matched, total, unmatched)
            if self.stat not in (STAT_CANCELLED, STAT_ENDED):
                self._handleSuccess()

        @property
        def name(self):
            return "Rescan missing ratings" if self.missing_only else "Scan ratings"

        @property
        def is_cancellable(self):
            return True

    return _Task(application, missing_only)


def _scan_ratings(task, application, missing_only, limit=None):
    from ... import db
    from ...services.worker import STAT_CANCELLED, STAT_ENDED

    if application is None:
        from flask import current_app
        application = current_app._get_current_object()
    worker_db = db.CalibreDB(application)
    books = worker_db.session.query(db.Books).all()
    if limit:
        books = books[: int(limit)]
    known = set(best_rating_map())
    total = len(books)
    matched = 0
    unmatched = 0
    for index, book in enumerate(books):
        if task is not None and task.stat in (STAT_CANCELLED, STAT_ENDED):
            break
        try:
            if missing_only and book.id in known:
                matched += 1
                _ensure_hardcover(book)
            else:
                rows = ensure_ratings(book, force_errors=bool(missing_only))
                if any(row.rating is not None and not row.error for row in rows) or book.id in known:
                    matched += 1
                    known.add(book.id)
                else:
                    unmatched += 1
        except Exception as error:
            unmatched += 1
            log.error("Rating scan book %s failed: %s", getattr(book, "id", None), error)
        if task is not None and total:
            task.progress = min(1, float(index + 1) / float(total))
    return total, matched, unmatched


def _ensure_hardcover(book):
    """Fill a missing Hardcover profile without touching providers that already matched."""
    provider = next((item for item in active_providers() if item.slug == "hardcover"), None)
    if provider is None or not provider.available():
        return
    if _hardcover_profile(book.id):
        return
    _fetch(book, provider, _row(book.id, provider.slug))


def _hardcover_profile(book_id):
    from ... import ub
    from ..models import HardcoverBook

    try:
        row = (ub.session.query(HardcoverBook)
               .filter(HardcoverBook.book_id == int(book_id))
               .one_or_none())
    except Exception:
        ub.session.rollback()
        return False
    return row is not None and not row.error


def save_manual_rating(book_id, value):
    from ... import ub

    number = _five(value)
    if not number:
        return False
    row = _row(book_id, "manual")
    if row is None:
        row = LibraryRating(book_id=int(book_id), provider="manual")
        ub.session.add(row)
    row.rating = number
    row.rating_count = row.rating_count or 0
    row.error = ""
    row.source_url = ""
    row.fetched_at = datetime.now(timezone.utc)
    ub.session_commit("Manual rating")
    return True


def rating_report():
    """Every book, and why each provider matched or missed. Cache only."""
    from ... import calibre_db, db, ub

    books = calibre_db.session.query(db.Books).order_by(db.Books.sort).all()
    try:
        rows = ub.session.query(LibraryRating).all()
    except Exception:
        ub.session.rollback()
        rows = []
    grouped = {}
    for row in rows:
        grouped.setdefault(row.book_id, {})[row.provider] = row
    slugs = [provider.slug for provider in PROVIDERS if provider.slug != "goodreads"]
    report = []
    matched_books = 0
    for book in books:
        found = grouped.get(book.id, {})
        providers = []
        hit = False
        for slug in slugs:
            row = found.get(slug)
            if row is None:
                providers.append({"name": _source_name(slug), "status": "not scanned", "detail": ""})
                continue
            if row.rating is not None and not row.error:
                hit = True
                count = row.rating_count or 0
                providers.append({
                    "name": _source_name(slug),
                    "status": "matched",
                    "detail": "%.1f from %s ratings" % (_five(row.rating) or 0, count),
                })
            else:
                providers.append({
                    "name": _source_name(slug),
                    "status": "missed",
                    "detail": row.error or "no results",
                })
        if found.get("manual") and found["manual"].rating is not None:
            hit = True
            providers.insert(0, {
                "name": "Manual",
                "status": "matched",
                "detail": "%.1f" % (_five(found["manual"].rating) or 0),
            })
        if hit:
            matched_books += 1
        report.append({"title": book.title or "", "id": book.id, "matched": hit, "providers": providers})
    total = len(books)
    return {
        "total": total,
        "matched": matched_books,
        "unmatched": total - matched_books,
        "books": report,
    }


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
        if result is None or result.value is None:
            rating = None
            error = (result.reason if result else "") or "no results"
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


def _five(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 5:
        number = number / 2.0
    number = round(number, 1)
    if number <= 0 or number > 5:
        return None
    return number


def _source_name(slug):
    if slug == "manual":
        return "Manual"
    for provider in PROVIDERS:
        if provider.slug == slug:
            return provider.name
    return slug
