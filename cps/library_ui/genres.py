# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from urllib.parse import urlencode

from flask import has_request_context, request
from sqlalchemy import func

from .logger_helper import log


def selected_ids():
    if not has_request_context():
        return []
    found = []
    pieces = list(request.args.getlist("genre"))
    packed = request.args.get("genres", "")
    if packed:
        pieces.extend(packed.split(","))
    for piece in pieces:
        for part in str(piece).split(","):
            part = part.strip()
            if part.isdigit():
                found.append(int(part))
    # Keep order, drop duplicates.
    unique = []
    for genre_id in found:
        if genre_id not in unique:
            unique.append(genre_id)
    return unique


def genre_clause():
    ids = selected_ids()
    if not ids:
        return None
    from .. import db
    return db.Books.tags.any(db.Tags.id.in_(ids))


def bar_context():
    empty = {"library_genres": [], "library_genre_clear": ""}
    try:
        if not has_request_context() or request.endpoint != "web.books_list":
            return empty
        selected = set(selected_ids())
        genres = []
        for tag in _popular_tags():
            genres.append({
                "id": tag.id,
                "name": tag.name,
                "selected": tag.id in selected,
                "href": _toggle_url(tag.id, selected),
            })
        return {
            "library_genres": genres,
            "library_genre_clear": _clear_url() if selected else "",
        }
    except Exception as error:
        log.debug("Genre bar unavailable: %s", error)
        return empty


def _popular_tags(limit=40):
    from .. import calibre_db, db
    rows = (calibre_db.session.query(db.Tags)
            .join(db.books_tags_link, db.Tags.id == db.books_tags_link.c.tag)
            .join(db.Books, db.Books.id == db.books_tags_link.c.book)
            .filter(calibre_db.common_filters())
            .group_by(db.Tags.id)
            .order_by(func.count(db.Books.id).desc(), db.Tags.name.asc())
            .limit(limit)
            .all())
    return rows


def _query_without_genres():
    params = []
    for key, values in request.args.lists():
        if key in ("genre", "genres", "page"):
            continue
        for value in values:
            params.append((key, value))
    return params


def _toggle_url(tag_id, selected):
    params = _query_without_genres()
    next_ids = set(selected)
    if tag_id in next_ids:
        next_ids.remove(tag_id)
    else:
        next_ids.add(tag_id)
    for genre_id in sorted(next_ids):
        params.append(("genre", str(genre_id)))
    query = urlencode(params)
    return request.path + (("?" + query) if query else "")


def _clear_url():
    params = _query_without_genres()
    query = urlencode(params)
    return request.path + (("?" + query) if query else "")
