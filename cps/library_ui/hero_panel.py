# -*- coding: utf-8 -*-

"""Quotes for the hero. Only stored quotes, and only from the featured book or its series."""

import re

from .accolades import _known_publication, _publication_label

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_SENTENCE = re.compile(r"[^.!?]*[.!?]+(?:\s|$)")


def series_quotes(members):
    """Quotes from books in this series. Book 1 is preferred."""
    ids = [book["id"] for book in (members or []) if book.get("id")]
    featured = ids[0] if ids else None
    return _quotes(ids, featured)


def book_quotes(book_id):
    """Quotes that belong to this book only."""
    if not book_id:
        return []
    return _quotes([int(book_id)], int(book_id))


def _quotes(book_ids, featured_id):
    from .. import ub
    from .models import BookQuote

    ids = []
    for book_id in book_ids:
        try:
            number = int(book_id)
        except (TypeError, ValueError):
            continue
        if number not in ids:
            ids.append(number)
    if not ids:
        return []
    try:
        featured = int(featured_id) if featured_id else None
    except (TypeError, ValueError):
        featured = None
    try:
        rows = (ub.session.query(BookQuote)
                .filter(BookQuote.book_id.in_(ids))
                .all())
    except Exception:
        ub.session.rollback()
        return []
    titles = _titles(ids)
    ready = []
    seen = set()
    for row in rows:
        quote = _fit((row.quote or "").strip())
        publication = _publication_label(row.publication) or (row.publication or "").strip()
        if not quote or not publication:
            continue
        key = quote.casefold()
        if key in seen:
            continue
        seen.add(key)
        book_id = int(row.book_id)
        ready.append({
            "quote": quote,
            "publication": publication,
            "url": row.url or "",
            "book_id": book_id,
            "book_title": "" if book_id == featured else (titles.get(book_id) or ""),
            "words": _words(quote),
            "preferred": book_id == featured,
            "known": _known_publication(row.publication),
        })
    ready.sort(key=lambda item: (
        0 if item["preferred"] else 1,
        0 if item["known"] else 1,
        item["words"],
    ))
    chosen = ready[:5]
    for item in chosen:
        item.pop("words", None)
        item.pop("preferred", None)
        item.pop("known", None)
    return chosen


def _fit(text):
    """Keep the quote, or one whole sentence from it. Never cut mid sentence."""
    text = " ".join((text or "").split())
    if not text:
        return ""
    if _words(text) <= 30:
        return text
    for match in _SENTENCE.finditer(text):
        sentence = " ".join(match.group(0).split())
        if sentence and _words(sentence) <= 30:
            return sentence
    return ""


def _words(text):
    return len(_WORD.findall(text or ""))


def _titles(book_ids):
    try:
        from .. import calibre_db, db

        found = {}
        rows = calibre_db.session.query(db.Books.id, db.Books.title).filter(db.Books.id.in_(book_ids)).all()
        for book_id, title in rows:
            found[int(book_id)] = title or ""
        return found
    except Exception:
        return {}
