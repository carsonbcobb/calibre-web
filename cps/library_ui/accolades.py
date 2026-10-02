# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Sourced accolades and press quotes. Nothing here is invented.

Lookups run from the admin scan, in the background. Pages only read
rows already stored in app.db.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .logger_helper import log

_CACHE_DAYS = 30
_USER_AGENT = "DeadMediaSociety/1.0 (local library catalog; accolade scan)"
_WIKIDATA = "https://query.wikidata.org/sparql"
_RANK = {
    "award_win": 0,
    "bestseller": 1,
    "adaptation": 2,
    "award_nominee": 3,
    "list": 4,
    "critical": 5,
}
_PUBLICATIONS = (
    ("new york times", "The New York Times"),
    ("washington post", "The Washington Post"),
    ("los angeles times", "Los Angeles Times"),
    ("the guardian", "The Guardian"),
    ("the new yorker", "The New Yorker"),
    ("new yorker", "The New Yorker"),
    ("publishers weekly", "Publishers Weekly"),
    ("kirkus", "Kirkus"),
    ("booklist", "Booklist"),
    ("school library journal", "School Library Journal"),
    ("library journal", "Library Journal"),
    ("sunday times", "The Sunday Times"),
    ("the telegraph", "The Telegraph"),
    ("the independent", "The Independent"),
    ("the observer", "The Observer"),
    ("the atlantic", "The Atlantic"),
    ("wall street journal", "The Wall Street Journal"),
    ("boston globe", "The Boston Globe"),
    ("chicago tribune", "Chicago Tribune"),
    ("usa today", "USA Today"),
    ("entertainment weekly", "Entertainment Weekly"),
    ("financial times", "Financial Times"),
    ("the times", "The Times"),
    ("npr", "NPR"),
)
_NAMES = (
    ("new york times", "NYT"),
    ("goodreads choice", "Goodreads Choice"),
    ("pulitzer", "Pulitzer"),
    ("booker", "Booker"),
    ("hugo", "Hugo"),
    ("nebula", "Nebula"),
    ("locus", "Locus"),
    ("world fantasy", "World Fantasy"),
    ("national book", "National Book"),
    ("edgar", "Edgar"),
    ("netflix", "Netflix"),
)
_PHRASES = (
    (r"new york times best[\s-]?seller", "bestseller", "New York Times bestseller"),
    (r"#\s*1 new york times", "bestseller", "New York Times bestseller"),
    (r"usa today best[\s-]?seller", "bestseller", "USA Today bestseller"),
    (r"sunday times best[\s-]?seller", "bestseller", "Sunday Times bestseller"),
    (r"winner of the hugo award", "award_win", "Hugo Award"),
    (r"hugo award winner", "award_win", "Hugo Award"),
    (r"hugo winner", "award_win", "Hugo Award"),
    (r"nebula award winner", "award_win", "Nebula Award"),
    (r"winner of the nebula award", "award_win", "Nebula Award"),
    (r"nebula winner", "award_win", "Nebula Award"),
    (r"nebula nominee", "award_nominee", "Nebula Award"),
    (r"nominated for the nebula", "award_nominee", "Nebula Award"),
    (r"pulitzer prize", "award_win", "Pulitzer Prize"),
    (r"booker longlist", "list", "Booker Longlist"),
    (r"booker shortlist", "list", "Booker Shortlist"),
    (r"booker prize", "award_win", "Booker Prize"),
    (r"goodreads choice", "award_win", "Goodreads Choice"),
    (r"now a netflix series", "adaptation", "Netflix series"),
    (r"netflix series", "adaptation", "Netflix series"),
    (r"soon to be a netflix series", "adaptation", "Netflix series"),
    (r"soon to be a major motion picture", "adaptation", "Major motion picture"),
    (r"soon to be a major film", "adaptation", "Major motion picture"),
    (r"now a major motion picture", "adaptation", "Now a major motion picture"),
    (r"major motion picture", "adaptation", "Major motion picture"),
    (r"bram stoker award", "award_win", "Bram Stoker Award"),
    (r"edgar award", "award_win", "Edgar Award"),
    (r"newbery medal", "award_win", "Newbery Medal"),
    (r"locus award", "award_win", "Locus Award"),
    (r"arthur c\.? clarke award", "award_win", "Arthur C. Clarke Award"),
    (r"time(?:'s)? 100", "list", "Time 100"),
)
_WIN_AWARD = re.compile(
    r"winner of the ([A-Za-z][A-Za-z0-9' ]{2,40}? award)",
    re.IGNORECASE,
)
_NOM_AWARD = re.compile(
    r"nominated for(?: the)? ([A-Za-z][A-Za-z0-9' ]{2,40}? award)",
    re.IGNORECASE,
)
_QUOTE_RES = (
    re.compile(
        r"[“\"]([^”\"]{12,240})[”\"]\s*(?:\u2014|\u2013|-)\s*([A-Z][^<\n]{1,80})"
    ),
    re.compile(
        r"(?:^|\n)\s*[“\"]([^”\"]{12,240})[”\"]\s*(?:\n|<br\s*/?>)\s*(?:\u2014|\u2013|-)\s*([^\n<]{2,80})",
        re.IGNORECASE,
    ),
)


class Provider:
    """One source of accolades or quotes. Add a subclass and list it in PROVIDERS."""

    name = "base"

    def accolades(self, book, text):
        return []

    def quotes(self, book, text):
        return []


class DescriptionProvider(Provider):
    """Phrases already written in the book description or comments."""

    name = "description"

    def accolades(self, book, text):
        return parse_accolades(text)

    def quotes(self, book, text):
        return parse_quotes(text)


class WikidataProvider(Provider):
    """Award received (P166) and nominated for (P1411) from the public SPARQL endpoint."""

    name = "wikidata"

    def accolades(self, book, text):
        # Reverse and forward lookups live in accolade_sources.lookup.
        # This method stays so the provider list is unchanged.
        return []


class HardcoverProvider(Provider):
    """Reserved for a later Hardcover accolade lookup. Returns nothing today."""

    name = "hardcover"


class OpenLibraryProvider(Provider):
    """Reserved for a later Open Library accolade lookup. Returns nothing today."""

    name = "openlibrary"


class ReceptionProvider(Provider):
    """Reserved for a Wikipedia reception section or a licensed quote API.

    A future subclass should save the source URL on every quote and return
    only text that came from that page. This one returns nothing.
    """

    name = "reception"


PROVIDERS = (
    DescriptionProvider(),
    WikidataProvider(),
    HardcoverProvider(),
    OpenLibraryProvider(),
    ReceptionProvider(),
)


def tags_for(book_id, limit=None):
    """Display tags already stored for one book. Never calls the network."""
    rows = _rows_for([book_id]).get(int(book_id), [])
    tags = []
    for row in rows:
        tag = _present(row)
        if tag:
            tags.append(tag)
    if limit:
        return tags[: int(limit)]
    return tags


def tags_for_ids(book_ids, limit=2):
    grouped = _rows_for(book_ids)
    rows = []
    for book_id in book_ids or []:
        rows.extend(grouped.get(int(book_id), []))
    rows.sort(key=lambda row: (_RANK.get(row.type, 9), -(row.year or 0), row.label or ""))
    tags = []
    seen = set()
    for row in rows:
        tag = _present(row)
        if not tag or not tag["label"] or tag["label"] in seen:
            continue
        seen.add(tag["label"])
        tags.append(tag)
        if len(tags) >= int(limit):
            break
    return tags


def top_accolade(book_id):
    found = tags_for(book_id, 1)
    return found[0] if found else None


def best_accolade(book_ids):
    rows = []
    grouped = _rows_for(book_ids)
    for book_id in book_ids or []:
        rows.extend(grouped.get(int(book_id), []))
    if not rows:
        return None
    rows.sort(key=lambda row: (_RANK.get(row.type, 9), -(row.year or 0), row.label or ""))
    for row in rows:
        tag = _present(row)
        if tag:
            return tag
    return None


def quotes_for(book_id):
    from .. import ub
    from .models import BookQuote

    try:
        rows = (ub.session.query(BookQuote)
                .filter(BookQuote.book_id == int(book_id))
                .order_by(BookQuote.id.asc())
                .all())
    except Exception:
        ub.session.rollback()
        return []
    ready = []
    for row in rows:
        if not (row.quote or "").strip() or not (row.publication or "").strip():
            continue
        ready.append({
            "id": row.id,
            "quote": row.quote.strip(),
            "publication": row.publication.strip(),
            "author": row.author_of_review or "",
            "url": row.url or "",
            "manual": bool(row.manual),
        })
    return ready


def quote_sections(book_id, html):
    """Featured quotes, then any other sourced quotes that are not already featured."""
    featured = _featured_quotes(book_id, html)
    used = {item["quote"].casefold() for item in featured}
    extra = []
    for row in quotes_for(book_id):
        publication = _publication_label(row["publication"])
        if row["quote"].casefold() in used or not publication:
            continue
        extra.append(dict(row, publication=publication))
    return {"featured": featured, "extra": extra[:3]}


def purge_disallowed():
    """Delete stored accolades that are not real recognitions. Manual rows stay."""
    from .. import ub
    from .models import BookAccolade

    removed = 0
    try:
        rows = (ub.session.query(BookAccolade)
                .filter(BookAccolade.manual == False)  # noqa: E712
                .all())
    except Exception:
        ub.session.rollback()
        return {"removed": 0, "books": 0}
    for row in rows:
        kept = _accept_item({
            "label": row.label,
            "type": row.type,
            "year": row.year,
            "source": row.source or "",
            "source_url": row.source_url or "",
        })
        if kept is None:
            ub.session.delete(row)
            removed += 1
            continue
        row.type = kept["type"]
        row.label = _display_label(kept)[:200]
        row.year = _year(kept.get("year"))
    ub.session_commit("Accolade cleanup")
    _clear_request_cache()
    books = (ub.session.query(BookAccolade.book_id).distinct().count())
    return {"removed": removed, "books": books}


def about_html(book_id, html):
    """Description with stored pull quotes removed so they are not shown twice."""
    text = html or ""
    for row in quotes_for(book_id):
        quote = row["quote"]
        if quote and quote in text:
            text = text.replace(quote, "")
        publication = row["publication"]
        if publication and publication in text:
            text = re.sub(
                r"(?:\u2014|\u2013|-)\s*" + re.escape(publication),
                "",
                text,
                count=1,
            )
    text = re.sub(r"(<p>\s*</p>|<br\s*/?>\s*){2,}", "<br>", text)
    return text


def award_win_ids():
    from .. import ub
    from .models import BookAccolade

    try:
        rows = ub.session.query(BookAccolade.book_id).filter(BookAccolade.type == "award_win").all()
    except Exception:
        ub.session.rollback()
        return set()
    return {row[0] for row in rows}


def has_award(book, wins):
    if not wins:
        return False
    if book.get("id") in wins:
        return True
    return bool(set(book.get("member_ids") or ()) & wins)


def counts():
    from .. import ub
    from .models import BookAccolade, BookQuote

    try:
        accolades = ub.session.query(BookAccolade.book_id).distinct().count()
        quotes = ub.session.query(BookQuote.book_id).distinct().count()
    except Exception:
        ub.session.rollback()
        return 0, 0
    return int(accolades or 0), int(quotes or 0)


def recent_accolades(limit=40):
    from .. import ub
    from .models import BookAccolade

    try:
        return (ub.session.query(BookAccolade)
                .order_by(BookAccolade.id.desc())
                .limit(limit)
                .all())
    except Exception:
        ub.session.rollback()
        return []


def recent_quotes(limit=40):
    from .. import ub
    from .models import BookQuote

    try:
        return (ub.session.query(BookQuote).order_by(BookQuote.id.desc()).limit(limit).all())
    except Exception:
        ub.session.rollback()
        return []


def save_accolade(book_id, type_name, label, year, source_url, row_id=None):
    from .. import ub
    from .models import BookAccolade

    kind = type_name if type_name in _RANK else "critical"
    label = (label or "").strip()
    if not label:
        return False
    row = None
    if row_id:
        row = ub.session.query(BookAccolade).filter(BookAccolade.id == int(row_id)).one_or_none()
    if row is None:
        row = BookAccolade(book_id=int(book_id), source="manual", manual=True)
        ub.session.add(row)
    row.book_id = int(book_id)
    row.type = kind
    row.label = label[:200]
    row.year = _year(year)
    row.source_url = (source_url or "").strip()[:400]
    row.manual = True
    row.source = row.source or "manual"
    ub.session_commit("Accolade saved")
    _clear_request_cache()
    return True


def replace_hardcover_lists(book_id, lists, source_url):
    """Replace Hardcover list tags for one book. Other sources stay."""
    from .. import ub
    from .models import BookAccolade

    (ub.session.query(BookAccolade)
     .filter(BookAccolade.book_id == int(book_id))
     .filter(BookAccolade.source == "hardcover")
     .filter(BookAccolade.manual == False)  # noqa: E712
     .delete(synchronize_session=False))
    seen = set()
    for item in lists or []:
        kept = _accept_item({
            "label": item.get("name") or "",
            "type": "list",
            "year": None,
            "source": "hardcover",
            "source_url": item.get("url") or source_url or "",
        })
        if not kept or kept["label"].casefold() in seen:
            continue
        seen.add(kept["label"].casefold())
        ub.session.add(BookAccolade(
            book_id=int(book_id),
            type=kept["type"],
            label=_display_label(kept)[:200],
            year=_year(kept.get("year")),
            source="hardcover",
            source_url=(kept.get("source_url") or "")[:400],
            manual=False,
        ))
    ub.session_commit("Hardcover lists")
    _clear_request_cache()


def delete_accolade(row_id):
    from .. import ub
    from .models import BookAccolade

    row = ub.session.query(BookAccolade).filter(BookAccolade.id == int(row_id)).one_or_none()
    if row is None:
        return
    ub.session.delete(row)
    ub.session_commit("Accolade deleted")
    _clear_request_cache()


def save_quote(book_id, quote, publication, author, url, row_id=None):
    from .. import ub
    from .models import BookQuote

    quote = _fit_quote(quote)
    publication = (publication or "").strip()
    if not quote or not publication:
        return False
    row = None
    if row_id:
        row = ub.session.query(BookQuote).filter(BookQuote.id == int(row_id)).one_or_none()
    if row is None:
        row = BookQuote(book_id=int(book_id), source="manual", manual=True)
        ub.session.add(row)
    row.book_id = int(book_id)
    row.quote = quote
    row.publication = publication[:160]
    row.author_of_review = (author or "").strip()[:160]
    row.url = (url or "").strip()[:400]
    row.manual = True
    row.source = row.source or "manual"
    ub.session_commit("Quote saved")
    return True


def delete_quote(row_id):
    from .. import ub
    from .models import BookQuote

    row = ub.session.query(BookQuote).filter(BookQuote.id == int(row_id)).one_or_none()
    if row is None:
        return
    ub.session.delete(row)
    ub.session_commit("Quote deleted")


def enqueue_scan(user_name, unmatched_only=False):
    from flask import current_app
    from ..services.worker import WorkerThread

    application = current_app._get_current_object()
    WorkerThread.add(user_name or "admin", task_instance(application, unmatched_only), hidden=False)


def scan_library(task, application, unmatched_only=False):
    """Scan books whose cache is older than 30 days. Manual rows stay.

    The worker has no request, so this never reads current_user or the request.
    A book that raises is counted unmatched and the scan continues.
    """
    from collections import Counter

    from .. import db
    from ..services.worker import STAT_CANCELLED, STAT_ENDED
    from .accolade_sources import prepare

    purge_disallowed()
    prepare()
    worker_db = db.CalibreDB(application)
    books = worker_db.session.query(db.Books).all()
    total = len(books)
    before = sum(1 for book in books if _has_accolade(getattr(book, "id", None)))
    matched = 0
    unmatched = 0
    reasons = Counter()
    for index, book in enumerate(books):
        if task is not None and task.stat in (STAT_CANCELLED, STAT_ENDED):
            break
        book_id = getattr(book, "id", None)
        try:
            skip = _has_accolade(book_id) if unmatched_only else _fresh(book_id)
            if not skip:
                misses = scan_book(book)
                if not _has_accolade(book_id) and misses:
                    reasons[misses] += 1
            if _has_accolade(book_id):
                matched += 1
            else:
                unmatched += 1
        except Exception as error:
            unmatched += 1
            reasons["request error"] += 1
            log.error("Accolade scan book %s failed: %s", book_id, error)
        if task is not None and total:
            task.progress = min(1, float(index + 1) / float(total))
    return before, matched, unmatched, reasons.most_common(5)


def _has_accolade(book_id):
    from .. import ub
    from .models import BookAccolade

    if not book_id:
        return False
    try:
        found = (ub.session.query(BookAccolade.id)
                 .filter(BookAccolade.book_id == int(book_id))
                 .first())
        return found is not None
    except Exception:
        ub.session.rollback()
        return False


def _has_stored(book_id):
    from .. import ub
    from .models import BookAccolade, BookQuote

    if not book_id:
        return False
    try:
        found = (ub.session.query(BookAccolade.id)
                 .filter(BookAccolade.book_id == int(book_id))
                 .first())
        if found is not None:
            return True
        found = (ub.session.query(BookQuote.id)
                 .filter(BookQuote.book_id == int(book_id))
                 .first())
        return found is not None
    except Exception:
        ub.session.rollback()
        return False


def scan_book(book):
    from .. import ub
    from .models import BookAccolade, BookQuote

    from .accolade_sources import lookup, save_attempts

    text = _plain_comments(book)
    found_accolades = []
    found_quotes = []
    attempts = []
    failed = False
    described = parse_accolades(text)
    kept_described = [item for item in (_accept_item(item) for item in described) if item]
    if kept_described:
        for item in kept_described:
            item["_ready"] = True
        found_accolades.extend(kept_described)
        attempts.append({"provider": "description", "matched": True, "identifier": "description", "reason": "matched"})
    elif described:
        attempts.append({"provider": "description", "matched": False, "identifier": "description", "reason": "filtered by the allowlist"})
    else:
        attempts.append({"provider": "description", "matched": False, "identifier": "description", "reason": "no results"})
    extra, extra_attempts = lookup(book, text)
    found_accolades.extend(extra)
    attempts.extend(extra_attempts)
    for provider in PROVIDERS:
        try:
            found_quotes.extend(provider.quotes(book, text) or [])
        except Exception as error:
            failed = True
            log.debug("%s lookup failed for book %s: %s", provider.name, book.id, error)
    manuals = (ub.session.query(BookAccolade)
               .filter(BookAccolade.book_id == book.id)
               .filter(BookAccolade.manual == True)  # noqa: E712
               .all())
    manual_labels = {(row.label or "").casefold() for row in manuals}
    (ub.session.query(BookAccolade)
     .filter(BookAccolade.book_id == book.id)
     .filter(BookAccolade.manual == False)  # noqa: E712
     .filter(BookAccolade.source != "hardcover")
     .delete(synchronize_session=False))
    seen = set(manual_labels)
    for item in found_accolades:
        kept = item if item.get("_ready") else _accept_item(item)
        if not kept:
            continue
        label = _display_label(kept)[:200]
        if not label or label.casefold() in seen:
            continue
        seen.add(label.casefold())
        ub.session.add(BookAccolade(
            book_id=book.id,
            type=kept["type"],
            label=label,
            year=_year(kept.get("year")),
            source=(kept.get("source") or "")[:32],
            source_url=(kept.get("source_url") or "")[:400],
            manual=False,
        ))
    manual_quotes = (ub.session.query(BookQuote)
                     .filter(BookQuote.book_id == book.id)
                     .filter(BookQuote.manual == True)  # noqa: E712
                     .all())
    quote_seen = {(row.quote or "").casefold() for row in manual_quotes}
    (ub.session.query(BookQuote)
     .filter(BookQuote.book_id == book.id)
     .filter(BookQuote.manual == False)  # noqa: E712
     .delete(synchronize_session=False))
    for item in found_quotes:
        quote = _fit_quote(item.get("quote"))
        publication = (item.get("publication") or "").strip()
        if not quote or not publication or quote.casefold() in quote_seen:
            continue
        quote_seen.add(quote.casefold())
        ub.session.add(BookQuote(
            book_id=book.id,
            quote=quote,
            publication=publication[:160],
            author_of_review=(item.get("author") or "")[:160],
            url=(item.get("url") or "")[:400],
            source=(item.get("source") or "description")[:32],
            manual=False,
        ))
    from .reviews import cache_reviews
    try:
        cache_reviews(book)
    except Exception as error:
        log.error("Review cache failed for book %s: %s", book.id, error)
    save_attempts(book.id, attempts)
    blocked = any(row.get("reason") in ("rate limited", "request error") for row in attempts)
    if not failed and not blocked:
        _touch(book.id)
    ub.session_commit("Accolade scan for book %s" % book.id)
    _clear_request_cache()
    misses = [row["reason"] for row in attempts if not row.get("matched") and row.get("reason")]
    if not misses:
        return ""
    return max(set(misses), key=misses.count)


def parse_accolades(text):
    plain = _plain(text)
    if not plain:
        return []
    found = []
    seen = set()
    for pattern, kind, label in _PHRASES:
        match = re.search(pattern, plain, re.IGNORECASE)
        if not match:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append({
            "type": kind,
            "label": label,
            "year": _nearby_year(plain, match.start()),
            "source": "description",
            "source_url": "",
        })
    for match in _WIN_AWARD.finditer(plain):
        label = _tidy(match.group(1))
        if label.casefold() in seen:
            continue
        seen.add(label.casefold())
        found.append({
            "type": "award_win",
            "label": label,
            "year": _nearby_year(plain, match.start()),
            "source": "description",
            "source_url": "",
        })
    for match in _NOM_AWARD.finditer(plain):
        label = _tidy(match.group(1))
        if label.casefold() in seen:
            continue
        seen.add(label.casefold())
        found.append({
            "type": "award_nominee",
            "label": label,
            "year": _nearby_year(plain, match.start()),
            "source": "description",
            "source_url": "",
        })
    return found


def parse_quotes(text):
    plain = text or ""
    found = []
    seen = set()
    for pattern in _QUOTE_RES:
        for match in pattern.finditer(plain):
            quote = _fit_quote(_plain(match.group(1)))
            publication = _tidy(match.group(2))
            if not quote or not publication or quote.casefold() in seen:
                continue
            if len(quote.split()) > 25:
                continue
            seen.add(quote.casefold())
            found.append({
                "quote": quote,
                "publication": publication[:160],
                "author": "",
                "url": "",
                "source": "description",
            })
    return found


def short_label(type_name, label, year):
    raw = (label or "").strip()
    folded = raw.casefold()
    name = raw
    for needle, short in _NAMES:
        if needle in folded:
            name = short
            break
    year_text = str(year) if year else ""
    if type_name == "award_win":
        if name == "Pulitzer":
            text = "Pulitzer Prize"
        elif name == "Goodreads Choice":
            text = "Goodreads Choice"
        elif name == "NYT":
            text = "NYT Bestseller"
        else:
            text = "%s Winner" % name
            if year_text:
                text = "%s %s" % (text, year_text)
    elif type_name == "award_nominee":
        if "longlist" in folded:
            text = "%s Longlist" % name
        elif "shortlist" in folded:
            text = "%s Shortlist" % name
        else:
            text = "%s Nominee" % name
    elif type_name == "bestseller":
        text = "NYT Bestseller" if name == "NYT" else "%s Bestseller" % name
    elif type_name == "adaptation":
        if "netflix" in folded:
            text = "Netflix Series"
        elif "motion picture" in folded:
            text = "Major Motion Picture"
        else:
            text = name
    elif type_name == "list":
        if "longlist" in folded and not name.endswith("Longlist"):
            text = "%s Longlist" % name
        elif "shortlist" in folded and not name.endswith("Shortlist"):
            text = "%s Shortlist" % name
        elif name.endswith("List") or "list" in folded:
            text = name
        else:
            text = "%s List" % name
    else:
        text = name
    return text


def wikidata_accolades(book):
    isbn = _isbn(book)
    if isbn:
        query = _isbn_query(isbn)
    else:
        author = ""
        if book.authors:
            author = (book.authors[0].name or "").replace("|", " ")
        query = _title_query(book.title or "", author)
    if not query:
        return []
    time.sleep(1.1)
    payload = _sparql(query)
    rows = []
    for binding in payload:
        award = ((binding.get("awardLabel") or {}).get("value") or "").strip()
        if not award or award.startswith("Q"):
            continue
        kind = (binding.get("kind") or {}).get("value") or "win"
        year = _year((binding.get("year") or {}).get("value"))
        rows.append({
            "type": "award_win" if kind == "win" else "award_nominee",
            "label": award,
            "year": year,
            "source": "wikidata",
            "source_url": (binding.get("award") or {}).get("value") or "",
        })
    return rows


def _isbn_query(isbn):
    safe = isbn.replace("\\", "").replace('"', "")
    compact = re.sub(r"[^0-9Xx]", "", safe)
    return """
SELECT ?award ?awardLabel ?kind ?year WHERE {
  VALUES ?isbn { "%s" "%s" }
  ?book wdt:P212 ?isbn .
  {
    ?book p:P166 ?statement .
    ?statement ps:P166 ?award .
    BIND("win" AS ?kind)
  } UNION {
    ?book p:P1411 ?statement .
    ?statement ps:P1411 ?award .
    BIND("nominee" AS ?kind)
  }
  OPTIONAL { ?statement pq:P585 ?time . BIND(YEAR(?time) AS ?year) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} LIMIT 12
""" % (safe, compact)


def _title_query(title, author):
    title = (title or "").replace("\\", "").replace('"', "").strip()
    author = (author or "").replace("\\", "").replace('"', "").strip()
    if len(title) < 2 or len(author) < 2:
        return ""
    return """
SELECT ?award ?awardLabel ?kind ?year WHERE {
  ?book rdfs:label "%s"@en .
  ?author rdfs:label "%s"@en .
  ?book wdt:P50 ?author .
  {
    ?book p:P166 ?statement .
    ?statement ps:P166 ?award .
    BIND("win" AS ?kind)
  } UNION {
    ?book p:P1411 ?statement .
    ?statement ps:P1411 ?award .
    BIND("nominee" AS ?kind)
  }
  OPTIONAL { ?statement pq:P585 ?time . BIND(YEAR(?time) AS ?year) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} LIMIT 8
""" % (title, author)


def _sparql(query):
    url = _WIKIDATA + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return ((payload.get("results") or {}).get("bindings") or [])


def _accept_item(item):
    from .accolade_allowlist import accept
    return accept(item)


def _display_label(item):
    if item.get("type") == "list":
        return item.get("label") or ""
    return short_label(item.get("type"), item.get("label"), item.get("year"))


def _known_publication(name):
    return _publication_label(name) != ""


def _publication_label(name):
    folded = (name or "").casefold()
    for needle, label in _PUBLICATIONS:
        if needle in folded:
            return label
    return ""


def _featured_quotes(book_id, html):
    stored = []
    for row in quotes_for(book_id):
        publication = _publication_label(row["publication"])
        if publication and _strong_quote(row["quote"]):
            stored.append(dict(row, publication=publication))
    if stored:
        stored.sort(key=lambda row: len(row["quote"].split()))
        return stored[:5]
    parsed = []
    for item in parse_quotes(html or ""):
        publication = _publication_label(item.get("publication"))
        if not publication or not _strong_quote(item.get("quote")):
            continue
        parsed.append({
            "quote": item["quote"],
            "publication": publication,
            "url": item.get("url") or "",
        })
    parsed.sort(key=lambda row: len(row["quote"].split()))
    return parsed[:5]


def _strong_quote(quote):
    count = len((quote or "").split())
    return 4 <= count <= 40


def _present(row):
    kind = row.type or "critical"
    label = row.label or ""
    year = row.year
    if not getattr(row, "manual", False):
        kept = _accept_item({
            "label": label,
            "type": kind,
            "year": year,
            "source": row.source or "",
            "source_url": row.source_url or "",
        })
        if kept is None:
            return None
        kind = kept["type"]
        year = kept.get("year")
        label = _display_label(kept)
    if not label:
        return None
    tone = "win" if kind == "award_win" else ("nominee" if kind == "award_nominee" else "note")
    icon = "film" if kind == "adaptation" else "laurel"
    return {
        "id": row.id,
        "label": label,
        "tone": tone,
        "icon": icon,
        "year": row.year,
        "result": _result(kind),
        "source_url": row.source_url or "",
        "type": kind,
    }


def _result(kind):
    return {
        "award_win": "Winner",
        "award_nominee": "Nominee",
        "bestseller": "Bestseller",
        "list": "Listed",
        "adaptation": "Adaptation",
        "critical": "Noted",
    }.get(kind, "Noted")


def _rows_for(book_ids):
    from flask import g, has_request_context

    ids = [int(item) for item in (book_ids or []) if item]
    if not ids:
        return {}
    if has_request_context():
        cached = getattr(g, "_book_accolades", None)
        if cached is None:
            cached = _load_all()
            g._book_accolades = cached
        return cached
    return _load_all()


def _load_all():
    from .. import ub
    from .models import BookAccolade

    grouped = {}
    try:
        rows = ub.session.query(BookAccolade).all()
    except Exception:
        ub.session.rollback()
        return grouped
    for row in rows:
        grouped.setdefault(row.book_id, []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: (_RANK.get(row.type, 9), -(row.year or 0), row.label or ""))
    return grouped


def _clear_request_cache():
    try:
        from flask import g, has_request_context
        if has_request_context():
            g._book_accolades = None
    except Exception:
        pass


def _fresh(book_id):
    from .. import ub
    from .models import AccoladeAttempt, BookLookup

    tried = (ub.session.query(AccoladeAttempt.id)
             .filter(AccoladeAttempt.book_id == int(book_id))
             .first())
    if tried is None:
        return False
    row = (ub.session.query(BookLookup)
           .filter(BookLookup.book_id == int(book_id))
           .filter(BookLookup.kind == "scan")
           .one_or_none())
    if row is None or row.checked_at is None:
        return False
    stamp = row.checked_at
    if getattr(stamp, "tzinfo", None) is not None:
        stamp = stamp.replace(tzinfo=None)
    return stamp >= datetime.now() - timedelta(days=_CACHE_DAYS)


def _touch(book_id):
    from .. import ub
    from .models import BookLookup

    row = (ub.session.query(BookLookup)
           .filter(BookLookup.book_id == int(book_id))
           .filter(BookLookup.kind == "scan")
           .one_or_none())
    if row is None:
        row = BookLookup(book_id=int(book_id), kind="scan")
        ub.session.add(row)
    row.checked_at = datetime.now()


def _plain_comments(book):
    parts = []
    for comment in book.comments or []:
        parts.append(comment.text or "")
    return _plain(" ".join(parts))


def _plain(value):
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _tidy(value):
    text = _plain(value).strip(" .,:;\"'")
    return text[:160]


def _year(value):
    try:
        year = int(str(value)[:4])
    except (TypeError, ValueError):
        return None
    if 1400 <= year <= 2100:
        return year
    return None


def _nearby_year(text, start):
    window = text[max(0, start - 30): start + 80]
    match = re.search(r"(1[89]\d{2}|20\d{2})", window)
    return int(match.group(1)) if match else None


def _fit_quote(value):
    text = _plain(value).strip(" \"'")
    words = text.split()
    if not words:
        return ""
    if len(words) <= 25:
        return text
    # Only shorten a quote when the source already cut it off.
    if text.endswith("...") or text.endswith("\u2026"):
        return " ".join(words[:24]).rstrip(".") + "..."
    return ""


def _isbn(book):
    for identifier in book.identifiers or []:
        kind = (identifier.type or "").casefold()
        if "isbn" in kind and identifier.val:
            return identifier.val.strip()
    return ""


def task_instance(application, unmatched_only=False):
    """A CalibreTask the worker can run. The app object is captured on the request thread."""
    from ..services.worker import STAT_CANCELLED, STAT_ENDED, CalibreTask

    class _Task(CalibreTask):
        def __init__(self, app_obj, missing_only):
            super(_Task, self).__init__("Scan accolades")
            self.application = app_obj
            self.missing_only = missing_only

        def run(self, worker_thread):
            with self.application.app_context():
                before, matched, unmatched, reasons = scan_library(
                    self, self.application, unmatched_only=self.missing_only
                )
            self.progress = 1
            reason_text = ", ".join("%s (%s)" % (name, count) for name, count in reasons)
            self.message = "Books with an accolade: %s before, %s after. %s are still unmatched." % (
                before, matched, unmatched,
            )
            if reason_text:
                self.message += " Top reasons: %s." % reason_text
            if self.stat not in (STAT_CANCELLED, STAT_ENDED):
                self._handleSuccess()

        @property
        def name(self):
            return "Rescan unmatched" if self.missing_only else "Scan accolades"

        @property
        def is_cancellable(self):
            return True

    return _Task(application, unmatched_only)
