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
    "fantasy": ("science fiction", "adventure", "mythology", "young adult"),
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
    "young adult": "young adult",
    "young adult fiction": "young adult",
    "ya": "young adult",
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
    """Ranked shelves for the current user. Cached for ten minutes."""
    from ..cw_login import current_user

    from .units import metadata_mtime

    skipped = tuple(sorted(int(item) for item in (skip_ids or []) if item))
    key = (
        int(getattr(current_user, "id", 0) or 0),
        str(getattr(current_user, "filter_language", lambda: "all")()),
        metadata_mtime(),
        skipped,
    )
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL:
        return _hydrate(cached[1])
    try:
        payload = _build(key[0], skipped)
    except Exception as error:
        log.debug("Home shelves unavailable: %s", error)
        payload = []
    _CACHE[key] = (now, payload)
    if len(_CACHE) > 24:
        oldest = sorted(_CACHE, key=lambda item: _CACHE[item][0])[:-12]
        for item in oldest:
            _CACHE.pop(item, None)
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
    for slug, title, subtitle in (
        ("fresh", _("Fresh on the shelf"), _("Added to the library most recently")),
        ("continue_series", _("Keep the story going"), _("The next unread book in a series you started")),
    ):
        seen.add(slug)
        rows.append(_editor_item(slug, title, subtitle, overrides.get(slug), False))
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
    catalog = _catalog(user_id)
    if not catalog:
        return []
    overrides = _override_map()
    hidden = {slug for slug, row in overrides.items() if row.hidden}
    rng = random.Random("%s:%s" % (user_id, datetime.now().strftime("%Y%m%d")))
    skipped = {int(item) for item in (skip_ids or []) if item}
    items = [
        item for item in _representatives(catalog)
        if item["id"] not in skipped and not (set(item.get("member_ids") or ()) & skipped)
    ]
    templates = [item for item in _templates_for(catalog, items) if item["id"] not in hidden]
    genre_links = {}
    for item in catalog:
        for tag_id, name in item["tag_pairs"]:
            genre_links.setdefault(name, tag_id)
    for template in templates:
        source = template.get("source")
        if source in genre_links and template["kind"] in ("genre", "mood"):
            template["link"] = {"data": "category", "sort_param": "stored", "book_id": genre_links[source]}
    custom_rows, custom_used = _custom_rows(catalog, items, overrides, hidden)
    exclusive, used = _assign(
        [item for item in items if item["id"] not in custom_used],
        templates,
        rng,
        2,
        _MIN_BOOKS,
    )
    used |= custom_used
    rows = custom_rows + exclusive + _open_rows(items, rng, _MIN_BOOKS, hidden)
    used = _rescue(rows, items, used, templates)
    rows = _fill_page(rows, items, used, rng)
    rows = _apply_overrides(rows, overrides)
    return _arrange(rows, rng)


def _static_templates():
    return [
        _genre("fantasy", _("Lose yourself in another world"), _("Fantasy, and the stories next door"), ("fantasy",), "genre", 0, ("magic", "dragon", "kingdom")),
        _genre("scifi", _("Out there in the stars"), _("Science fiction, and what sits beside it"), ("science fiction",), "genre", 0, ("space",)),
        _genre("dark", _("Can't sleep after this"), _("Horror, thrillers, and uneasy nights"), ("horror", "thriller", "dark fantasy"), "mood", 8, ("dark", "detective")),
        _genre("litrpg", _("Dungeons, levels, and dark humor"), _("LitRPG, with fantasy and humor nearby"), ("litrpg",), "genre", 8),
        _genre("heist", _("Heists, schemes, and clever plans"), _("Plans, cons, and jobs that go sideways"), (), "mood", 12, ("heist",)),
        _genre("apocalypse", _("The end of the world as we know it"), _("Dystopia, collapse, and what comes after"), ("dystopian",), "mood", 8, ("apocalypse", "survival")),
        _genre("classics", _("Timeless and worth the hype"), _("Classics, and books people still pass along"), ("classics",), "genre", 0),
        _pred("new_series", _("Start a new series"), _("Book one, when the series has room to grow"), "discovery", "series", lambda item: item.get("kind") == "series" and not item["started"]),
        _pred("finish_series", _("Finish what you started"), _("You already began these. The rest is waiting"), "discovery", "series", lambda item: item.get("kind") == "series" and item["started"] and item["unread_left"]),
        _pred("standalones", _("Standalones, no commitment"), _("One book, then you are free"), "discovery", "discovery", lambda item: not item["series_id"]),
        _pred("quick", _("Quick reads under 6 hours"), _("Short enough for a single sitting"), "length", "length", lambda item: item.get("kind") != "series" and item["minutes"] and item["minutes"] <= 360),
        _pred("long", _("Big books for long nights"), _("Over fifteen hours"), "length", "length", lambda item: item["minutes"] and item["minutes"] >= 900),
        _pred("gems", _("Hidden gems"), _("Strong books without a huge ratings count"), "discovery", "discovery", lambda item: item["real_tags"] and (item["rating"] is None or (item["rating"] >= 4 and (item["rating_count"] or 0) < 500))),
        _pred("like_author", _("More like a favorite author"), _("Same neighborhood as their other work"), "discovery", "discovery", None),
        _pred("because_finished", _("Because you finished a book"), _("Close to the last book you finished"), "discovery", "discovery", None),
    ]


def _genre(slug, title, subtitle, genres, kind, bonus, keywords=()):
    adjacent = []
    for genre in genres:
        for other in ADJACENCY.get(genre, ()):
            if other not in genres and other not in adjacent:
                adjacent.append(other)
    return {
        "id": slug,
        "title": title,
        "subtitle": subtitle,
        "kind": kind,
        "source": genres[0] if genres else slug,
        "genres": genres,
        "adjacent": tuple(adjacent),
        "keywords": keywords,
        "bonus": bonus,
        "match": None,
        "link": None,
    }


def _pred(slug, title, subtitle, kind, source, match):
    return {
        "id": slug,
        "title": title,
        "subtitle": subtitle,
        "kind": kind,
        "source": source,
        "genres": (),
        "adjacent": (),
        "keywords": (),
        "bonus": 0,
        "match": match,
        "link": None,
    }


def _templates_for(catalog, items):
    templates = _static_templates()
    last = _last_finished(catalog)
    if last is None:
        return [item for item in templates if item["id"] not in ("like_author", "because_finished")]
    author = last["author_key"]
    genres = last["tags"]
    for template in templates:
        if template["id"] == "like_author" and author:
            template["title"] = _("More like %(author)s", author=last["author_name"])
            series_id = last.get("series_id")
            template["match"] = lambda item, author=author, genres=genres, series_id=series_id: (not series_id or item.get("series_id") != series_id) and (item["author_key"] == author or bool(item["tags"] & genres))
        elif template["id"] == "because_finished":
            template["title"] = _("Because you finished %(title)s", title=_short(last["title"]))
            finished_id = last["id"]
            series_id = last.get("series_id")
            template["match"] = lambda item, genres=genres, finished_id=finished_id, series_id=series_id: item["id"] != finished_id and (not series_id or item.get("series_id") != series_id) and bool(item["tags"] & _with_neighbors(genres))
    return templates


def _custom_templates(overrides, hidden):
    found = []
    for saved in overrides.values():
        if saved.slug in hidden or not saved.source_kind or not str(saved.slug).startswith("custom-"):
            continue
        ids = _id_set(saved.source_value)
        found.append({
            "id": saved.slug,
            "title": saved.title or _("A shelf you made"),
            "subtitle": saved.subtitle or _("Chosen for this library"),
            "kind": "custom",
            "source": "custom",
            "genres": (),
            "adjacent": (),
            "keywords": (),
            "bonus": 0,
            "match": None,
            "link": None,
            "custom_kind": saved.source_kind,
            "custom_ids": ids,
        })
    return found


def _assign(items, templates, rng, author_cap, minimum):
    """Put each card on its best shelf. A series is already one card."""
    template_by_id = {template["id"]: template for template in templates}
    options = {}
    for item in items:
        ranked = []
        for template in templates:
            score = _score(item, template)
            if score >= 60:
                ranked.append((score, rng.random(), template["id"]))
        ranked.sort(reverse=True)
        options[item["id"]] = ranked
    claimed = {template["id"]: [] for template in templates}
    authors = {template["id"]: {} for template in templates}
    owner = {}

    def give(item, template_id):
        claimed[template_id].append(item)
        _author_add(authors[template_id], item)
        owner[item["id"]] = template_id

    def take(item):
        template_id = owner.pop(item["id"], None)
        if template_id is None:
            return
        claimed[template_id] = [other for other in claimed[template_id] if other["id"] != item["id"]]
        authors[template_id] = {}
        for other in claimed[template_id]:
            _author_add(authors[template_id], other)

    def preference(template_id):
        count = len(claimed[template_id])
        kind = template_by_id[template_id]["kind"]
        # Finish one shelf before opening another, so a tie does not leave every shelf short.
        return (
            0 if count < minimum else 1,
            -(count if count < minimum else 0),
            0 if kind in ("genre", "mood") else 1,
            rng.random(),
        )

    def choose(item, window, limit):
        ranked = options.get(item["id"]) or []
        if not ranked:
            return None
        best = ranked[0][0]
        found = []
        for score, _roll, template_id in ranked:
            if score < best - window:
                break
            if template_id in closed:
                continue
            if len(claimed[template_id]) >= limit:
                continue
            if not _author_ok(authors[template_id], item, author_cap):
                continue
            found.append(template_id)
        if not found:
            return None
        found.sort(key=preference)
        return found[0]

    closed = set()
    for template_id in (
        "dark", "litrpg", "apocalypse", "heist",
        "fantasy", "scifi", "classics",
        "long", "quick", "new_series", "finish_series", "standalones",
    ):
        if template_id not in claimed:
            continue
        matches = []
        for item in items:
            if item["id"] in owner:
                continue
            ranked = options.get(item["id"]) or []
            if not ranked:
                continue
            best = ranked[0][0]
            for score, _roll, tid in ranked:
                if tid != template_id:
                    continue
                if score >= 60 and score >= best - 15:
                    matches.append((score, rng.random(), item))
                break
        matches.sort(reverse=True)
        for _score_value, _roll, item in matches:
            if len(claimed[template_id]) >= minimum:
                break
            if not _author_ok(authors[template_id], item, author_cap):
                continue
            give(item, template_id)
        if len(claimed[template_id]) < minimum:
            for item in list(claimed[template_id]):
                take(item)
            closed.add(template_id)

    ordered = sorted(
        items,
        key=lambda item: (-(options[item["id"]][0][0] if options[item["id"]] else 0), rng.random()),
    )
    pending = []
    for item in ordered:
        if item["id"] in owner:
            continue
        template_id = choose(item, 0, _MAIN_TARGET)
        if template_id:
            give(item, template_id)
        else:
            pending.append(item)
    for item in pending:
        template_id = choose(item, 15, _MAIN_TARGET) or choose(item, 15, _MAX_BOOKS)
        if template_id:
            give(item, template_id)

    unassigned = [item for item in items if item["id"] not in owner]
    rng.shuffle(unassigned)
    for template in templates:
        template_id = template["id"]
        if len(claimed[template_id]) >= _MAIN_TARGET or not template.get("adjacent"):
            continue
        for item in list(unassigned):
            if len(claimed[template_id]) >= _MAIN_TARGET:
                break
            if item["id"] in owner or not _adjacent_hit(item, template):
                continue
            if not _author_ok(authors[template_id], item, author_cap):
                continue
            give(item, template_id)

    rows = []
    for template in templates:
        bucket = claimed[template["id"]]
        if len(bucket) < minimum:
            for item in bucket:
                owner.pop(item["id"], None)
            continue
        rng.shuffle(bucket)
        rows.append(_pack(template, bucket[:_MAX_BOOKS]))
    return rows, set(owner)


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


def _rescue(rows, items, used, templates):
    """Move a leftover card onto a shelf that already fits it."""
    by_id = {item["id"]: item for item in items}
    homes = {row["id"]: row for row in rows}
    for item in items:
        if item["id"] in used:
            continue
        ranked = []
        global_best = 0
        for template in templates:
            score = _score(item, template)
            if score > global_best:
                global_best = score
            if template["id"] in homes and score >= 60:
                ranked.append((score, template["id"]))
        if not ranked:
            continue
        ranked.sort(reverse=True)
        for score, template_id in ranked:
            if score < global_best - 15:
                continue
            row = homes[template_id]
            if str(row["id"]).startswith("custom-") or len(row["book_ids"]) >= _MAX_BOOKS:
                continue
            authors = {}
            for book_id in row["book_ids"]:
                other = by_id.get(book_id)
                if other is not None:
                    _author_add(authors, other)
            if not _author_ok(authors, item, 2):
                continue
            row["book_ids"].append(item["id"])
            if item["series_len"] > 1:
                row.setdefault("counts", {})[item["id"]] = item["series_len"]
            used.add(item["id"])
            break
    return used


def _open_rows(items, rng, minimum, hidden):
    rows = []
    if "fresh" not in hidden:
        fresh = []
        for item in _fresh(items)[:_MAX_BOOKS]:
            card = dict(item)
            card["id"] = item.get("fresh_id") or item["id"]
            fresh.append(card)
        fresh = _author_limited_items(fresh, 2)
        if len(fresh) >= minimum:
            rng.shuffle(fresh)
            rows.append(_pack({
                "id": "fresh",
                "title": _("Fresh on the shelf"),
                "subtitle": _("Added to the library most recently"),
                "kind": "recent",
                "source": "recent",
                "link": {"data": "newest", "sort_param": "stored"},
            }, fresh))
    if "continue_series" not in hidden:
        ongoing = [item for item in items if item.get("kind") == "series" and item["started"] and item["unread_left"]]
        ongoing = _author_limited_items(ongoing, 2)
        if len(ongoing) >= minimum:
            rng.shuffle(ongoing)
            rows.append(_pack({
                "id": "continue_series",
                "title": _("Keep the story going"),
                "subtitle": _("The next unread book in a series you started"),
                "kind": "discovery",
                "source": "continue",
                "link": None,
            }, ongoing[:_MAX_BOOKS]))
    return rows


def _fill_page(rows, items, used, rng):
    """Keep at least six shelves. Extra cards come off the longest shelves first."""
    by_id = {item["id"]: item for item in items}
    used = set(used)
    guard = 0
    while len(rows) < 6 and guard < 8:
        guard += 1
        need = 6 - len(rows)
        pool_ids = [item["id"] for item in items if item["id"] not in used]
        rng.shuffle(pool_ids)
        if len(pool_ids) < need * _MIN_BOOKS:
            donors = []
            for floor in (_MAIN_TARGET, _MIN_BOOKS):
                donors = [
                    row for row in rows
                    if row["id"] not in ("fresh", "continue_series")
                    and not str(row["id"]).startswith("fallback")
                    and not str(row["id"]).startswith("custom-")
                    and len(row["book_ids"]) > floor
                ]
                if donors:
                    break
            donors.sort(key=lambda row: len(row["book_ids"]), reverse=True)
            for donor in donors:
                floor = _MAIN_TARGET if len(donor["book_ids"]) > _MAIN_TARGET else _MIN_BOOKS
                spare = len(donor["book_ids"]) - floor
                take_n = min(spare, need * _MIN_BOOKS - len(pool_ids))
                if take_n <= 0:
                    continue
                harvested = donor["book_ids"][-take_n:]
                donor["book_ids"] = donor["book_ids"][:-take_n]
                counts = donor.get("counts") or {}
                for book_id in harvested:
                    counts.pop(book_id, None)
                    used.discard(book_id)
                    pool_ids.append(book_id)
                if len(pool_ids) >= need * _MIN_BOOKS:
                    break
        if len(pool_ids) < _MIN_BOOKS:
            break
        need = 6 - len(rows)
        reserve = max(0, (need - 1) * _MIN_BOOKS)
        size = min(_MAX_BOOKS, len(pool_ids) - reserve)
        if size < _MIN_BOOKS:
            break
        chunk_ids = _author_limited(pool_ids, by_id, size, 2)
        if len(chunk_ids) < _MIN_BOOKS:
            chunk_ids = pool_ids[:size]
        bucket = [by_id[book_id] for book_id in chunk_ids if book_id in by_id]
        if len(bucket) < _MIN_BOOKS:
            break
        for item in bucket:
            used.add(item["id"])
        rows.append(_pack({
            "id": "fallback-%s" % sum(1 for row in rows if str(row["id"]).startswith("fallback")),
            "title": _("Worth a look"),
            "subtitle": _("A mix from the rest of the shelf"),
            "kind": "discovery",
            "source": "fallback",
            "link": None,
        }, bucket))
    return rows


def _author_limited_items(items, cap):
    chosen = []
    counts = {}
    for item in items:
        if not _author_ok(counts, item, cap):
            continue
        chosen.append(item)
        _author_add(counts, item)
    return chosen


def _author_limited(ids, by_id, size, cap):
    chosen = []
    counts = {}
    for book_id in ids:
        item = by_id.get(book_id)
        if item is None or not _author_ok(counts, item, cap):
            continue
        chosen.append(book_id)
        _author_add(counts, item)
        if len(chosen) >= size:
            break
    return chosen


def _chunks(items, rng, minimum, title, subtitle):
    if len(items) < minimum:
        return []
    rng.shuffle(items)
    rows = []
    index = 0
    while len(items) - index >= minimum and len(rows) < 3:
        chunk = items[index:index + _MAX_BOOKS]
        index += len(chunk)
        if len(chunk) < minimum:
            break
        rows.append(_pack({
            "id": "fallback-%s" % len(rows),
            "title": title,
            "subtitle": subtitle,
            "kind": "discovery",
            "source": "fallback",
            "link": None,
        }, chunk))
    return rows


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
    folded = (name or "").strip().casefold()
    if not folded or folded in NOISE_TAGS:
        return ""
    return ALIASES.get(folded, folded)


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
