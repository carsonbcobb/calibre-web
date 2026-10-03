# -*- coding: utf-8 -*-

"""Hardcover GraphQL client. The token stays on the server."""

import json
import threading
import time

import requests

from ..store import get_setting
from .base import Rating, RatingProvider
from .match import confident, identifiers, series_query

_URL = "https://api.hardcover.app/v1/graphql"
_UA = "DeadMediaSociety/1.0 (local library catalog; hardcover)"
_LOCK = threading.Lock()
_NEXT = 0.0

_BOOK = """
id
title
slug
rating
ratings_count
reviews_count
users_count
users_read_count
pages
release_date
description
lists_count
editions_count
cached_tags
cached_image
cached_featured_series
list_books(limit: 8) { list { name slug } }
book_series(limit: 2) { position series { name } }
"""

_BY_ISBN = """
query ($isbn: String!) {
  editions(where: {isbn_13: {_eq: $isbn}}, limit: 1) {
    book { id }
  }
}
"""

_BY_ISBN10 = """
query ($isbn: String!) {
  editions(where: {isbn_10: {_eq: $isbn}}, limit: 1) {
    book { id }
  }
}
"""

_BY_ID = """
query ($id: Int!) {
  books(where: {id: {_eq: $id}}, limit: 1) {
    %s
  }
}
""" % _BOOK

_SEARCH = """
query ($q: String!) {
  search(query: $q, query_type: "Book", per_page: 5, page: 1) {
    results
  }
}
"""


class HardcoverProvider(RatingProvider):
    name = "Hardcover"
    slug = "hardcover"

    def available(self):
        return bool(_token())

    def lookup(self, book):
        if not _token():
            return Rating(reason="no token")
        ids = identifiers(book)
        for value in ids["hardcover"]:
            if str(value).isdigit():
                found = _book(int(value))
                saved = _keep(book.id, found)
                if saved is not None:
                    return saved
        for isbn in ids["isbn"]:
            book_id = _isbn_id(isbn)
            if isinstance(book_id, Rating):
                return book_id
            if book_id:
                found = _book(book_id)
                saved = _keep(book.id, found)
                if saved is not None:
                    return saved
        title = (book.title or "").strip()
        author = _author(book)
        found = _search(title, author)
        saved = _keep(book.id, found)
        if saved is not None:
            return saved
        if isinstance(found, Rating) and found.reason not in ("title mismatch", "no results"):
            return found
        series = ""
        index = None
        if getattr(book, "series", None):
            series = book.series[0].name or ""
            index = getattr(book, "series_index", None)
        query = series_query(series, index)
        if query:
            found = _search(query, author, wanted_title=title or query)
            saved = _keep(book.id, found)
            if saved is not None:
                return saved
            if isinstance(found, Rating) and found.reason not in ("title mismatch", "no results"):
                return found
        if not ids["isbn"] and not ids["hardcover"] and not title:
            return Rating(reason="no identifier")
        return Rating(reason="title mismatch" if title else "no results")


def _keep(book_id, found):
    if not isinstance(found, dict):
        return None
    _save_profile(book_id, found)
    return _rating(found)


def profile_for(book_id):
    from ... import ub
    from ..models import HardcoverBook

    try:
        row = (ub.session.query(HardcoverBook)
               .filter(HardcoverBook.book_id == int(book_id))
               .one_or_none())
    except Exception:
        ub.session.rollback()
        return None
    if row is None or row.error:
        return None
    return {
        "readers": row.users_read_count,
        "readers_label": _comma(row.users_read_count),
        "ratings_label": _comma(row.ratings_count),
        "shelved": row.users_count,
        "ratings_count": row.ratings_count,
        "reviews_count": row.reviews_count,
        "moods": _loads(row.moods),
        "genres": _loads(row.genres),
        "tags": _loads(row.tags),
        "warnings": _loads(row.warnings),
        "series_name": row.series_name or "",
        "series_position": row.series_position or "",
        "pages": row.pages,
        "release_date": row.release_date or "",
        "description": row.description or "",
        "cover_url": row.cover_url or "",
        "url": row.source_url or "",
    }


def _token():
    return (get_setting("hardcover_token", "") or "").strip()


def _isbn_id(isbn):
    query = _BY_ISBN if len(isbn) == 13 else _BY_ISBN10
    payload = _post(query, {"isbn": isbn})
    if isinstance(payload, Rating):
        return payload
    editions = ((payload.get("data") or {}).get("editions")) or []
    if not editions:
        return None
    book = editions[0].get("book") or {}
    return book.get("id")


def _book(hardcover_id):
    payload = _post(_BY_ID, {"id": int(hardcover_id)})
    if isinstance(payload, Rating):
        return payload
    books = ((payload.get("data") or {}).get("books")) or []
    return books[0] if books else None


def _search(title, author, wanted_title=None):
    if not title:
        return None
    payload = _post(_SEARCH, {"q": title if not author else "%s %s" % (title, author)})
    if isinstance(payload, Rating):
        return payload
    results = ((payload.get("data") or {}).get("search") or {}).get("results")
    hits = _hits(results)
    wanted = wanted_title or title
    close = False
    for hit in hits:
        if not confident(wanted, author, hit.get("title") or "", _hit_author(hit)):
            continue
        close = True
        hardcover_id = hit.get("id")
        if hardcover_id:
            found = _book(hardcover_id)
            if isinstance(found, dict):
                return found
        if hit.get("rating") is not None:
            return hit
    if hits and not close:
        return Rating(reason="title mismatch")
    return None


def _hits(results):
    if isinstance(results, str):
        try:
            results = json.loads(results)
        except ValueError:
            return []
    if isinstance(results, dict):
        results = results.get("hits") or results.get("results") or []
    if not isinstance(results, list):
        return []
    ready = []
    for item in results:
        if isinstance(item, dict) and "document" in item:
            ready.append(item["document"] or {})
        elif isinstance(item, dict):
            ready.append(item)
    return ready


def _hit_author(hit):
    names = hit.get("author_names") or hit.get("authors") or []
    if isinstance(names, str):
        return names
    return ", ".join(str(name) for name in names)


def _rating(book):
    if not isinstance(book, dict) or book.get("rating") is None:
        return Rating(reason="no results")
    count = book.get("ratings_count")
    slug = book.get("slug") or ""
    url = ("https://hardcover.app/books/" + slug) if slug else "https://hardcover.app"
    return Rating(round(float(book["rating"]), 2), int(count) if count else 0, url)


def _save_profile(book_id, book):
    from datetime import datetime, timezone

    from ... import ub
    from ..accolades import replace_hardcover_lists
    from ..models import HardcoverBook

    moods, genres, tags, warnings = _tags(book.get("cached_tags"))
    series_name, position = _series(book)
    cover = _cover(book.get("cached_image"))
    lists = _lists(book.get("list_books"))
    row = (ub.session.query(HardcoverBook)
           .filter(HardcoverBook.book_id == int(book_id))
           .one_or_none())
    if row is None:
        row = HardcoverBook(book_id=int(book_id))
        ub.session.add(row)
    row.hardcover_id = book.get("id")
    row.rating = book.get("rating")
    row.ratings_count = book.get("ratings_count")
    row.reviews_count = book.get("reviews_count")
    row.users_count = book.get("users_count")
    row.users_read_count = book.get("users_read_count")
    row.pages = book.get("pages")
    row.release_date = str(book.get("release_date") or "")[:32]
    row.description = book.get("description") or ""
    row.cover_url = cover
    row.moods = json.dumps(moods)
    row.genres = json.dumps(genres)
    row.tags = json.dumps(tags)
    row.warnings = json.dumps(warnings)
    row.series_name = series_name
    row.series_position = position
    row.lists_json = json.dumps(lists)
    row.editions_count = book.get("editions_count")
    slug = book.get("slug") or ""
    row.source_url = ("https://hardcover.app/books/" + slug) if slug else ""
    row.error = ""
    row.fetched_at = datetime.now(timezone.utc)
    ub.session_commit("Hardcover profile")
    replace_hardcover_lists(book_id, lists, row.source_url)


def _tags(raw):
    moods, genres, tags, warnings = [], [], [], []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if isinstance(raw, dict):
        buckets = {
            "mood": moods,
            "genre": genres,
            "tag": tags,
            "contentwarning": warnings,
            "content_warning": warnings,
        }
        for key, value in raw.items():
            folded = str(key).replace(" ", "").replace("_", "").casefold()
            target = None
            for name, bucket in buckets.items():
                if name in folded:
                    target = bucket
                    break
            if target is None:
                continue
            target.extend(_names(value))
    return _unique(moods), _unique(genres), _unique(tags), _unique(warnings)


def _names(value):
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        label = value.get("tag") or value.get("name") or ""
        return [label] if label else []
    if isinstance(value, list):
        names = []
        for item in value:
            names.extend(_names(item))
        return names
    return []


def _unique(names):
    seen = set()
    ready = []
    for name in names:
        text = str(name).strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        ready.append(text)
    return ready[:12]


def _series(book):
    featured = book.get("cached_featured_series")
    if isinstance(featured, str):
        try:
            featured = json.loads(featured)
        except ValueError:
            featured = None
    if isinstance(featured, dict):
        series = featured.get("series") or featured
        name = ""
        if isinstance(series, dict):
            name = series.get("name") or ""
        else:
            name = featured.get("name") or ""
        position = featured.get("position") or featured.get("featured_series_position") or ""
        if name:
            return str(name), _position(position)
    rows = book.get("book_series") or []
    if rows:
        row = rows[0] or {}
        series = row.get("series") or {}
        return (series.get("name") or ""), _position(row.get("position"))
    return "", ""


def _position(value):
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)[:32]
    return ("%.2f" % number).rstrip("0").rstrip(".")


def _cover(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return ""
    if isinstance(raw, dict):
        return raw.get("url") or ""
    return ""


def _lists(rows):
    ready = []
    for row in rows or []:
        item = (row or {}).get("list") or {}
        name = (item.get("name") or "").strip()
        if not name:
            continue
        slug = item.get("slug") or ""
        ready.append({
            "name": name,
            "url": ("https://hardcover.app/lists/" + slug) if slug else "",
        })
    return ready


def _comma(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    return "{:,}".format(number)


def _loads(text):
    try:
        value = json.loads(text or "[]")
    except ValueError:
        return []
    return value if isinstance(value, list) else []


def _post(query, variables):
    global _NEXT
    token = _token()
    if not token:
        return Rating(reason="no token")
    with _LOCK:
        wait = _NEXT - time.time()
        if wait > 0:
            time.sleep(wait)
        _NEXT = time.time() + 1.05
    try:
        response = requests.post(
            _URL,
            json={"query": query, "variables": variables},
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "User-Agent": _UA,
            },
            timeout=20,
        )
    except requests.RequestException:
        return Rating(reason="request error")
    if response.status_code == 429:
        time.sleep(5)
        return Rating(reason="rate limited")
    if response.status_code >= 400:
        return Rating(reason="request error")
    payload = response.json() or {}
    if payload.get("errors") and not (payload.get("data") or {}):
        return Rating(reason="request error")
    return payload


def _author(book):
    authors = getattr(book, "authors", None) or []
    if not authors:
        return ""
    return (authors[0].name or "").replace("|", " ")


def enqueue_moods(user_name):
    """Retry Hardcover for books that still have no moods. Does not invent one."""
    from flask import current_app
    from ...services.worker import WorkerThread

    application = current_app._get_current_object()
    WorkerThread.add(user_name or "admin", _mood_task(application), hidden=False)


def _mood_task(application):
    from ...services.worker import STAT_CANCELLED, STAT_ENDED, CalibreTask

    class _Task(CalibreTask):
        def __init__(self, app_obj):
            super(_Task, self).__init__("Fill moods")
            self.application = app_obj

        def run(self, worker_thread):
            with self.application.app_context():
                total, filled = _fill_moods(self)
            self.progress = 1
            self.message = "Moods filled for %s of %s books. The rest are still missing." % (filled, total)
            if self.stat not in (STAT_CANCELLED, STAT_ENDED):
                self._handleSuccess()

        @property
        def name(self):
            return "Fill moods"

        @property
        def is_cancellable(self):
            return True

    return _Task(application)


def _fill_moods(task):
    import json

    from ... import calibre_db, db, ub
    from ..evidence import clear_evidence_cache
    from ..models import HardcoverBook

    provider = HardcoverProvider()
    if not provider.available():
        return 0, 0
    have = {}
    for row in ub.session.query(HardcoverBook).all():
        have[int(row.book_id)] = row
    books = calibre_db.session.query(db.Books).filter(calibre_db.common_filters()).all()
    missing = []
    for book in books:
        row = have.get(int(book.id))
        moods = []
        if row is not None and not row.error:
            try:
                moods = json.loads(row.moods or "[]")
            except ValueError:
                moods = []
        if not moods:
            missing.append(book)
    filled = 0
    for index, book in enumerate(missing):
        if getattr(task, "stat", None) == "cancelled":
            break
        found = provider.lookup(book)
        row = have.get(int(book.id)) or ub.session.query(HardcoverBook).filter(HardcoverBook.book_id == int(book.id)).one_or_none()
        if row is not None and not row.error:
            try:
                moods = json.loads(row.moods or "[]")
            except ValueError:
                moods = []
            if moods:
                filled += 1
        if missing:
            task.progress = float(index + 1) / float(len(missing))
        if found is None:
            continue
    clear_evidence_cache()
    return len(missing), filled
