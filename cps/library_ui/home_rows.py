# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Home shelf generator.

A book lands in one shelf, except Fresh on the shelf and Keep the story going.
A series is one card. The map and the keyword lists at the top are the edit point.
"""

import random
import re
import time
from datetime import datetime

from flask import url_for
from flask_babel import gettext as _

from .logger_helper import log
from .reading import WORDS_PER_MINUTE

_CACHE = {}
_TTL = 600
_MIN_BOOKS = 6
_MAX_BOOKS = 20
_MAIN_TARGET = 12
_EXACT = 100
_ADJACENT = 45
_KEYWORD = 30

# Tags that are too broad to define a shelf.
NOISE_TAGS = {
    "fiction",
    "general",
    "general fiction",
    "novel",
    "novels",
    "books",
    "ebook",
    "ebooks",
    "kindle",
    "adult",
}

# Canonical genre -> neighbors used only to top up a short shelf.
ADJACENCY = {
    "fantasy": ("science fiction", "adventure", "mythology"),
    "science fiction": ("fantasy", "thriller", "dystopian", "adventure"),
    "horror": ("thriller", "mystery", "dark fantasy"),
    "thriller": ("mystery", "crime", "horror", "science fiction"),
    "mystery": ("crime", "thriller", "historical fiction"),
    "classics": ("literary fiction", "historical fiction", "adventure"),
    "historical fiction": ("classics", "literary fiction", "adventure"),
    "litrpg": ("fantasy", "science fiction", "adventure", "comedy"),
    "dystopian": ("science fiction", "literary fiction", "thriller"),
}

# Loose tags in this library, folded onto the canonical names above.
ALIASES = {
    "sci fi": "science fiction",
    "scifi": "science fiction",
    "sf": "science fiction",
    "hard science fiction": "science fiction",
    "space opera": "science fiction",
    "historical": "historical fiction",
    "history": "historical fiction",
    "myth": "mythology",
    "mythology": "mythology",
    "folklore & mythology": "mythology",
    "fairy tales; folk tales; legends & mythology": "mythology",
    "humour": "comedy",
    "humor": "comedy",
    "humorous": "comedy",
    "dark humor": "comedy",
    "lit rpg": "litrpg",
    "litrpg (literary role-playing game)": "litrpg",
    "thrillers": "thriller",
    "suspense": "thriller",
    "crime & mystery": "crime",
    "literary": "literary fiction",
    "action & adventure": "adventure",
    "action and adventure": "adventure",
    "epic": "fantasy",
    "dark fantasy": "dark fantasy",
    "apocalyptic": "dystopian",
    "apocalyptic & post-apocalyptic": "dystopian",
    "dystopian": "dystopian",
}

# Words in a description. Values are phrases to look for, including the forms
# that already exist in publisher blurbs.
KEYWORDS = {
    "dragon": ("dragon", "drake"),
    "heist": ("heist", "con artist", "robbery", "scheme"),
    "space": ("space", "starship", "galaxy", "planet"),
    "detective": ("detective", "inspector", "whodunit", "murder"),
    "apocalypse": ("apocalypse", "post-apocalyptic", "end of the world", "wasteland"),
    "kingdom": ("kingdom", "throne", "realm"),
    "war": ("war", "battle", "soldier"),
    "magic": ("magic", "wizard", "spell", "witch"),
    "survival": ("survival", "survive", "stranded"),
    "dark": ("nightmare", "haunted", "blood", "terror"),
}


def page_rows(skip_ids=None):
    """Ranked shelves for the current user. A new mix on every load."""
    from ..cw_login import current_user

    user_id = int(getattr(current_user, "id", 0) or 0)
    try:
        payload = _build(user_id, skip_ids or ())
    except Exception as error:
        log.debug("Home shelves unavailable: %s", error)
        payload = []
    return _hydrate(payload)


def clear_home_cache():
    _CACHE.clear()


def editor_rows():
    """Builtin and custom shelves for the admin screen, including hidden ones."""
    overrides = _override_map()
    rows = []
    seen = set()
    for template in _static_templates():
        seen.add(template["id"])
        rows.append(_editor_item(template["id"], template["title"], template["subtitle"], overrides.get(template["id"]), False))
    for saved in overrides.values():
        if saved.slug in seen:
            continue
        rows.append(_editor_item(
            saved.slug,
            saved.title or _("A shelf you made"),
            saved.subtitle or "",
            saved,
            True,
        ))
    rows.sort(key=lambda item: (not item["pinned"], item["sort_order"], item["title"]))
    return rows


def save_override(slug, title, subtitle, pinned, hidden, sort_order):
    row = _get_or_create(slug)
    row.title = (title or "").strip()
    row.subtitle = (subtitle or "").strip()
    row.pinned = bool(pinned)
    row.hidden = bool(hidden)
    try:
        row.sort_order = int(sort_order or 0)
    except (TypeError, ValueError):
        row.sort_order = 0
    _commit()
    clear_home_cache()


def create_custom(title, subtitle, source_kind, source_name):
    kind = (source_kind or "").strip()
    if kind not in ("tag", "author", "series", "books"):
        return False
    ids = _resolve_ids(kind, source_name)
    if not ids:
        return False
    from .. import ub
    from .models import LibraryHomeRow

    row = LibraryHomeRow(
        slug="custom-new",
        title=(title or "").strip() or _("A shelf you made"),
        subtitle=(subtitle or "").strip(),
        source_kind=kind,
        source_value=",".join(str(item) for item in ids),
        pinned=True,
        sort_order=0,
    )
    ub.session.add(row)
    _commit()
    row.slug = "custom-%s" % row.id
    _commit()
    clear_home_cache()
    return True


def delete_custom(slug):
    if not str(slug).startswith("custom-"):
        return
    from .. import ub
    from .models import LibraryHomeRow

    row = ub.session.query(LibraryHomeRow).filter(LibraryHomeRow.slug == slug).one_or_none()
    if row is None:
        return
    ub.session.delete(row)
    _commit()
    clear_home_cache()


def _build(user_id, skip_ids=()):
    from .shelf_engine import home_payload

    catalog = _catalog(user_id)
    if not catalog:
        return []
    rows, plan = home_payload(user_id, skip_ids)
    if plan.get("dropped"):
        rows.append({
            "id": "dropped",
            "title": "Dropped rows",
            "subtitle": "",
            "label": "",
            "book_ids": [],
            "counts": {},
            "reasons": [(title, "Fewer than 6 units passed every gate") for title in plan["dropped"]],
            "kind": "discovery",
            "source": "dropped",
            "link": None,
            "pinned": False,
            "sort_order": 0,
        })
    overrides = _override_map()
    hidden = {slug for slug, row in overrides.items() if row.hidden}
    rows = _apply_overrides(rows, overrides)
    custom_rows, _used = _custom_rows(catalog, catalog, overrides, hidden)
    return rows + custom_rows


def _static_templates():
    from .shelf_config import ROWS

    return [
        {"id": row["id"], "title": row["title"], "subtitle": row["subtitle"]}
        for row in ROWS
        if "home" in row["where"]
    ]


def _templates_for(catalog, items):
    return []


def _custom_rows(catalog, reps, overrides, hidden):
    """Shelves an admin built. A series shelf lists that series in order."""
    rows = []
    used = set()
    for saved in overrides.values():
        if not str(saved.slug).startswith("custom-") or saved.slug in hidden or not saved.source_kind:
            continue
        ids = _id_set(saved.source_value)
        if not ids:
            continue
        kind = saved.source_kind
        if kind in ("series", "books"):
            matched = [item for item in catalog if _custom_match(item, kind, ids)]
            if kind == "series":
                matched.sort(key=lambda item: (item["series_index"], item["title"]))
            else:
                order = []
                for piece in (saved.source_value or "").split(","):
                    piece = piece.strip()
                    if piece.isdigit():
                        order.append(int(piece))
                position = {book_id: index for index, book_id in enumerate(order)}
                matched.sort(key=lambda item: position.get(item["id"], 999))
            bucket = []
            for item in matched[:_MAX_BOOKS]:
                card = dict(item)
                card["series_len"] = 1
                bucket.append(card)
                used.add(item["id"])
        else:
            bucket = [item for item in reps if _custom_match(item, kind, ids)][:_MAX_BOOKS]
            for item in bucket:
                used.add(item["id"])
        if not bucket:
            continue
        packed = _pack({
            "id": saved.slug,
            "title": saved.title or _("A shelf you made"),
            "subtitle": saved.subtitle or _("Chosen for this library"),
            "kind": "custom",
            "source": "custom",
            "link": None,
        }, bucket)
        packed["pinned"] = bool(saved.pinned)
        packed["sort_order"] = saved.sort_order or 0
        rows.append(packed)
    return rows, used


def _custom_match(item, kind, ids):
    if kind == "tag":
        return bool(item["tag_ids"] & ids)
    if kind == "author":
        return bool(item["author_ids"] & ids)
    if kind == "series":
        return item["series_id"] in ids
    return item["id"] in ids


def _pack(template, bucket):
    counts = {}
    ids = []
    for item in bucket:
        ids.append(item["id"])
        if item["series_len"] > 1:
            counts[item["id"]] = item["series_len"]
    return {
        "id": template["id"],
        "title": template["title"],
        "subtitle": template["subtitle"],
        "kind": template["kind"],
        "source": template.get("source") or template["id"],
        "link": template.get("link"),
        "book_ids": ids,
        "counts": counts,
        "pinned": False,
        "sort_order": 0,
    }


def _score(item, template):
    if template.get("custom_ids"):
        return 160 if _custom_hit(item, template) else 0
    score = 0
    if _exact(item, template):
        score += _EXACT
    else:
        hits = _keyword_hits(item, template.get("keywords") or ())
        if hits:
            score += 60 + _KEYWORD * (min(hits, 2) - 1)
    if score and template.get("bonus"):
        score += template["bonus"]
    match = template.get("match")
    if match is not None and match(item):
        floor = 62 if template["id"] == "gems" else 100
        score = max(score, floor)
    if template["id"] == "classics" and item["rating"] is not None and item["rating"] >= 4:
        score = max(score, 70)
    return score


def _exact(item, template):
    return bool(item["tags"] & set(template.get("genres") or ()))


def _adjacent_hit(item, template):
    return bool(item["tags"] & set(template.get("adjacent") or ()))


def _keyword_hits(item, names):
    if not names or not item["blurb"]:
        return 0
    hits = 0
    for name in names:
        for phrase in KEYWORDS.get(name, ()):
            if phrase in item["blurb"]:
                hits += 1
                break
    return hits


def _custom_hit(item, template):
    ids = template["custom_ids"]
    kind = template.get("custom_kind")
    if kind == "tag":
        return bool(item["tag_ids"] & ids)
    if kind == "author":
        return bool(item["author_ids"] & ids)
    if kind == "series":
        return item["series_id"] in ids
    return item["id"] in ids


def _author_ok(counts, item, cap):
    key = item["author_key"]
    if not key:
        return True
    return counts.get(key, 0) < cap


def _author_add(counts, item):
    key = item["author_key"]
    if key:
        counts[key] = counts.get(key, 0) + 1


def _with_neighbors(genres):
    found = set(genres)
    for genre in genres:
        found.update(ADJACENCY.get(genre, ()))
    return found


def _representatives(catalog):
    from .units import display_units

    return display_units(catalog)


def _fresh(items):
    ranked = sorted(items, key=lambda item: item["stamp"] or datetime.min, reverse=True)
    return ranked


def _last_finished(catalog):
    finished = [item for item in catalog if item["read"] == 1 and item["read_at"] is not None]
    if not finished:
        return None
    finished.sort(key=lambda item: item["read_at"], reverse=True)
    return finished[0]


def _catalog(user_id):
    from .. import calibre_db, db, ub

    books = (calibre_db.session.query(db.Books)
             .filter(calibre_db.common_filters())
             .all())
    reads = {}
    if user_id:
        for row in ub.session.query(ub.ReadBook).filter(ub.ReadBook.user_id == int(user_id)).all():
            reads[row.book_id] = row
    words = {}
    ratings = {}
    moods = {}
    try:
        from .models import HardcoverBook, LibraryBookStat
        from .ratings.service import best_rating_map
        for row in ub.session.query(LibraryBookStat).all():
            words[row.book_id] = row.word_count
        ratings = best_rating_map()
        for row in ub.session.query(HardcoverBook).all():
            if row.error:
                continue
            moods[row.book_id] = _json_list(row.moods)
    except Exception:
        ub.session.rollback()
    items = []
    for book in books:
        tags = set()
        tag_ids = set()
        for tag in book.tags or []:
            tag_ids.add(tag.id)
            name = _canonical(tag.name)
            if name:
                tags.add(name)
        authors = []
        author_ids = set()
        for author in book.authors or []:
            author_ids.add(author.id)
            authors.append((author.name or "").replace("|", ", "))
        series_id = None
        series_index = 0.0
        if book.series:
            series_id = book.series[0].id
            try:
                series_index = float(book.series_index or 0)
            except (TypeError, ValueError):
                series_index = 0.0
        read = reads.get(book.id)
        visible = _visible(" ".join((comment.text or "") for comment in (book.comments or [])))
        blurb = visible.casefold()
        minutes = None
        if words.get(book.id):
            minutes = max(1, int(round(float(words[book.id]) / WORDS_PER_MINUTE)))
        rating = ratings.get(book.id)
        items.append({
            "id": book.id,
            "title": book.title or "",
            "author_name": authors[0] if authors else "",
            "author_key": authors[0].casefold() if authors else "",
            "author_ids": author_ids,
            "tags": tags,
            "tag_ids": tag_ids,
            "tag_pairs": [(tag.id, _canonical(tag.name)) for tag in (book.tags or []) if _canonical(tag.name)],
            "real_tags": bool(tags),
            "series_id": series_id,
            "series_index": series_index,
            "series_len": 1,
            "started": False,
            "unread_left": False,
            "is_first": abs(series_index - 1) < 0.51 if series_id else False,
            "stamp": book.timestamp,
            "read": read.read_status if read is not None else 0,
            "read_at": read.last_modified if read is not None else None,
            "minutes": minutes,
            "blurb": blurb,
            "blurb_text": visible,
            "rating": rating["value"] if rating else None,
            "rating_count": rating["count"] if rating else None,
            "rating_source": rating["source"] if rating else "",
            "moods": moods.get(book.id) or [],
            "fresh_id": book.id,
        })
    return items


def _canonical(name):
    from .shelf_config import bucket_name_for_tag

    return bucket_name_for_tag(name).casefold()


def _plain(value):
    return _visible(value).casefold()


def _visible(value):
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _json_list(text):
    import json
    try:
        value = json.loads(text or "[]")
    except ValueError:
        return []
    return value if isinstance(value, list) else []


def _five_star(value):
    number = float(value)
    if number > 5:
        number = number / 2.0
    return round(number, 1)


def _short(title):
    title = title or ""
    if len(title) <= 42:
        return title
    return title[:41].rstrip() + "..."


def _hydrate(payload):
    if not payload:
        return []
    from .. import calibre_db, db

    ids = [book_id for row in payload for book_id in (row.get("book_ids") or [])]
    books = calibre_db.session.query(db.Books).filter(db.Books.id.in_(ids)).all() if ids else []
    by_id = {book.id: book for book in books}
    rows = []
    for row in payload:
        try:
            chosen = []
            for book_id in row.get("book_ids") or []:
                book = by_id.get(book_id)
                if book is None:
                    continue
                count = (row.get("counts") or {}).get(book_id)
                if count and count > 1:
                    book.library_series_count = count
                chosen.append(book)
            from .units import decorate_books
            decorate_books(chosen)
            if not chosen:
                continue
            href = ""
            link = row.get("link")
            if link:
                try:
                    href = url_for("web.books_list", **link)
                except Exception:
                    href = ""
            title = row.get("title") or row.get("name") or row.get("genre") or ""
            if not title:
                continue
            rows.append({
                "id": row.get("id") or "",
                "title": title,
                "subtitle": row.get("subtitle") or "",
                "label": row.get("label") or "",
                "cover_only": bool(row.get("cover_only")),
                "books": chosen,
                "href": href,
            })
        except Exception as error:
            log.error("Home row skipped: %s (%s)", row.get("id") if isinstance(row, dict) else row, error)
    return rows


def _apply_overrides(rows, overrides):
    for row in rows:
        saved = overrides.get(row["id"])
        if saved is None:
            continue
        if saved.title:
            row["title"] = saved.title
        if saved.subtitle:
            row["subtitle"] = saved.subtitle
        row["pinned"] = bool(saved.pinned)
        row["sort_order"] = saved.sort_order or 0
    return [row for row in rows if not (overrides.get(row["id"]) and overrides[row["id"]].hidden)]


def _arrange(rows, rng):
    pinned = [row for row in rows if row.get("pinned")]
    rest = [row for row in rows if not row.get("pinned")]
    pinned.sort(key=lambda row: (row.get("sort_order") or 0, row.get("title") or ""))
    mixed = _mix(rest, rng)
    return _separate(pinned + mixed)


def _mix(rows, rng):
    buckets = {}
    for row in rows:
        buckets.setdefault(row["kind"], []).append(row)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    kinds = list(buckets)
    rng.shuffle(kinds)
    mixed = []
    while any(buckets.values()):
        for kind in list(kinds):
            bucket = buckets.get(kind) or []
            if bucket:
                mixed.append(bucket.pop())
    return mixed


def _separate(rows):
    for _pass in range(len(rows) * 2):
        moved = False
        for index in range(len(rows) - 1):
            if not rows[index]["source"] or rows[index]["source"] != rows[index + 1]["source"]:
                continue
            for later in range(index + 2, len(rows)):
                if rows[later].get("pinned"):
                    continue
                if rows[later]["source"] != rows[index]["source"]:
                    rows[index + 1], rows[later] = rows[later], rows[index + 1]
                    moved = True
                    break
        if not moved:
            break
    return rows


def _override_map():
    from .. import ub
    from .models import LibraryHomeRow

    try:
        rows = ub.session.query(LibraryHomeRow).all()
    except Exception:
        ub.session.rollback()
        return {}
    return {row.slug: row for row in rows}


def _editor_item(slug, title, subtitle, saved, custom):
    return {
        "slug": slug,
        "title": (saved.title if saved and saved.title else title),
        "subtitle": (saved.subtitle if saved and saved.subtitle else subtitle),
        "default_title": title,
        "pinned": bool(saved.pinned) if saved else False,
        "hidden": bool(saved.hidden) if saved else False,
        "sort_order": saved.sort_order if saved else 0,
        "custom": custom,
    }


def _get_or_create(slug):
    from .. import ub
    from .models import LibraryHomeRow

    row = ub.session.query(LibraryHomeRow).filter(LibraryHomeRow.slug == slug).one_or_none()
    if row is None:
        row = LibraryHomeRow(slug=slug)
        ub.session.add(row)
    return row


def _commit():
    from .. import ub

    ub.session_commit("Library home shelf updated")


def _resolve_ids(kind, text):
    from .. import calibre_db, db

    raw = (text or "").strip()
    if not raw:
        return []
    if kind == "books":
        found = []
        for piece in raw.split(","):
            piece = piece.strip()
            if not piece:
                continue
            if piece.isdigit():
                found.append(int(piece))
                continue
            book = (calibre_db.session.query(db.Books)
                    .filter(db.Books.title.ilike(piece))
                    .first())
            if book is not None:
                found.append(book.id)
        return found
    if raw.isdigit():
        return [int(raw)]
    if kind == "tag":
        row = calibre_db.session.query(db.Tags).filter(db.Tags.name.ilike(raw)).first()
    elif kind == "author":
        row = calibre_db.session.query(db.Authors).filter(db.Authors.name.ilike(raw)).first()
    else:
        row = calibre_db.session.query(db.Series).filter(db.Series.name.ilike(raw)).first()
    return [row.id] if row is not None else []


def _id_set(value):
    found = set()
    for piece in (value or "").split(","):
        piece = piece.strip()
        if piece.isdigit():
            found.add(int(piece))
    return found
