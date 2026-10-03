# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Discover page. Rows come from discover_rows. The grid walks every allowed book."""

import random

from flask import abort, jsonify, request
from flask_babel import gettext as _

from .browse import _world
from .discover_rows import get_plan, log_scope
from .home import discover_cards
from .logger_helper import log


def render_discover_page():
    from .. import constants
    from ..cw_login import current_user
    from ..render_template import render_title_template

    if not current_user.check_visibility(constants.SIDEBAR_RANDOM):
        abort(404)
    log_scope()
    cards = discover_cards(3)
    featured, extra = _genre_chips()
    debug = request.args.get("debug") == "1" and current_user.role_admin()
    genre_debug = _genre_debug() if debug else []
    seed = _seed()
    panel = [card["id"] for card in cards]
    plan = _safe_plan(seed, None, panel)
    ready_rows, later_rows, grid_books, shown, total = _first_paint(plan)
    return render_title_template(
        "library_discover.html",
        title=_("Discover"),
        page="discover",
        discover_cards=cards,
        featured_genres=featured,
        extra_genres=extra,
        discover_seed=seed,
        discover_exclude=panel,
        discover_debug=debug,
        genre_debug=genre_debug,
        plan_debug=plan.get("debug") if debug else [],
        discover_rows=ready_rows,
        discover_later=later_rows,
        discover_grid=grid_books,
        discover_shown=shown,
        discover_total=total,
        discover_grid_offset=len(grid_books),
        discover_grid_count=len(plan.get("grid_ids") or []),
    )


def shelf_response():
    from .. import constants
    from ..cw_login import current_user
    from ..render_template import themed_render

    if current_user.is_anonymous or not current_user.check_visibility(constants.SIDEBAR_RANDOM):
        abort(404)
    kind = (request.form.get("kind") or "").strip()
    seed = (request.form.get("seed") or "discover")[:40]
    genre_id = _genre_id(request.form.get("genre"))
    panel = _id_list(request.form.get("panel") or request.form.get("exclude"))
    plan = _safe_plan(seed, genre_id, panel)
    debug = request.form.get("debug") == "1" and current_user.role_admin()
    if kind == "plan":
        payload = {
            "rows": [{"key": row["template"], "title": row["title"]} for row in plan["rows"]],
            "total": plan["total"],
            "counted": plan["counted"],
            "grid_count": len(plan["grid_ids"]),
        }
        if debug:
            payload["debug_html"] = themed_render("library_discover_debug.html", blocks=plan["debug"])
        return jsonify(payload)
    if kind == "more":
        offset = _offset(request.form.get("offset"))
        chunk = plan["grid_ids"][offset:offset + 24]
        books = _load_books(chunk)
        html = themed_render("library_discover_more.html", books=books) if books else ""
        return jsonify({
            "title": _("Keep exploring"),
            "ids": chunk,
            "html": html,
            "done": offset + len(chunk) >= len(plan["grid_ids"]),
            "total": plan["total"],
        })
    row = plan["by_id"].get(kind)
    if not row:
        return jsonify({"title": "", "ids": [], "html": ""})
    books = _load_books([item["id"] for item in row["books"]])
    lanes = _lanes(row.get("lanes"))
    html = themed_render(
        "library_discover_shelf.html",
        title=row["title"],
        subtitle=row["subtitle"],
        label=row.get("label") or "",
        books=books,
        row_id="discover-%s" % kind,
        cover_only=row.get("cover_only"),
        lanes=lanes,
    ) if (books or lanes) else ""
    return jsonify({
        "title": row["title"],
        "ids": [item["id"] for item in row["books"]],
        "html": html,
    })


def _safe_plan(seed, genre_id, panel):
    """Row plan for this chip. A chip that matches nothing falls back to the whole library."""
    try:
        plan = get_plan(seed, genre_id, panel)
        if genre_id and not plan.get("total"):
            plan = get_plan(seed, None, panel)
        return plan
    except Exception as error:
        log.exception("Discover plan failed: %s", error)
        from .units import display_units

        catalog, _names = _world()
        catalog = display_units(catalog)
        ids = [book["id"] for book in catalog]
        random.Random("%s:fallback" % seed).shuffle(ids)
        return {
            "rows": [],
            "by_id": {},
            "grid_ids": ids,
            "counted": list(panel or []),
            "total": len(catalog),
            "debug": [],
        }


def _first_paint(plan):
    rows = plan.get("rows") or []
    views = []
    seen = set(plan.get("counted") or [])
    for row in rows[:6]:
        books = _load_books([item["id"] for item in row.get("books") or []])
        if not books and not row.get("lanes"):
            continue
        for book in books:
            seen.add(book.id)
        from ..render_template import themed_render

        views.append({
            "key": row["template"],
            "html": themed_render(
                "library_discover_shelf.html",
                title=row["title"],
                subtitle=row.get("subtitle") or "",
                label=row.get("label") or "",
                books=books,
                row_id="discover-%s" % row["template"],
                cover_only=row.get("cover_only"),
                lanes=_lanes(row.get("lanes")),
            ),
        })
    grid_books = _load_books((plan.get("grid_ids") or [])[:24])
    for book in grid_books:
        seen.add(book.id)
    later = [{"key": row["template"]} for row in rows[6:]]
    return views, later, grid_books, len(seen), int(plan.get("total") or 0)


def _genre_chips():
    from .genre_rows import chip_lists

    catalog, names = _world()
    return chip_lists(catalog, names)


def _genre_debug():
    from .genre_rows import debug_blocks

    catalog, names = _world()
    return debug_blocks(catalog, names)


def _lanes(lanes):
    ready = []
    for lane in lanes or []:
        ready.append({
            "name": lane["name"],
            "href": lane["href"],
            "books": _load_books(lane["ids"]),
        })
    return ready


def _load_books(ids):
    from .. import calibre_db, db

    if not ids:
        return []
    books = (calibre_db.session.query(db.Books)
             .filter(db.Books.id.in_(ids))
             .filter(calibre_db.common_filters())
             .all())
    order = {book_id: index for index, book_id in enumerate(ids)}
    books.sort(key=lambda book: order.get(book.id, len(ids)))
    from .units import decorate_books
    return decorate_books(books)


def _seed():
    import secrets
    return secrets.token_hex(4)


def _genre_id(value):
    text = (value or "").strip()
    if not text or text == "0" or text.lower() == "all":
        return None
    return text


def _offset(value):
    text = (value or "").strip()
    if text.isdigit():
        return int(text)
    return 0


def _id_list(value):
    found = []
    for piece in (value or "").split(","):
        piece = piece.strip()
        if piece.isdigit():
            found.append(int(piece))
    return found
