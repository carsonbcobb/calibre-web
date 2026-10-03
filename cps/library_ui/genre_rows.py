# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Genre pages. Buckets and row copy come from shelf_config.py."""

from .shelf_config import BUCKETS
from .shelf_config import bucket_for_tag as tag_bucket


def is_noise(name):
    from .shelf_config import NATIONALITY_TAGS, NOISE_TAGS

    folded = (name or "").strip().casefold()
    if not folded or folded in NOISE_TAGS or folded in NATIONALITY_TAGS:
        return True
    return folded.endswith(" century")


def bucket_for_tag(name):
    return tag_bucket(name)


def book_bucket_ids(book, names):
    found = []
    for tag_id in book.get("tag_ids") or ():
        bucket_id = tag_bucket((names or {}).get(tag_id) or "")
        if bucket_id and bucket_id not in found:
            found.append(bucket_id)
    for tag in book.get("raw_tags") or ():
        bucket_id = tag_bucket(tag)
        if bucket_id and bucket_id not in found:
            found.append(bucket_id)
    return found


def book_in_bucket(book, bucket_id, names):
    if not bucket_id:
        return True
    text = str(bucket_id).strip()
    if not text or text == "0":
        return True
    if text.isdigit():
        return int(text) in (book.get("tag_ids") or ())
    return text in book_bucket_ids(book, names)


def assign(catalog, names):
    by_id = {}
    order = []
    for spec in BUCKETS:
        bucket = {
            "id": spec["id"],
            "name": spec["name"],
            "adjacent": spec["adjacent"],
            "label": spec["label"],
            "chip": spec["chip"],
            "books": [],
        }
        by_id[spec["id"]] = bucket
        order.append(bucket)
    membership = {}
    for book in catalog or []:
        found = book_bucket_ids(book, names)
        membership[book["id"]] = found
        for bucket_id in found:
            if bucket_id in by_id:
                by_id[bucket_id]["books"].append(book)
    return order, membership


def chip_lists(catalog, names, limit=10):
    from .shelf_engine import _assign, prepare

    units, tag_names, _catalog = prepare()
    ordered = sorted(
        (bucket for bucket in _assign(units, tag_names) if bucket["chip"] and bucket["books"]),
        key=lambda item: (-len(item["books"]), item["name"].lower()),
    )
    chips = [{
        "id": bucket["id"],
        "name": bucket["name"],
        "href": "/genres/%s" % bucket["name"],
        "count": len(bucket["books"]),
        "current": False,
    } for bucket in ordered]
    return chips, []


def build_landing(catalog, names, rng=None, books=None):
    from .shelf_engine import genre_landing

    page = genre_landing()
    order, membership = assign(page.get("units") or catalog, page.get("names") or names)
    page["buckets"] = order
    page["membership"] = membership
    return page


def build_genre_page(name, catalog, names, sort_mode, rng=None, books=None):
    from .shelf_engine import genre_page

    return genre_page(name, sort_mode)


def debug_blocks(catalog, names, rng=None):
    page = build_landing(catalog, names, rng)
    blocks = []
    for row in page["rows"]:
        blocks.append({
            "title": "%s: %s" % (row.get("label") or "", row["title"]),
            "template": row["id"],
            "books": [{"title": title, "reason": reason, "kind": "book"} for title, reason in row.get("reasons") or []],
        })
    if page.get("dropped"):
        blocks.append({
            "title": "Dropped rows",
            "template": "dropped",
            "books": [{"title": title, "reason": "Fewer than 6 units after top up", "kind": "book"} for title in page["dropped"]],
        })
    return blocks


def landing_report(catalog, names):
    page = build_landing(catalog, names)
    rows = []
    for row in page["rows"]:
        rows.append({
            "name": "%s: %s" % (row.get("label") or "", row["title"]),
            "ids": list(row["book_ids"]),
            "candidates": row["count"],
            "dropped": [],
            "reasons": ["%s: %s" % pair for pair in row.get("reasons") or []],
        })
    if page.get("dropped"):
        rows.append({
            "name": "Dropped rows",
            "ids": [],
            "candidates": len(page["dropped"]),
            "dropped": list(page["dropped"]),
            "reasons": ["%s: Fewer than 6 units after top up" % title for title in page["dropped"]],
        })
    shown = {book_id for row in page["rows"] for book_id in row["book_ids"]}
    missed = []
    for book in catalog or []:
        if book["id"] in shown:
            continue
        labels = [bucket["name"] for bucket in page["buckets"] if book["id"] in {item["id"] for item in bucket["books"]}]
        missed.append("%s: %s" % (book.get("title") or "", ", ".join(labels) if labels else "No bucket"))
    if missed:
        rows.append({
            "name": "Not on a genre row",
            "ids": [],
            "candidates": len(missed),
            "dropped": [],
            "reasons": missed,
            "counts": False,
        })
    return rows
