# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Discover rows. Titles and rules live in shelf_config.py."""

from .home_rows import _canonical
from .logger_helper import log

_PLANS = {}


def log_scope():
    """Write the Discover book counts once per page render."""
    try:
        from .. import calibre_db, config, db, ub
        from ..cw_login import current_user

        catalog, _names, raw = _prepare()
        total = int(calibre_db.session.query(db.Books.id).count())
        archived = 0
        if current_user.is_authenticated:
            archived = int(ub.session.query(ub.ArchivedBook)
                           .filter(ub.ArchivedBook.user_id == int(current_user.id))
                           .filter(ub.ArchivedBook.is_archived == True)  # noqa: E712
                           .count())
        noise_only = sum(1 for book in catalog if not book["tags"])
        missing_time = sum(1 for book in catalog if not book["minutes"])
        missing_year = sum(1 for book in catalog if not book.get("year"))
        missing_cover = 0
        try:
            missing_cover = int(calibre_db.session.query(db.Books.id).filter(db.Books.has_cover == 0).count())
        except Exception:
            missing_cover = 0
        language = current_user.filter_language() if current_user.is_authenticated else "all"
        denied = (current_user.denied_tags or "") if current_user.is_authenticated else ""
        allowed = (current_user.allowed_tags or "") if current_user.is_authenticated else ""
        log.info(
            "Discover scope: %s books in metadata.db, %s after common filters, %s units eligible for rows and the grid. "
            "Language filter %s, denied tags %r, allowed tags %r, restricted column %s, archived for this user %s, "
            "books per page %s (not applied). Covers missing %s (not required). "
            "Books with only noise tags %s (shown under All). Books missing a read time %s (still included). "
            "Books missing a usable publish year %s (still included). No rating minimum.",
            total, len(raw), len(catalog), language or "all", denied, allowed,
            config.config_restricted_column, archived, config.config_books_per_page,
            missing_cover, noise_only, missing_time, missing_year,
        )
    except Exception as error:
        log.debug("Discover scope log failed: %s", error)


def get_plan(seed, genre_id, panel_ids):
    """Row assignment and grid order for one seed, genre, and featured panel."""
    from ..cw_login import current_user
    from .shelf_engine import discover_plan
    from .units import metadata_mtime

    user_id = int(current_user.id) if current_user.is_authenticated else 0
    seed = (seed or "discover")[:40]
    genre_key = str(genre_id).strip() if genre_id else ""
    if genre_key.isdigit() and int(genre_key) == 0:
        genre_key = ""
    panel_key = tuple(int(book_id) for book_id in (panel_ids or []) if book_id)
    key = (user_id, seed, genre_key, panel_key, metadata_mtime())
    cached = _PLANS.get(key)
    if cached:
        return cached
    plan = discover_plan(seed, genre_key or None, panel_key)
    _PLANS[key] = plan
    if len(_PLANS) > 40:
        for old in list(_PLANS)[:20]:
            _PLANS.pop(old, None)
    return plan


def _prepare():
    from .browse import _world
    from .. import calibre_db, db

    catalog, names = _world()
    years = {}
    try:
        ids = [book["id"] for book in catalog]
        if ids:
            for book_id, pubdate in calibre_db.session.query(db.Books.id, db.Books.pubdate).filter(db.Books.id.in_(ids)):
                year = getattr(pubdate, "year", None)
                if year and 1800 <= int(year) <= 2100:
                    years[book_id] = int(year)
    except Exception as error:
        log.debug("Discover years unavailable: %s", error)
    sizes = {}
    for book in catalog:
        if book["series_id"]:
            sizes[book["series_id"]] = sizes.get(book["series_id"], 0) + 1
    for book in catalog:
        raw = set()
        labels = []
        for tag_id in book["tag_ids"]:
            label = names.get(tag_id) or ""
            folded = label.strip().casefold()
            if not folded:
                continue
            raw.add(folded)
            canon = _canonical(label)
            if canon:
                labels.append((label, canon))
        book["series_len"] = sizes.get(book["series_id"] or 0, 0)
        book["year"] = years.get(book["id"])
        book["raw_tags"] = raw
        book["labels"] = labels
        book["search"] = " ".join([book.get("blurb") or ""] + list(raw))
    from .units import display_units

    return display_units(catalog), names, catalog
