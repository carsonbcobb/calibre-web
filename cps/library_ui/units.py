# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Display units for shelves, heroes, and grids.

A unit is one standalone book, or one series when two or more visible
books share it. A series with a single visible book stays a book card.
"""

import os
from datetime import datetime

_CACHE = {}

def metadata_mtime():
    """mtime of metadata.db, or 0 when the file cannot be read."""
    try:
        from .. import config

        path = os.path.join(config.config_calibre_dir or "", "metadata.db")
        return int(os.path.getmtime(path))
    except Exception:
        return 0


def display_units(catalog, user_id=None):
    """Cached units for this user. Invalid when metadata.db changes."""
    signature = (metadata_mtime(), _signature(catalog))
    cached = _CACHE.get(user_id)
    if cached and cached[0] == signature:
        return [_clone(unit) for unit in cached[1]]
    units = _assemble(catalog or [], _page_counts(), _series_names(catalog))
    _CACHE[user_id] = (signature, units)
    if len(_CACHE) > 24:
        for key in list(_CACHE)[:12]:
            _CACHE.pop(key, None)
    return [_clone(unit) for unit in units]


def clear_unit_cache():
    _CACHE.clear()


def same_series(item, anchor):
    series_id = (anchor or {}).get("series_id")
    return bool(series_id) and (item or {}).get("series_id") == series_id


def series_by_member():
    """Series units keyed by every book id inside the series."""
    from ..cw_login import current_user
    from .home_rows import _catalog

    user_id = int(getattr(current_user, "id", 0) or 0)
    found = {}
    for unit in display_units(_catalog(user_id), user_id):
        if unit.get("kind") != "series":
            continue
        for book_id in unit.get("member_ids") or ():
            found[book_id] = unit
    return found


def unit_index():
    """Series units keyed by the book id the card is built from."""
    from ..cw_login import current_user
    from .home_rows import _catalog

    user_id = int(getattr(current_user, "id", 0) or 0)
    found = {}
    for unit in display_units(_catalog(user_id), user_id):
        if unit.get("kind") == "series":
            found[unit["id"]] = unit
    return found


def decorate_books(books):
    """Mark ORM books that should render as a series card."""
    rows = [book for book in (books or []) if book is not None]
    if not rows:
        return books
    index = unit_index()
    for book in rows:
        unit = index.get(getattr(book, "id", None))
        if unit:
            _stamp(book, unit)
    return books


def _assemble(catalog, pages, series_names):
    groups = {}
    singles = []
    for book in catalog:
        if book.get("series_id"):
            groups.setdefault(book["series_id"], []).append(book)
        else:
            singles.append(_book_unit(book, pages))
    units = []
    for series_id, members in groups.items():
        members = sorted(members, key=lambda entry: entry.get("series_index") or 0)
        if len(members) < 2:
            units.append(_book_unit(members[0], pages))
            continue
        name = series_names.get(series_id) or members[0].get("series_name") or members[0].get("title") or ""
        units.append(_series_unit(series_id, name, members, pages))
    return units + singles


def _book_unit(book, pages):
    item = _copy_fields(book)
    item["kind"] = "book"
    item["member_ids"] = [book["id"]]
    item["member_titles"] = [book.get("title") or ""]
    item["cover_ids"] = [book["id"]]
    item["cover_id"] = book["id"]
    item["count"] = 1
    item["pages"] = int(pages.get(book["id"]) or 0)
    item["finished_count"] = 1 if book.get("read") == 1 else 0
    item["progress"] = 100 if book.get("read") == 1 else 0
    item["next_id"] = book["id"]
    item["next_index"] = book.get("series_index") or 1
    item["next_title"] = book.get("title") or ""
    item["lead_blurb"] = sentence_case(book.get("blurb_text") or "")
    item["count_label"] = ""
    item["hours_label"] = _hours(item.get("minutes"))
    item["meta_line"] = item["hours_label"]
    item["send_note"] = ""
    item["href"] = ""
    item["series_len"] = item.get("series_len") or 1
    item["started"] = book.get("read") in (1, 2)
    item["unread_left"] = book.get("read") != 1
    item["is_first"] = abs(float(book.get("series_index") or 0) - 1) < 0.51 if book.get("series_id") else False
    return item


def _series_unit(series_id, name, members, pages):
    first = members[0]
    item = _copy_fields(first)
    tags = set()
    tag_ids = set()
    author_ids = set()
    pairs = []
    seen_pairs = set()
    labels = []
    seen_labels = set()
    raw_tags = set()
    blurbs = []
    minutes = 0
    page_total = 0
    ratings = []
    rating_counts = []
    moods = []
    newest = first.get("stamp")
    year = None
    for book in members:
        tags.update(book.get("tags") or ())
        tag_ids.update(book.get("tag_ids") or ())
        author_ids.update(book.get("author_ids") or ())
        for pair in book.get("tag_pairs") or ():
            if pair[0] not in seen_pairs:
                seen_pairs.add(pair[0])
                pairs.append(pair)
        for label in book.get("labels") or ():
            if label not in seen_labels:
                seen_labels.add(label)
                labels.append(label)
        raw_tags.update(book.get("raw_tags") or ())
        if book.get("blurb"):
            blurbs.append(book["blurb"])
        if book.get("minutes"):
            minutes += int(book["minutes"])
        page_total += int(pages.get(book["id"]) or 0)
        for mood in book.get("moods") or ():
            if mood not in moods:
                moods.append(mood)
        if book.get("rating") is not None:
            ratings.append(float(book["rating"]))
            if book.get("rating_count"):
                rating_counts.append(int(book["rating_count"]))
        stamp = book.get("stamp")
        if stamp and (newest is None or stamp > newest):
            newest = stamp
        if book.get("year") and (year is None or book["year"] < year):
            year = book["year"]
    unread = [book for book in members if book.get("read") != 1]
    nxt = unread[0] if unread else first
    finished = sum(1 for book in members if book.get("read") == 1)
    started = any(book.get("read") in (1, 2) for book in members)
    count = len(members)
    hours = _hours(minutes)
    count_label = "1 book" if count == 1 else "%s books" % count
    item.update({
        "id": nxt["id"],
        "kind": "series",
        "title": name,
        "series_id": series_id,
        "series_name": name,
        "series_index": nxt.get("series_index") or 1,
        "series_len": count,
        "is_first": abs(float(nxt.get("series_index") or 0) - 1) < 0.51,
        "author_name": first.get("author_name") or "",
        "author_key": first.get("author_key") or "",
        "author_ids": author_ids,
        "tags": tags,
        "tag_ids": tag_ids,
        "tag_pairs": pairs,
        "real_tags": bool(tags),
        "labels": labels,
        "raw_tags": raw_tags,
        "blurb": " ".join(blurbs),
        "lead_blurb": sentence_case(first.get("blurb_text") or ""),
        "search": " ".join(blurbs + list(raw_tags)),
        "minutes": minutes or None,
        "pages": page_total,
        "rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "rating_count": int(round(sum(rating_counts) / len(rating_counts))) if rating_counts else None,
        "rating_source": "Series average" if ratings else "",
        "moods": moods,
        "stamp": newest,
        "fresh_id": max(members, key=lambda book: book.get("stamp") or datetime.min)["id"],
        "year": year,
        "read": nxt.get("read") or 0,
        "read_at": nxt.get("read_at"),
        "started": started,
        "unread_left": bool(unread),
        "member_ids": [book["id"] for book in members],
        "member_titles": [book.get("title") or "" for book in members],
        "cover_ids": [book["id"] for book in members[:3]],
        "cover_id": first["id"],
        "count": count,
        "finished_count": finished,
        "progress": _progress(finished, count, started),
        "next_id": nxt["id"],
        "next_index": nxt.get("series_index") or 1,
        "next_title": nxt.get("title") or "",
        "count_label": count_label,
        "hours_label": hours,
        "meta_line": "%s, %s" % (count_label, hours) if hours else count_label,
        "send_note": "Sends Book %s" % _index_label(nxt.get("series_index")),
        "href": "/series/%s" % series_id,
    })
    return item


def sentence_case(text):
    """Readable description. Mixed case stays, so names are not flattened."""
    text = " ".join((text or "").split())
    if not text:
        return ""
    letters = [char for char in text if char.isalpha()]
    if letters and not any(char.islower() for char in letters):
        text = text.lower()
    chars = list(text)
    start = True
    for index, char in enumerate(chars):
        if start and char.isalpha():
            chars[index] = char.upper()
            start = False
        elif char in ".!?":
            start = True
    return "".join(chars)


def _copy_fields(book):
    return {
        "id": book["id"],
        "title": book.get("title") or "",
        "author_name": book.get("author_name") or "",
        "author_key": book.get("author_key") or "",
        "author_ids": set(book.get("author_ids") or ()),
        "tags": set(book.get("tags") or ()),
        "tag_ids": set(book.get("tag_ids") or ()),
        "tag_pairs": list(book.get("tag_pairs") or ()),
        "real_tags": bool(book.get("real_tags")),
        "series_id": book.get("series_id"),
        "series_name": book.get("series_name") or "",
        "series_index": book.get("series_index") or 0,
        "series_len": book.get("series_len") or 1,
        "started": bool(book.get("started")),
        "unread_left": bool(book.get("unread_left")),
        "is_first": bool(book.get("is_first")),
        "stamp": book.get("stamp"),
        "read": book.get("read") or 0,
        "read_at": book.get("read_at"),
        "minutes": book.get("minutes"),
        "blurb": book.get("blurb") or "",
        "blurb_text": book.get("blurb_text") or "",
        "rating": book.get("rating"),
        "rating_count": book.get("rating_count"),
        "rating_source": book.get("rating_source") or "",
        "moods": list(book.get("moods") or ()),
        "fresh_id": book.get("fresh_id") or book["id"],
        "year": book.get("year"),
        "labels": list(book.get("labels") or ()),
        "raw_tags": set(book.get("raw_tags") or ()),
        "search": book.get("search") or "",
    }


def _clone(unit):
    item = dict(unit)
    item["tags"] = set(unit.get("tags") or ())
    item["tag_ids"] = set(unit.get("tag_ids") or ())
    item["author_ids"] = set(unit.get("author_ids") or ())
    item["raw_tags"] = set(unit.get("raw_tags") or ())
    item["tag_pairs"] = list(unit.get("tag_pairs") or ())
    item["labels"] = list(unit.get("labels") or ())
    item["member_ids"] = list(unit.get("member_ids") or ())
    item["member_titles"] = list(unit.get("member_titles") or ())
    item["cover_ids"] = list(unit.get("cover_ids") or ())
    return item


def _stamp(book, unit):
    from flask import url_for

    from .send import send_choice

    book.library_unit = "series"
    book.library_series_name = unit.get("title") or ""
    book.library_author = unit.get("author_name") or ""
    book.library_href = unit.get("href") or ""
    book.library_cover_ids = list(unit.get("cover_ids") or [])
    book.library_count_label = unit.get("count_label") or ""
    book.library_meta_line = unit.get("meta_line") or ""
    book.library_rating_value = unit.get("rating")
    book.library_rating_count = unit.get("rating_count")
    book.library_rating_source = unit.get("rating_source") or ""
    book.library_rating_label = _rating_label(unit.get("rating"))
    book.library_progress = int(unit.get("progress") or 0)
    book.library_send_title = unit.get("next_title") or ""
    book.library_send_note = unit.get("send_note") or ""
    from .accolades import best_accolade

    book.library_accolade = best_accolade(unit.get("member_ids") or [])
    book.library_blurb = unit.get("lead_blurb") or ""
    book.library_cover_id = unit.get("cover_id") or book.id
    choice = send_choice(book)
    book.library_send_url = ""
    if choice:
        book.library_send_url = url_for(
            "web.send_to_ereader",
            book_id=book.id,
            book_format=choice["format"],
            convert=choice["convert"],
        )


def _page_counts():
    found = {}
    try:
        from .. import ub
        from .models import LibraryBookStat

        for row in ub.session.query(LibraryBookStat).all():
            if row.page_count:
                found[row.book_id] = int(row.page_count)
    except Exception:
        try:
            from .. import ub
            ub.session.rollback()
        except Exception:
            pass
    return found


def _series_names(catalog):
    found = {}
    for book in catalog or []:
        if book.get("series_id") and book.get("series_name"):
            found[book["series_id"]] = book["series_name"]
    missing = {book.get("series_id") for book in catalog or [] if book.get("series_id")} - set(found)
    if not missing:
        return found
    try:
        from .. import calibre_db, db

        for series in calibre_db.session.query(db.Series).filter(db.Series.id.in_(list(missing))).all():
            found[series.id] = series.name or ""
    except Exception:
        pass
    return found


def _signature(catalog):
    rows = []
    for book in catalog or []:
        rows.append((
            book.get("id"),
            book.get("series_id"),
            book.get("read"),
            book.get("minutes"),
            book.get("rating"),
            str(book.get("stamp") or ""),
            book.get("year") or 0,
            1 if book.get("raw_tags") else 0,
        ))
    return tuple(rows)


def _progress(finished, count, started):
    if not count or not started:
        return 0
    if finished:
        return int(round(100.0 * finished / count))
    return max(8, int(round(100.0 / count)))


def reading_time(minutes, whole_hours=False):
    """One reading time string for every hero, card, and series total."""
    try:
        total = int(round(float(minutes or 0)))
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    if whole_hours:
        hours = int(round(total / 60.0))
        if hours <= 0:
            return "%s min" % total
        return "%s hr" % hours
    hours, mins = divmod(total, 60)
    if hours and mins:
        return "%s hr %s min" % (hours, mins)
    if hours:
        return "%s hr" % hours
    return "%s min" % mins


def _hours(minutes):
    return reading_time(minutes, whole_hours=True)


def _rating_label(value):
    if value is None:
        return ""
    return ("%.1f" % float(value)).rstrip("0").rstrip(".")


def _index_label(value):
    try:
        number = float(value or 1)
    except (TypeError, ValueError):
        number = 1
    text = ("%.2f" % number).rstrip("0").rstrip(".")
    return text or "1"
