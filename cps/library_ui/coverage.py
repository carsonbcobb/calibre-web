# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Read only coverage report. Does not change which books a page selects."""

from datetime import datetime

from flask_babel import gettext as _

from .logger_helper import log


LIMITS = (
    {"where": "Home row cache", "kind": "cache", "value": "10 minutes, keyed by user id and language"},
    {"where": "Home shelves", "kind": "minimum books", "value": "6 or the shelf is dropped"},
    {"where": "Home shelves", "kind": "maximum books", "value": "20 per shelf, after scoring"},
    {"where": "Home shelves", "kind": "main target", "value": "12 books before a shelf is treated as full"},
    {"where": "Home shelves", "kind": "author cap", "value": "2 books per author on a shelf"},
    {"where": "Home shelves", "kind": "series", "value": "one representative card per series before shelves are filled"},
    {"where": "Home shelves", "kind": "seed", "value": "user id plus the calendar day, shared by every home shelf"},
    {"where": "Home fallback rows", "kind": "maximum rows", "value": "3 extra rows, 20 books each"},
    {"where": "Genres landing", "kind": "minimum books", "value": "8 cards or the row is dropped, after adjacent genres top it up"},
    {"where": "Genres landing", "kind": "maximum books", "value": "8 cards on a row, one series and two books per author"},
    {"where": "Genres landing", "kind": "repeats", "value": "a book is on one row, except Fresh on the shelf"},
    {"where": "Genres landing", "kind": "seed", "value": "a new seed on every page load, and a different seed for each row"},
    {"where": "Genres landing", "kind": "buckets", "value": "raw tags merge in genre_config.py, noise tags are ignored"},
    {"where": "Single genre rows", "kind": "minimum books", "value": "8 or the carousel is omitted"},
    {"where": "Single genre rows", "kind": "maximum books", "value": "8 cards, one series and two books per author"},
    {"where": "Single genre grid", "kind": "limit", "value": "every book in the bucket, no page size"},
    {"where": "Single genre", "kind": "seed", "value": "a new seed on every page load for the playful titles"},
    {"where": "Series landing", "kind": "covers", "value": "at most 3 covers per series card"},
    {"where": "Series landing", "kind": "cache", "value": "10 minutes, keyed by user id and language"},
    {"where": "Series landing", "kind": "seed", "value": "the calendar day, one featured series"},
    {"where": "Single series", "kind": "author row", "value": "at most 20 other books by the same author"},
    {"where": "Discover rows", "kind": "minimum books", "value": "8 or the row is omitted"},
    {"where": "Discover rows", "kind": "maximum books", "value": "12, or 15 for Roll the dice"},
    {"where": "Discover rows", "kind": "row count", "value": "at most 12, and at most one book per 8 in the library"},
    {"where": "Discover rows", "kind": "series and author", "value": "one series and two books per author inside a row"},
    {"where": "Discover grid", "kind": "page size", "value": "24"},
    {"where": "Discover panel", "kind": "limit", "value": "3 books, excluded from the rows and the grid"},
    {"where": "Discover", "kind": "seed", "value": "random token per page load, shared by the rows from that load"},
    {"where": "Login collage", "kind": "cache", "value": "1 hour for the cover list, 2 minutes for the slot cache"},
    {"where": "Login collage", "kind": "filter", "value": "requires a cover file, ignores books with no cover"},
    {"where": "Calibre Web books per page", "kind": "setting", "value": "used by the old catalog pages, not these library pages"},
    {"where": "Common filters", "kind": "filter", "value": "language, allowed tags, denied tags, restricted column, archived books"},
)


def build_report():
    """Coverage for the signed in user. Safe to call from the admin page."""
    from .. import calibre_db, config, db
    from ..cw_login import current_user
    from .home_rows import _build, _catalog, _representatives, _score, _templates_for

    user_id = int(current_user.id)
    catalog = _catalog(user_id)
    by_id = {book["id"]: book for book in catalog}
    total = int(calibre_db.session.query(db.Books.id).count())
    appearances = {}
    pages = []

    from .units import display_units

    series_members = {}
    for unit in display_units(catalog, user_id):
        if unit.get("kind") == "series":
            series_members[unit["id"]] = list(unit.get("member_ids") or [])

    def add_page(name, path, rows, expand=False):
        seen = []
        rendered = set()
        for row in rows:
            ids = list(row["ids"])
            if row.get("counts", True):
                for book_id in ids:
                    covered = series_members.get(book_id, [book_id]) if expand else [book_id]
                    for covered_id in covered:
                        rendered.add(covered_id)
                        appearances.setdefault(covered_id, []).append("%s / %s" % (name, row["name"]))
            seen.append({
                "name": row["name"],
                "candidates": row.get("candidates"),
                "kept": len(row["ids"]),
                "dropped": row.get("dropped") or [],
                "reasons": row.get("reasons") or [],
                "ids": row["ids"],
            })
        missing = [by_id[book_id]["title"] for book_id in by_id if book_id not in rendered]
        missing.sort()
        pages.append({
            "name": name,
            "path": path,
            "rendered": len(rendered),
            "missing_count": len(missing),
            "missing": missing,
            "rows": seen,
        })

    home_rows, home_funnel = _home(catalog, user_id, _build, _representatives, _score, _templates_for)
    add_page(_("Home"), "/", home_rows, expand=True)
    add_page(_("Genres"), "/genres", _genres_landing(catalog), expand=True)
    for row in _genre_pages(catalog):
        add_page(row["title"], row["path"], row["rows"], expand=True)
    add_page(_("Series"), "/series", _series_landing(catalog))
    for row in _series_pages(catalog):
        add_page(row["title"], row["path"], row["rows"])
    add_page(_("Discover"), "/discover/stored", _discover(catalog), expand=True)
    add_page(_("Login collage"), "/login", _login(catalog))
    lists = _flags(catalog)

    nowhere = []
    busy = []
    for book in catalog:
        places = appearances.get(book["id"]) or []
        if not places:
            nowhere.append(book["title"])
        elif len(places) > 3:
            busy.append({"title": book["title"], "count": len(places), "places": places})
    nowhere.sort()
    busy.sort(key=lambda item: (-item["count"], item["title"].lower()))
    from .accolades import counts
    from .ratings.service import rating_report

    noise_only = sum(1 for book in catalog if not book["tags"])
    from .accolade_sources import accolade_report

    accolade_books, quote_books = counts()
    ratings = rating_report()
    accolades = accolade_report()
    from .series_info import coverage as series_coverage

    series_info = series_coverage()
    log.info(
        "Coverage report: %s in metadata.db, %s visible, %s never rendered on these pages",
        total, len(catalog), len(nowhere),
    )
    if len(nowhere):
        log.warning("Coverage warning: %s visible books are not rendered on any measured page", len(nowhere))
    return {
        "total": total,
        "visible": len(catalog),
        "noise_only": noise_only,
        "accolade_books": accolade_books,
        "quote_books": quote_books,
        "ratings": ratings,
        "accolades": accolades,
        "series_info": series_info,
        "books_per_page": config.config_books_per_page,
        "pages": pages,
        "nowhere": nowhere,
        "busy": busy,
        "lists": lists,
        "limits": LIMITS,
        "generated": datetime.now().strftime("%b %d, %Y %H:%M"),
    }


def _home(catalog, user_id, build, representatives, score, templates_for):
    reps = representatives([dict(book) for book in catalog])
    rep_ids = {item["id"] for item in reps}
    collapsed = [book["title"] for book in catalog if book["id"] not in rep_ids and book["series_id"]]
    built = build(user_id)
    rendered = []
    for row in built:
        rendered.append({
            "name": row["title"],
            "ids": list(row.get("book_ids") or []),
            "candidates": None,
            "dropped": [],
        })
    templates = templates_for(catalog, reps)
    funnel = []
    for template in templates:
        scored = [item for item in reps if score(item, template) >= 60]
        funnel.append({
            "name": "Home template %s" % template["id"],
            "ids": [item["id"] for item in scored],
            "candidates": len(reps),
            "dropped": ["%s of %s representatives scored under 60" % (len(reps) - len(scored), len(reps))],
            "counts": False,
        })
    rendered.insert(0, {
        "name": "Series representatives",
        "ids": [item["id"] for item in reps],
        "candidates": len(catalog),
        "dropped": ["%s series books collapsed to one card before any shelf is filled" % len(collapsed)],
        "counts": False,
    })
    rendered.extend(funnel)
    return rendered, funnel


def _genres_landing(catalog):
    from .browse import _world
    from .genre_rows import landing_report
    from .units import display_units

    _catalog, names = _world()
    return landing_report(display_units(catalog or _catalog), names)


def _genre_pages(catalog):
    from .browse import _world
    from .genre_rows import assign, build_genre_page
    from .units import display_units

    _catalog, names = _world()
    books = display_units(catalog or _catalog)
    buckets, _membership = assign(books, names)
    pages = []
    for bucket in buckets:
        if not bucket["books"]:
            continue
        payload = build_genre_page(bucket["name"], books, names, "added")
        if not payload:
            continue
        rows = []
        for row in payload["rows"]:
            rows.append({
                "name": "%s: %s" % (row.get("label") or "", row["title"]),
                "ids": list(row.get("book_ids") or []),
                "candidates": row.get("count"),
                "dropped": [],
                "reasons": ["%s: %s" % pair for pair in (row.get("reasons") or [])],
            })
        rows.append({
            "name": "All books in this bucket",
            "ids": list(payload["grid"]),
            "candidates": len(payload["grid"]),
            "dropped": [],
        })
        pages.append({
            "title": bucket["name"],
            "path": "/genres/%s" % bucket["name"],
            "rows": rows,
        })
    return pages


def _series_landing(catalog):
    from .browse import _series_cards, _stat_map

    cards = _series_cards(catalog, _stat_map())
    ids = []
    hidden = 0
    for card in cards:
        members = card["members"]
        ids.extend(book["id"] for book in members)
        if len(members) > 3:
            hidden += len(members) - 3
    return [{
        "name": "Series cards",
        "ids": ids,
        "candidates": sum(len(card["members"]) for card in cards),
        "dropped": ["Covers on a series card stop at 3. Every book in that series still counts as shown."] if hidden else [],
    }]


def _series_pages(catalog):
    from .browse import _series_cards, _series_detail, _stat_map

    pages = []
    for card in _series_cards(catalog, _stat_map()):
        series_id = card["public"]["id"]
        payload = _series_detail(series_id)
        if not payload:
            continue
        rows = [{
            "name": "Books in order",
            "ids": list(payload["volumes"]),
            "candidates": len(payload["volumes"]),
            "dropped": [],
        }]
        if payload.get("more"):
            rows.append({
                "name": payload["more"]["title"],
                "ids": list(payload["more"]["book_ids"]),
                "candidates": None,
                "dropped": [],
            })
        pages.append({
            "title": payload["name"],
            "path": "/series/%s" % series_id,
            "rows": rows,
        })
    return pages


def _discover(catalog):
    from .discover_rows import get_plan
    from .home import discover_cards

    try:
        plan = get_plan("coverage", None, [])
    except Exception as error:
        cards = discover_cards(3)
        return [{
            "name": "Featured panel",
            "ids": [card["id"] for card in cards],
            "candidates": len(catalog),
            "dropped": ["row builder stopped with %s, so the rows and the grid do not load" % type(error).__name__],
        }]
    rows = [{
        "name": "Featured panel",
        "ids": [],
        "candidates": 3,
        "dropped": ["three featured books are chosen separately and removed from the rows"],
    }]
    for row in plan["rows"]:
        rows.append({
            "name": row["title"],
            "ids": [item["id"] for item in row["books"]],
            "candidates": None,
            "dropped": [],
        })
    rows.append({
        "name": "Keep exploring",
        "ids": list(plan["grid_ids"]),
        "candidates": plan["total"],
        "dropped": [],
    })
    return rows


def _login(catalog):
    from .login_collage import cover_catalog

    ids = [row["id"] for row in cover_catalog()]
    present = set(ids)
    missing = [book["title"] for book in catalog if book["id"] not in present]
    return [{
        "name": "Cover catalog",
        "ids": ids,
        "candidates": len(catalog),
        "dropped": ["%s books have no usable cover" % len(missing)] if missing else [],
    }]


def _flags(catalog):
    from .flags import favorite_ids, want_ids

    finished = [book["id"] for book in catalog if book["read"] == 1]
    return [
        {"name": "Want to Read", "ids": sorted(want_ids()), "candidates": len(catalog), "dropped": []},
        {"name": "Finished", "ids": finished, "candidates": len(catalog), "dropped": []},
        {"name": "Favorites", "ids": sorted(favorite_ids()), "candidates": len(catalog), "dropped": []},
    ]
