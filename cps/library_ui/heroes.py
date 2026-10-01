# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import re

from .logger_helper import log
from .models import LibraryHero


def list_heroes():
    from .. import ub

    return (ub.session.query(LibraryHero)
            .order_by(LibraryHero.sort_order.asc(), LibraryHero.id.asc())
            .all())


def hero_slides():
    """Enabled heroes, in order, with the book or shelf they point at."""
    slides = []
    try:
        from .. import calibre_db, db, ub
        rows = (ub.session.query(LibraryHero)
                .filter(LibraryHero.enabled == True)  # noqa: E712
                .order_by(LibraryHero.sort_order.asc(), LibraryHero.id.asc())
                .all())
        for row in rows:
            slide = _slide_for(row, calibre_db, db, ub)
            if slide:
                slides.append(slide)
    except Exception as error:
        log.debug("Featured heroes unavailable: %s", error)
    return slides


def search_books(text, limit=8):
    from .. import calibre_db, db

    cleaned = (text or "").strip()
    if len(cleaned) < 2:
        return []
    like = "%" + cleaned.replace("%", "").replace("_", "") + "%"
    return (calibre_db.session.query(db.Books)
            .filter(db.Books.title.ilike(like))
            .filter(calibre_db.common_filters())
            .order_by(db.Books.sort.asc())
            .limit(limit)
            .all())


def shelf_choices():
    from sqlalchemy import or_
    from ..cw_login import current_user
    from .. import ub

    user_id = int(current_user.id) if current_user.is_authenticated else -1
    return (ub.session.query(ub.Shelf)
            .filter(or_(ub.Shelf.is_public == 1, ub.Shelf.user_id == user_id))
            .order_by(ub.Shelf.name.asc())
            .all())


def add_hero(kind, target_id, headline, blurb):
    from .. import ub

    if kind not in ("book", "collection"):
        return False
    try:
        target_id = int(target_id)
    except (TypeError, ValueError):
        return False
    if not _target_exists(kind, target_id):
        return False
    current = list_heroes()
    order = (current[-1].sort_order + 1) if current else 0
    row = LibraryHero(
        kind=kind,
        target_id=target_id,
        headline=(headline or "").strip()[:200],
        blurb=(blurb or "").strip()[:1000],
        sort_order=order,
        enabled=True,
    )
    ub.session.add(row)
    ub.session_commit("Library UI hero added")
    return True


def delete_hero(hero_id):
    from .. import ub

    ub.session.query(LibraryHero).filter(LibraryHero.id == int(hero_id)).delete()
    ub.session_commit("Library UI hero removed")


def move_hero(hero_id, direction):
    rows = list_heroes()
    index = next((i for i, row in enumerate(rows) if row.id == int(hero_id)), None)
    if index is None:
        return
    swap = index + (1 if direction > 0 else -1)
    if swap < 0 or swap >= len(rows):
        return
    rows[index].sort_order, rows[swap].sort_order = rows[swap].sort_order, rows[index].sort_order
    if rows[index].sort_order == rows[swap].sort_order:
        rows[index].sort_order = index
        rows[swap].sort_order = swap
    from .. import ub
    ub.session_commit("Library UI hero reordered")


def _target_exists(kind, target_id):
    from .. import calibre_db, db, ub

    if kind == "book":
        book = (calibre_db.session.query(db.Books)
                .filter(db.Books.id == target_id)
                .filter(calibre_db.common_filters())
                .first())
        return book is not None
    shelf = ub.session.query(ub.Shelf).filter(ub.Shelf.id == target_id).first()
    return shelf is not None


def _slide_for(row, calibre_db, db, ub):
    if row.kind == "book":
        book = (calibre_db.session.query(db.Books)
                .filter(db.Books.id == row.target_id)
                .filter(calibre_db.common_filters())
                .first())
        if book is None:
            return None
        return {
            "id": row.id,
            "kind": "book",
            "book": book,
            "title": book.title,
            "headline": (row.headline or "").strip(),
            "blurb": (row.blurb or "").strip() or _comment_excerpt(book),
            "href_kind": "book",
        }
    shelf = ub.session.query(ub.Shelf).filter(ub.Shelf.id == row.target_id).first()
    if shelf is None:
        return None
    link = shelf.books.order_by(ub.BookShelf.order.asc()).first()
    book = None
    if link is not None:
        book = calibre_db.session.query(db.Books).filter(db.Books.id == link.book_id).first()
    return {
        "id": row.id,
        "kind": "collection",
        "book": book,
        "shelf": shelf,
        "title": shelf.name,
        "headline": (row.headline or "").strip(),
        "blurb": (row.blurb or "").strip(),
        "href_kind": "collection",
    }


def _comment_excerpt(book):
    if not book.comments:
        return ""
    raw = book.comments[0].text or ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 280:
        text = text[:277].rsplit(" ", 1)[0] + "..."
    return text
