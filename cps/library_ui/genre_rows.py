# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Genre buckets, playful row titles, and cross genre rows.

Reads the shared catalog. Does not write Calibre metadata.
"""

import random
from datetime import datetime, timedelta

from .genre_config import (
    BUCKETS,
    CROSS_ROWS,
    NATIONALITY_TAGS,
    NOISE_TAGS,
    ROW_MIN,
    ROW_SHOW,
    TAG_BUCKETS,
)

_BUCKET_NAMES = {spec["id"]: spec["name"] for spec in BUCKETS}
_FRESH_DAYS = 90
_SHORT_MINUTES = 8 * 60
_SERIES_MIN = 4


def is_noise(name):
    folded = (name or "").strip().casefold()
    if not folded or folded in NOISE_TAGS or folded in NATIONALITY_TAGS:
        return True
    return folded.endswith(" century")


def bucket_for_tag(name):
    """Bucket id for one raw tag, or an empty string when the tag is ignored."""
    folded = (name or "").strip().casefold()
    if is_noise(folded):
        return ""
    return TAG_BUCKETS.get(folded, "")


def book_bucket_ids(book, names):
    found = []
    for tag_id in book.get("tag_ids") or ():
        bucket_id = bucket_for_tag((names or {}).get(tag_id) or "")
        if bucket_id and bucket_id not in found:
            found.append(bucket_id)
    return found


def book_in_bucket(book, bucket_id, names):
    """True when a chip is All, or the book sits in that bucket. Numeric ids still match a raw tag."""
    if not bucket_id:
        return True
    text = str(bucket_id).strip()
    if not text or text == "0":
        return True
    if text.isdigit():
        return int(text) in (book.get("tag_ids") or ())
    return text in book_bucket_ids(book, names)


def assign(catalog, names):
    """Buckets in config order, plus book id -> bucket ids. Books with no genre stay out."""
    by_id = {}
    order = []
    for spec in BUCKETS:
        bucket = {
            "id": spec["id"],
            "name": spec["name"],
            "adjacent": spec["adjacent"],
            "titles": spec["titles"],
            "books": [],
        }
        by_id[spec["id"]] = bucket
        order.append(bucket)
    membership = {}
    for book in catalog or []:
        found = book_bucket_ids(book, names)
        membership[book["id"]] = found
        for bucket_id in found:
            by_id[bucket_id]["books"].append(book)
    return order, membership


def chip_lists(catalog, names, limit=10):
    chips = _chips(assign(catalog, names)[0])
    return chips[:limit], chips[limit:]


def build_landing(catalog, names, rng=None):
    """Rows for /genres. A new page seed on every call."""
    page_rng = rng or _page_rng()
    buckets, membership = assign(catalog, names)
    sizes = _series_sizes(catalog)
    names = names or {}
    used = set()
    filled = []
    pending = []
    largest_first = sorted(buckets, key=lambda item: (-len(item["books"]), item["name"].lower()))
    for bucket in largest_first:
        row = _bucket_row(bucket, buckets, names, sizes, page_rng, used, False, topup=False)
        if row:
            filled.append(row)
            used.update(row["book_ids"])
        elif bucket["books"]:
            pending.append(bucket)
    for bucket in pending:
        row = _bucket_row(bucket, buckets, names, sizes, page_rng, used, False, topup=True)
        if row:
            filled.append(row)
            used.update(row["book_ids"])
    crosses = []
    specs = [spec for spec in CROSS_ROWS if not spec.get("repeat")]
    page_rng.shuffle(specs)
    for spec in specs:
        if len(crosses) >= 3:
            break
        row = _cross_row(spec, catalog, buckets, membership, names, sizes, page_rng, used)
        if row:
            crosses.append(row)
            used.update(row["book_ids"])
    fresh = next((spec for spec in CROSS_ROWS if spec.get("repeat")), None)
    if fresh:
        row = _cross_row(fresh, catalog, buckets, membership, names, sizes, page_rng, used)
        if row:
            crosses.append(row)
    hero_book, hero_genre = _hero_pick(filled, catalog, page_rng)
    _drop_unit(filled, hero_book)
    return {
        "seed": getattr(page_rng, "seed_value", None),
        "rows": _weave(filled, crosses, page_rng),
        "pills": _chips(buckets),
        "hero_book": hero_book,
        "hero_genre": hero_genre,
        "membership": membership,
        "buckets": buckets,
    }


def build_genre_page(name, catalog, names, sort_mode, rng=None):
    page_rng = rng or _page_rng()
    buckets, _membership = assign(catalog, names)
    bucket = _resolve(name, buckets)
    if bucket is None or not bucket["books"]:
        return None
    sizes = _series_sizes(catalog)
    names = names or {}
    used = set()
    rows = []
    main = _bucket_row(bucket, buckets, names, sizes, page_rng, used, True)
    if main:
        main["href"] = "#genre-grid"
        main["see_all_url"] = "#genre-grid"
        rows.append(main)
        used.update(main["book_ids"])
    for spec in (
        ("start", "Book one", "The first book in a series that lives in this genre"),
        ("alone", "On its own", "No series, no sequel, just this book"),
        ("quick", "Quick reads", "Short enough to finish without clearing a week"),
        ("long", "Long hauls", "Over fifteen hours in this genre"),
        ("prize", "Prize shelf", "Award winners in this genre"),
    ):
        pool = _slice_pool(spec[0], bucket["books"], sizes)
        row_rng = _row_rng(page_rng)
        chosen = _choose(pool, row_rng, used, False, ROW_SHOW)
        if len(chosen) < ROW_MIN:
            continue
        title, subtitle = row_rng.choice(bucket["titles"])
        row = _row(
            spec[0],
            bucket["name"],
            title,
            subtitle if spec[0] == "start" else spec[2],
            len(pool),
            "#genre-grid",
            chosen,
            bucket["id"],
        )
        if spec[0] == "prize":
            row["title"] = "Prize shelf"
            row["subtitle"] = "Award winners in this genre"
        elif spec[0] != "start":
            row["subtitle"] = spec[2]
        rows.append(row)
        used.update(row["book_ids"])
    if rows:
        grid_title = ""
        grid_label = bucket["name"]
        grid_subtitle = ""
    else:
        title, subtitle = _row_rng(page_rng).choice(bucket["titles"])
        grid_title = title
        grid_label = bucket["name"]
        grid_subtitle = subtitle
    hero_book = page_rng.choice(bucket["books"])
    _drop_unit(rows, hero_book)
    grid = [book["id"] for book in _sort_books(bucket["books"], sort_mode) if book["id"] != hero_book["id"]]
    return {
        "name": bucket["name"],
        "id": bucket["id"],
        "hero_book": hero_book,
        "bucket_books": bucket["books"],
        "rows": rows,
        "grid": grid,
        "grid_title": grid_title,
        "grid_label": grid_label,
        "grid_subtitle": grid_subtitle,
        "grid_count": len(grid),
        "pills": _chips(buckets, current=bucket["id"]),
        "sort": sort_mode if sort_mode in ("added", "title", "rating", "length") else "added",
    }


def debug_blocks(catalog, names, rng=None):
    """Same placement the Genres page uses, as title and reason pairs."""
    page = build_landing(catalog, names, rng)
    blocks = [_membership_block(catalog, names, page["membership"], page["buckets"])]
    for row in page["rows"]:
        blocks.append({
            "title": "%s: %s" % (row["label"], row["title"]),
            "template": row["id"],
            "books": [{"title": title, "reason": reason} for title, reason in row["reasons"]],
        })
    return blocks


def landing_report(catalog, names):
    """Coverage rows: which books landed, and why."""
    page = build_landing(catalog, names)
    rows = []
    for row in page["rows"]:
        rows.append({
            "name": "%s: %s" % (row["label"], row["title"]),
            "ids": list(row["book_ids"]),
            "candidates": row["count"],
            "dropped": [],
            "reasons": ["%s: %s" % pair for pair in row["reasons"]],
        })
    shown = {book_id for row in page["rows"] if row["id"] != "fresh" for book_id in row["book_ids"]}
    missed = []
    for book in catalog or []:
        if book["id"] in shown:
            continue
        labels = [bucket["name"] for bucket in page["buckets"] if book["id"] in {item["id"] for item in bucket["books"]}]
        missed.append("%s: %s" % (book["title"], ", ".join(labels) if labels else "No bucket"))
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


def _page_rng():
    seed = random.SystemRandom().randrange(1, 2 ** 31 - 1)
    rng = random.Random(seed)
    rng.seed_value = seed
    return rng


def _row_rng(page_rng):
    return random.Random(page_rng.randrange(1, 2 ** 31 - 1))


def _chips(buckets, current=""):
    chips = []
    for bucket in buckets:
        if not bucket["books"]:
            continue
        chips.append({
            "id": bucket["id"],
            "name": bucket["name"],
            "href": _bucket_href(bucket["name"]),
            "count": len(bucket["books"]),
            "current": bucket["id"] == current,
        })
    chips.sort(key=lambda chip: (-chip["count"], chip["name"].lower()))
    return chips


def _bucket_row(bucket, buckets, names, sizes, page_rng, used, on_page, topup=True):
    if not bucket["books"] and not on_page:
        return None
    row_rng = _row_rng(page_rng)
    pool = []
    for book in bucket["books"]:
        pool.append((book, _tag_reason(book, names, bucket)))
    chosen = _choose(pool, row_rng, used, False, ROW_SHOW)
    extra_reason_books = []
    if len(chosen) < ROW_MIN and topup and not on_page:
        extra = _adjacent_pool(bucket["adjacent"], buckets, names, {book["id"] for book, _reason in chosen})
        chosen = _choose(extra, row_rng, used, False, ROW_MIN, already=chosen)
        extra_reason_books = extra
    if len(chosen) < ROW_MIN:
        return None
    title, subtitle = row_rng.choice(bucket["titles"])
    href = "#genre-grid" if on_page else _bucket_href(bucket["name"])
    count = len({book["id"] for book in bucket["books"]})
    if extra_reason_books and count < ROW_MIN:
        count = len(chosen)
    return _row(bucket["id"], bucket["name"], title, subtitle, count, href, chosen, bucket["id"])


def _cross_row(spec, catalog, buckets, membership, names, sizes, page_rng, used):
    row_rng = _row_rng(page_rng)
    pool = _cross_pool(spec, catalog, membership, names, sizes)
    allow = bool(spec.get("repeat"))
    newest = spec.get("rule") == "fresh"
    chosen = _choose(pool, row_rng, used, allow, ROW_SHOW, shuffle=not newest, prefer="newest" if newest else "first")
    if len(chosen) < ROW_MIN and spec.get("adjacent") and not allow:
        have = {book["id"] for book, _reason in chosen}
        extra = _adjacent_pool(spec["adjacent"], buckets, names, have)
        chosen = _choose(extra, row_rng, used, False, ROW_MIN, already=chosen)
    if len(chosen) < ROW_MIN:
        return None
    title, subtitle = row_rng.choice(spec["titles"])
    href = _see_href(spec.get("see"), buckets)
    count = len({book["id"] for book, _reason in pool}) or len(chosen)
    if spec.get("rule") == "fresh":
        recent = {book["id"] for book, reason in pool if reason.startswith("Added")}
        count = len(recent) or len(chosen)
    if count < len(chosen):
        count = len(chosen)
    return _row(spec["id"], spec["label"], title, subtitle, count, href, chosen, spec["id"])


def _cross_pool(spec, catalog, membership, names, sizes):
    rule = spec.get("rule") or "tags_or_keywords"
    pool = []
    for book in catalog or []:
        reason = _cross_reason(spec, book, membership, names, sizes, rule)
        if reason:
            pool.append((book, reason))
    if rule == "fresh":
        pool.sort(key=lambda pair: _stamp_key(pair[0]), reverse=True)
    return pool


def _cross_reason(spec, book, membership, names, sizes, rule):
    buckets = set(membership.get(book["id"]) or ())
    text = _haystack(book, names)
    keyword = ""
    for word in spec.get("keywords") or ():
        if word and word in text:
            keyword = word
            break
    tag_hit = bool(buckets & set(spec.get("tags") or ()))
    if rule == "short":
        minutes = book.get("minutes")
        if book.get("kind") != "series" and minutes and minutes < _SHORT_MINUTES and (tag_hit or not spec.get("tags")):
            return "Under eight hours"
        return ""
    if rule == "series":
        if book.get("kind") == "series" and int(book.get("count") or book.get("series_len") or 0) >= _SERIES_MIN:
            return "Series has %s books" % int(book.get("count") or book.get("series_len") or 0)
        return ""
    if rule == "standalone":
        return "" if book.get("series_id") else "Not part of a series"
    if rule == "hidden":
        return "" if book.get("rating") is not None else "No rating on file"
    if rule == "fresh":
        if _recent(book):
            return "Added in the last 90 days"
        return "One of the newest books"
    if keyword:
        return "Description mentions %s" % keyword
    if tag_hit:
        labels = [_BUCKET_NAMES[bucket_id] for bucket_id in spec.get("tags") or () if bucket_id in buckets and bucket_id in _BUCKET_NAMES]
        if labels:
            return "In %s" % " and ".join(labels[:2])
        return "Matched a tag on this row"
    return ""


def _slice_pool(kind, books, sizes):
    from .accolades import award_win_ids, has_award

    wins = award_win_ids() if kind == "prize" else set()
    pool = []
    for book in books:
        if kind == "start" and book.get("kind") == "series":
            pool.append((book, "A series you can start"))
        elif kind == "alone" and not book.get("series_id"):
            pool.append((book, "Not part of a series"))
        elif kind == "quick" and book.get("kind") != "series" and book.get("minutes") and book["minutes"] <= 360:
            pool.append((book, "Short enough for a few sittings"))
        elif kind == "long" and book.get("minutes") and book["minutes"] >= 900:
            pool.append((book, "Over fifteen hours"))
        elif kind == "prize" and has_award(book, wins):
            pool.append((book, "Recorded award win"))
    return pool


def _choose(pool, row_rng, used, allow_repeat, limit, shuffle=True, prefer="first", already=None):
    already = list(already or [])
    seen = {book["id"] for book, _reason in already}
    series_seen = {book.get("series_id") for book, _reason in already if book.get("series_id")}
    authors = {}
    for book, _reason in already:
        author = book.get("author_key") or ""
        if author:
            authors[author] = authors.get(author, 0) + 1
    grouped = {}
    for book, reason in pool:
        series_id = book.get("series_id")
        if series_id and series_id in series_seen:
            continue
        if book["id"] in seen:
            continue
        key = series_id or ("solo", book["id"])
        current = grouped.get(key)
        if current is None or _prefer(book, current[0], prefer):
            grouped[key] = (book, reason)
    picks = list(grouped.values())
    if shuffle:
        row_rng.shuffle(picks)
    else:
        picks.sort(key=lambda pair: _stamp_key(pair[0]), reverse=True)
    chosen = list(already)
    for book, reason in picks:
        if book["id"] in seen:
            continue
        if book.get("kind") == "series" and book["id"] in used:
            continue
        if not allow_repeat and book["id"] in used:
            continue
        author = book.get("author_key") or ""
        if author and authors.get(author, 0) >= 2:
            continue
        chosen.append((book, reason))
        seen.add(book["id"])
        if book.get("series_id"):
            series_seen.add(book["series_id"])
        if author:
            authors[author] = authors.get(author, 0) + 1
        if len(chosen) >= limit:
            break
    return chosen


def _adjacent_pool(adjacent_ids, buckets, names, skip_ids):
    by_id = {bucket["id"]: bucket for bucket in buckets}
    pool = []
    for bucket_id in adjacent_ids or ():
        bucket = by_id.get(bucket_id)
        if bucket is None:
            continue
        for book in bucket["books"]:
            if book["id"] in skip_ids:
                continue
            pool.append((book, "Topped up from %s" % bucket["name"]))
    return pool


def _row(row_id, label, title, subtitle, count, href, chosen, bucket_id):
    return {
        "id": row_id,
        "slug": row_id,
        "label": label,
        "title": title,
        "name": label,
        "subtitle": subtitle,
        "count": count,
        "href": href,
        "see_all_url": href,
        "book_ids": [book["id"] for book, _reason in chosen],
        "reasons": [(book["title"], reason) for book, reason in chosen],
        "bucket": bucket_id,
    }


def _weave(buckets, crosses, page_rng):
    ordered = sorted(buckets, key=lambda row: (-row["count"], row["label"].lower()))
    page_rng.shuffle(crosses)
    rows = []
    left = 0
    right = 0
    while left < len(ordered) or right < len(crosses):
        if left < len(ordered):
            rows.append(ordered[left])
            left += 1
        if right < len(crosses):
            rows.append(crosses[right])
            right += 1
    return _split_same_bucket(rows)


def _split_same_bucket(rows):
    if len(rows) < 2:
        return rows
    safe = [rows[0]]
    held = []
    for row in rows[1:]:
        if row.get("bucket") == safe[-1].get("bucket"):
            held.append(row)
            continue
        safe.append(row)
        if held and held[0].get("bucket") != safe[-1].get("bucket"):
            safe.append(held.pop(0))
    safe.extend(held)
    return safe


def _prefer(book, current, prefer):
    if prefer == "newest":
        return _stamp_key(book) > _stamp_key(current)
    return float(book.get("series_index") or 0) < float(current.get("series_index") or 0)


def _drop_unit(rows, book):
    if not book:
        return
    for row in rows or []:
        row["book_ids"] = [book_id for book_id in (row.get("book_ids") or []) if book_id != book["id"]]


def _hero_pick(rows, catalog, page_rng):
    by_id = {book["id"]: book for book in catalog or []}
    bucket_ids = {spec["id"] for spec in BUCKETS}
    options = []
    for row in rows:
        if row.get("bucket") not in bucket_ids:
            continue
        for book_id in row["book_ids"]:
            book = by_id.get(book_id)
            if book is not None:
                options.append((book, row["label"]))
    if not options:
        return None, ""
    return page_rng.choice(options)


def _resolve(name, buckets):
    wanted = (name or "").strip().casefold()
    if not wanted:
        return None
    for bucket in buckets:
        if bucket["id"] == wanted or bucket["name"].casefold() == wanted:
            return bucket
    mapped = bucket_for_tag(wanted)
    if not mapped:
        mapped = bucket_for_tag(wanted.replace("&", " and "))
    for bucket in buckets:
        if bucket["id"] == mapped:
            return bucket
    return None


def _pretty(text):
    cleaned = (text or "").replace("&", " and ").replace("-", " ")
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    return cleaned.strip()


def _tag_reason(book, names, bucket):
    labels = []
    for tag_id in book.get("tag_ids") or ():
        raw = ((names or {}).get(tag_id) or "").strip()
        if bucket_for_tag(raw) == bucket["id"] and raw and raw not in labels:
            labels.append(_pretty(raw))
    if not labels:
        return "In %s" % bucket["name"]
    if len(labels) == 1:
        return "Tag %s maps to %s" % (labels[0], bucket["name"])
    return "Tags %s map to %s" % (" and ".join(labels[:3]), bucket["name"])


def _haystack(book, names):
    tags = " ".join(((names or {}).get(tag_id) or "") for tag_id in (book.get("tag_ids") or ()))
    return ("%s %s" % (book.get("blurb") or "", tags)).casefold()


def _series_sizes(catalog):
    sizes = {}
    for book in catalog or []:
        series_id = book.get("series_id")
        if series_id:
            sizes[series_id] = sizes.get(series_id, 0) + 1
    return sizes


def _membership_block(catalog, names, membership, buckets):
    lookup = {bucket["id"]: bucket["name"] for bucket in buckets}
    books = []
    for book in catalog or []:
        labels = [lookup[bucket_id] for bucket_id in membership.get(book["id"]) or () if bucket_id in lookup]
        books.append({
            "title": book["title"],
            "reason": ", ".join(labels) if labels else "No bucket",
        })
    books.sort(key=lambda item: item["title"].lower())
    return {"title": "Genre buckets", "template": "buckets", "books": books}


def _sort_books(books, mode):
    if mode == "title":
        return sorted(books, key=lambda book: (book.get("title") or "").lower())
    if mode == "rating":
        return sorted(books, key=lambda book: (book.get("rating") is None, -(book.get("rating") or 0)))
    if mode == "length":
        return sorted(books, key=lambda book: (book.get("minutes") is None, -(book.get("minutes") or 0)))
    return sorted(books, key=_stamp_key, reverse=True)


def _stamp_key(book):
    stamp = book.get("stamp")
    if stamp is None:
        return ""
    try:
        if getattr(stamp, "tzinfo", None) is not None:
            stamp = stamp.replace(tzinfo=None)
        return stamp.isoformat()
    except Exception:
        return str(stamp)


def _recent(book):
    stamp = book.get("stamp")
    if stamp is None:
        return False
    try:
        if getattr(stamp, "tzinfo", None) is not None:
            stamp = stamp.replace(tzinfo=None)
        return stamp >= datetime.now() - timedelta(days=_FRESH_DAYS)
    except Exception:
        return False


def _bucket_href(name):
    try:
        from flask import url_for
        return url_for("library_ui.genre_page", name=name)
    except Exception:
        return "/genres/%s" % name


def _see_href(see, buckets):
    if see == "series":
        try:
            from flask import url_for
            return url_for("web.series_list")
        except Exception:
            return "/series"
    if see == "genres" or not see:
        try:
            from flask import url_for
            return url_for("library_ui.genres_home")
        except Exception:
            return "/genres"
    for bucket in buckets:
        if bucket["id"] == see:
            return _bucket_href(bucket["name"])
    return _bucket_href(see)
