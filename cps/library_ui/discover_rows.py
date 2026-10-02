# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Discover row templates.

Edit ROW_TEMPLATES to change a row. title, subtitle, tags, keywords,
minutes (min, max), years (min, max), min_books, and take are the knobs.
minutes and years use None for an open end. The upper minute bound is
exclusive, so (None, 300) means under five hours. Year bounds are inclusive.
"""

import random
import re
from datetime import datetime

from flask import url_for
from flask_babel import gettext as _

from .home_rows import ADJACENCY, _canonical
from .logger_helper import log

# One row definition. rule selects the matcher. type keeps neighbors apart.
ROW_TEMPLATES = (
    {"id": "stacks", "type": "format", "rule": "stacks", "title": "Pulled from the stacks",
     "subtitle": "Later volumes from series already on the shelf",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 8},
    {"id": "start_new", "type": "format", "rule": "book1", "title": "Start something new",
     "subtitle": "Book 1 of a series you have not started",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 8},
    {"id": "short_sweet", "type": "format", "rule": "minutes", "title": "Short and sweet",
     "subtitle": "Under six hours",
     "tags": (), "keywords": (), "minutes": (None, 360), "years": (None, None), "min_books": 8, "take": 8},
    {"id": "something_big", "type": "format", "rule": "minutes", "title": "Something big",
     "subtitle": "Long enough to get lost in",
     "tags": (), "keywords": (), "minutes": (600, None), "years": (None, None), "min_books": 8, "take": 8},
    {"id": "gems", "type": "wildcard", "rule": "gems", "title": "Hidden gems",
     "subtitle": "No rating yet, still worth a look",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 8},
    {"id": "never", "type": "personal", "rule": "unread", "title": "Never opened",
     "subtitle": "On the shelf, not started",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 8},
    {"id": "cant_sleep", "type": "mood", "rule": "tags", "title": "Can't sleep after this",
     "subtitle": "Horror, thrillers, and the dark corners",
     "tags": ("horror", "thriller", "dark fantasy"), "keywords": ("nightmare", "haunted", "terror", "blood"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "brain_candy", "type": "mood", "rule": "tags", "title": "Brain candy",
     "subtitle": "Fast, funny, and easy to fall into",
     "tags": ("comedy", "humor", "humorous", "litrpg", "adventure"), "keywords": ("funny", "humor", "adventure"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "villains", "type": "mood", "rule": "tags", "title": "Villains with a point",
     "subtitle": "Antiheroes, revenge, and a point of view",
     "tags": ("dark fantasy",), "keywords": ("villain", "antihero", "revenge"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "found_family", "type": "mood", "rule": "tags", "title": "Found family energy",
     "subtitle": "Crews, companions, and people who stay",
     "tags": ("family life",), "keywords": ("found family", "companion", "crew", "friend"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "heists", "type": "mood", "rule": "tags", "title": "Heists, schemes, and clever plans",
     "subtitle": "Cons, schemes, and plans with too many steps",
     "tags": ("crime", "espionage"), "keywords": ("heist", "con artist", "scheme", "conspiracy", "robbery"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "apocalypse", "type": "mood", "rule": "tags", "title": "The end of the world, but make it interesting",
     "subtitle": "Collapse, survival, and what people do next",
     "tags": ("dystopian", "apocalyptic", "apocalyptic & post-apocalyptic"),
     "keywords": ("apocalypse", "wasteland", "survival", "collapse"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "space_personal", "type": "mood", "rule": "tags", "title": "Space but make it personal",
     "subtitle": "First contact, colonies, and people in the middle",
     "tags": ("space opera", "alien contact", "space exploration", "science fiction"),
     "keywords": ("colony", "first contact", "starship", "alien"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "swords", "type": "mood", "rule": "tags", "title": "Swords and sorcery",
     "subtitle": "Quests, kingdoms, and choices that go wrong",
     "tags": ("fantasy", "epic", "adventure"), "keywords": ("kingdom", "quest", "sword", "throne"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "twists", "type": "mood", "rule": "tags", "title": "Plot twists you will not see coming",
     "subtitle": "Secrets, betrayals, and the turn you missed",
     "tags": ("thriller", "mystery", "psychological"), "keywords": ("twist", "secret", "betrayal", "truth"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "cozy", "type": "mood", "rule": "tags", "title": "Cozy up with these",
     "subtitle": "Gentle stories for a quiet night",
     "tags": ("small town & rural", "contemporary"), "keywords": ("small town", "comfort", "gentle", "slow"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "weird", "type": "mood", "rule": "tags", "title": "Weird and wonderful",
     "subtitle": "Strange, surreal, and hard to explain",
     "tags": ("magical realism", "steampunk"), "keywords": ("strange", "surreal", "experimental", "speculative"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "smart_dangerous", "type": "mood", "rule": "tags", "title": "Smart and a little dangerous",
     "subtitle": "Hard science, clever machines, and big questions",
     "tags": ("hard science fiction", "technological", "androids; robots & artificial intelligences"),
     "keywords": ("artificial intelligence", "android", "philosophy", "technology"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "dragons", "type": "mood", "rule": "tags", "title": "Dragons, obviously",
     "subtitle": "Scales, fire, and the people who bargain with them",
     "tags": ("dragons & mythical creatures", "fantasy"), "keywords": ("dragon", "drake"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "war_thrones", "type": "mood", "rule": "tags", "title": "War, thrones, and loyalty",
     "subtitle": "Battles, crowns, and the cost of picking a side",
     "tags": ("military", "epic"), "keywords": ("war", "battle", "throne", "soldier"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "mystery_pulse", "type": "mood", "rule": "tags", "title": "Mystery with a pulse",
     "subtitle": "Crimes, questions, and a reason to keep the light on",
     "tags": ("mystery", "crime", "crime & mystery", "thriller"), "keywords": ("detective", "murder", "whodunit"),
     "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "one_sitting", "type": "format", "rule": "minutes", "title": "Done in one sitting",
     "subtitle": "Under five hours, start to finish",
     "tags": (), "keywords": (), "minutes": (None, 300), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "couch", "type": "format", "rule": "minutes", "title": "Bring snacks, you are not leaving the couch",
     "subtitle": "Over fifteen hours, so settle in",
     "tags": (), "keywords": (), "minutes": (900, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "standalones", "type": "format", "rule": "standalone", "title": "Standalones no commitment",
     "subtitle": "One book, then you are free",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "acclaimed", "type": "format", "rule": "accolade", "title": "Award winners and acclaimed reads",
     "subtitle": "Books with a recorded award win",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "book_ones", "type": "format", "rule": "book1", "title": "Book 1s worth the hype",
     "subtitle": "First books of a series with at least three books you have not started",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "binge", "type": "format", "rule": "binge", "title": "Series you can binge right now",
     "subtitle": "Sets of three to six books, starting at book 1",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "short_feelings", "type": "format", "rule": "rated_short", "title": "Short books, big feelings",
     "subtitle": "Under eight hours, and four stars or better when a rating exists",
     "tags": (), "keywords": (), "minutes": (None, 480), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "classics", "type": "time", "rule": "year", "title": "Classics that still hit",
     "subtitle": "Published before 1980",
     "tags": ("classics",), "keywords": (), "minutes": (None, None), "years": (None, 1979), "min_books": 8, "take": 12},
    {"id": "fresh", "type": "time", "rule": "recent", "title": "Fresh off the press",
     "subtitle": "Published in the last two years",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "decade", "type": "time", "rule": "decade", "title": "From the {decade}",
     "subtitle": "Ten years of books, chosen at random",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "era", "type": "time", "rule": "era", "title": "A different era",
     "subtitle": "Published far from the years you usually finish",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "because", "type": "personal", "rule": "because", "title": "Because you finished {book}",
     "subtitle": "Same tags and neighboring genres as that book",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "favorite", "type": "personal", "rule": "favorite", "title": "More like your Favorites",
     "subtitle": "In the orbit of a book you marked as a favorite",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "author", "type": "personal", "rule": "author", "title": "Another book from an author you read",
     "subtitle": "Other titles from an author you already finished",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "ignored", "type": "personal", "rule": "ignored", "title": "Your most ignored genre",
     "subtitle": "{genre} is the shelf you have barely touched",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "waiting", "type": "personal", "rule": "want", "title": "Added to your Want to Read, still waiting",
     "subtitle": "Oldest first, still sitting on the list",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "fast_funny", "type": "format", "rule": "moods", "title": "Fast paced and funny",
     "subtitle": "Hardcover moods that lean quick and comic",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12,
     "moods": ("fast", "funny")},
    {"id": "dark_grip", "type": "format", "rule": "moods", "title": "Dark and gripping",
     "subtitle": "Hardcover moods that lean dark",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12,
     "moods": ("dark", "grim")},
    {"id": "loved", "type": "personal", "rule": "loved", "title": "Loved by other readers here",
     "subtitle": "The books people here have favorited most",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "covers", "type": "wildcard", "rule": "covers", "title": "Judge a book by its cover",
     "subtitle": "No titles until you hover",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "wildcard", "type": "wildcard", "rule": "wildcard", "title": "Wildcard genre",
     "subtitle": "A turn through {genre}",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
    {"id": "dice", "type": "wildcard", "rule": "dice", "title": "Roll the dice",
     "subtitle": "Fifteen books, no agenda",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 15},
    {"id": "lanes", "type": "wildcard", "rule": "lanes", "title": "Pick a lane",
     "subtitle": "Three genres side by side",
     "tags": (), "keywords": (), "minutes": (None, None), "years": (None, None), "min_books": 8, "take": 12},
)

_BY_ID = {row["id"]: row for row in ROW_TEMPLATES}
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

    user_id = int(current_user.id) if current_user.is_authenticated else 0
    seed = (seed or "discover")[:40]
    genre_key = str(genre_id).strip() if genre_id else ""
    if genre_key.isdigit() and int(genre_key) == 0:
        genre_key = ""
    from .units import metadata_mtime

    panel_key = tuple(int(book_id) for book_id in panel_ids)
    key = (user_id, seed, genre_key, panel_key, metadata_mtime())
    cached = _PLANS.get(key)
    if cached:
        return cached
    catalog, names, raw = _prepare()
    base_key = (user_id, seed, "", panel_key, metadata_mtime())
    if genre_key and base_key in _PLANS:
        order = [row["template"] for row in _PLANS[base_key]["rows"]]
    elif genre_key:
        base = _build(catalog, seed, None, panel_ids, names, None, raw)
        _PLANS[base_key] = base
        order = [row["template"] for row in base["rows"]]
    else:
        order = None
    plan = _build(catalog, seed, genre_id, panel_ids, names, order, raw)
    _PLANS[key] = plan
    if len(_PLANS) > 40:
        for old in list(_PLANS)[:20]:
            _PLANS.pop(old, None)
    return plan


def _build(catalog, seed, genre_id, panel_ids, names, only_ids, raw=None):
    from .genre_rows import book_in_bucket

    filtered = [book for book in catalog if book_in_bucket(book, genre_id, names)]
    by_id = {book["id"]: book for book in filtered}
    panel = [book_id for book_id in panel_ids if book_id in by_id]
    rng = random.Random("%s:%s" % (seed, genre_id or "all"))
    ctx = _context(raw or catalog, filtered)
    templates = [_BY_ID[item] for item in only_ids if item in _BY_ID] if only_ids else list(ROW_TEMPLATES)
    if not only_ids:
        rng.shuffle(templates)
        templates.sort(key=lambda item: 0 if item["type"] == "personal" else 1)
    rows = _place_rows(templates, filtered, rng, set(), ctx, names)
    used = set(panel)
    for row in rows:
        used.update(item["id"] for item in row["books"])
    grid = [book["id"] for book in filtered if book["id"] not in used]
    random.Random("%s:grid:%s" % (seed, genre_id or "all")).shuffle(grid)
    debug = _debug_blocks(rows, grid, by_id, panel, names)
    return {
        "rows": rows,
        "by_id": {row["template"]: row for row in rows},
        "grid_ids": grid,
        "counted": panel,
        "total": len(filtered),
        "debug": debug,
    }


def _place_rows(templates, books, rng, used, ctx, names):
    available = max(0, len(books) - len(used))
    target = min(12, available // 8)
    if target >= 12:
        target = rng.randint(10, 12)
    elif target >= 10:
        target = rng.randint(10, target)
    queue = list(templates)
    personal = [item for item in queue if item["type"] == "personal"]
    if personal and (not queue or queue[0]["type"] != "personal"):
        queue = [personal[0]] + [item for item in queue if item is not personal[0]]
    rows = []
    deferred = []
    guard = 0
    while queue and len(rows) < target and guard < 80:
        guard += 1
        template = queue.pop(0)
        if rows and template["type"] == rows[-1].get("type") and queue:
            deferred.append(template)
            continue
        placed = _safe_place(template, books, rng, used, ctx, names, target - len(rows))
        if not placed:
            continue
        rows.append(placed)
        for item in placed["books"]:
            used.add(item["id"])
        if deferred:
            queue = deferred + queue
            deferred = []
    for template in deferred:
        if len(rows) >= target:
            break
        if rows and template["type"] == rows[-1].get("type"):
            continue
        placed = _safe_place(template, books, rng, used, ctx, names, target - len(rows))
        if not placed:
            continue
        rows.append(placed)
        for item in placed["books"]:
            used.add(item["id"])
    for fallback_id in ("dice", "covers", "unread", "gems"):
        if len(rows) >= 6:
            break
        if any(row.get("template") == fallback_id for row in rows):
            continue
        template = _BY_ID.get(fallback_id)
        if not template:
            continue
        placed = _safe_place(template, books, rng, used, ctx, names, 1)
        if not placed:
            continue
        rows.append(placed)
        for item in placed["books"]:
            used.add(item["id"])
    return rows


def _safe_place(template, books, rng, used, ctx, names, rows_still):
    try:
        free = sum(1 for book in books if book["id"] not in used)
        floor = int(template.get("min_books") or 8)
        ceiling = int(template.get("take") or floor)
        limit = floor if rows_still > 1 and free < ceiling * rows_still else ceiling
        return _place(template, books, rng, used, ctx, names, limit)
    except Exception as error:
        log.exception("Discover row %s skipped: %s", template.get("id"), error)
        return None


def _place(template, books, rng, used, ctx, names, limit=None):
    primary, allow_topup, title_bits, cover_only, lanes = _rule_pool(template, books, rng, used, ctx, names)
    if primary is None:
        return None
    cap = int(limit or template.get("take") or 12)
    state = {"ids": set(), "series": set(), "authors": {}}
    chosen = _constrain(primary, cap, used, state, rng, template.get("rule") not in ("want", "loved"))
    if allow_topup and len(chosen) < cap:
        chosen.extend(_top_up(chosen, books, template, used, state, rng, cap - len(chosen)))
    if lanes is None and len(chosen) < int(template.get("min_books") or 8):
        return None
    if lanes is not None and sum(len(lane["ids"]) for lane in lanes) < int(template.get("min_books") or 8):
        return None
    books_out = [_placed(book, reason) for book, reason in chosen]
    if lanes is not None:
        books_out = []
        unit_by_id = {book["id"]: book for book in books}
        for lane in lanes:
            for book_id, reason in lane["pairs"]:
                book = unit_by_id.get(book_id) or ctx["by_id"].get(book_id)
                books_out.append(_placed(book or {"id": book_id, "title": ""}, reason))
    title = _text(template["title"], title_bits)
    subtitle = _text(template["subtitle"], title_bits)
    return {
        "template": template["id"],
        "type": template.get("type") or "",
        "title": title,
        "subtitle": subtitle,
        "cover_only": cover_only,
        "lanes": lanes,
        "books": books_out,
    }


def _rule_pool(template, books, rng, used, ctx, names):
    rule = template["rule"]
    free = [book for book in books if book["id"] not in used]
    if rule == "tags":
        pool = [(book, _tag_reason(book, template)) for book in free if _tag_reason(book, template)]
        return pool, True, {}, False, None
    if rule == "minutes":
        lo, hi = template["minutes"] or (None, None)
        short = hi is not None
        pool = [(book, _("Fits the length")) for book in free if _minutes_ok(book, template["minutes"]) and (not short or book.get("kind") != "series")]
        return pool, True, {}, False, None
    if rule == "year":
        pool = [(book, _("Fits the years")) for book in free if _year_ok(book, template["years"])]
        return pool, True, {}, False, None
    if rule == "recent":
        start = datetime.now().year - 2
        pool = [(book, _("Published in the last two years")) for book in free if book.get("year") and book["year"] >= start]
        return pool, True, {}, False, None
    if rule == "standalone":
        pool = [(book, _("Not part of a series")) for book in free if not book["series_id"]]
        return pool, True, {}, False, None
    if rule == "accolade":
        wins = ctx.get("award_wins") or set()
        pool = [(book, _("Recorded award win")) for book in free if _has_award(book, wins)]
        return pool, True, {}, False, None
    if rule == "moods":
        pool = [(book, _("Hardcover mood match")) for book in free if _mood_hit(book, template.get("moods") or ())]
        return pool, True, {}, False, None
    if rule == "book1":
        pool = [(book, _("A series you have not started")) for book in free if book.get("kind") == "series" and _is_fresh_opener(book, ctx)]
        return pool, True, {}, False, None
    if rule == "binge":
        pool = [(book, _("A series with three to six books")) for book in free if book.get("kind") == "series" and _is_binge(book)]
        return pool, True, {}, False, None
    if rule == "rated_short":
        pool = [(book, _("Short, and highly rated when a rating exists")) for book in free if _short_feeling(book)]
        return pool, True, {}, False, None
    if rule == "decade":
        return _decade_pool(free, rng)
    if rule == "era":
        return _era_pool(free, ctx)
    if rule == "because":
        return _because_pool(free, ctx)
    if rule == "favorite":
        return _favorite_pool(free, rng, ctx)
    if rule == "author":
        return _author_pool(free, rng, ctx)
    if rule == "ignored":
        return _ignored_pool(free, ctx)
    if rule == "want":
        return _want_pool(free, ctx)
    if rule == "loved":
        return _loved_pool(free, ctx)
    if rule == "stacks":
        pool = [(book, _("Later in a series already on the shelf")) for book in free
                if book.get("series_id") and float(book.get("series_index") or 0) >= 1.5]
        return pool, True, {}, False, None
    if rule == "gems":
        pool = [(book, _("No rating stored yet")) for book in free if not book.get("rating")]
        return pool, True, {}, False, None
    if rule == "unread":
        pool = [(book, _("Not opened yet")) for book in free if book.get("read") not in (1, 2)]
        return pool, True, {}, False, None
    if rule == "covers":
        pool = [(book, _("Picked for the cover")) for book in free]
        return pool, False, {}, True, None
    if rule == "dice":
        pool = [(book, _("Rolled at random")) for book in free]
        return pool, False, {}, False, None
    if rule == "wildcard":
        return _wildcard_pool(free, rng)
    if rule == "lanes":
        lanes = _lane_pool(free, rng, names)
        if not lanes:
            return [], False, {}, False, None
        return [], False, {}, False, lanes
    return [], False, {}, False, None


def _decade_pool(books, rng):
    groups = {}
    for book in books:
        year = book.get("year")
        if not year:
            continue
        start = (int(year) // 10) * 10
        groups.setdefault(start, []).append(book)
    options = [start for start, group in groups.items() if len(group) >= 4]
    if not options:
        return None, False, {}, False, None
    start = rng.choice(options)
    label = "%ss" % start
    pool = [(book, _("Published in the %(decade)s", decade=label)) for book in groups[start]]
    return pool, True, {"decade": label}, False, None


def _era_pool(books, ctx):
    finished_years = [book["year"] for book in ctx["finished"] if book.get("year")]
    if not finished_years:
        return None, False, {}, False, None
    center = sum(finished_years) / float(len(finished_years))
    groups = {}
    for book in books:
        year = book.get("year")
        if not year:
            continue
        start = (int(year) // 10) * 10
        groups.setdefault(start, []).append(book)
    if not groups:
        return None, False, {}, False, None
    start = max(groups, key=lambda item: abs(((item + 5) - center)))
    pool = [(book, _("Published far from the years you finish")) for book in groups[start]]
    return pool, True, {}, False, None


def _has_award(book, wins):
    from .accolades import has_award

    return has_award(book, wins)


def _same_series(book, anchor):
    series_id = (anchor or {}).get("series_id")
    return bool(series_id) and book.get("series_id") == series_id


def _because_pool(books, ctx):
    anchor = ctx["last_finished"]
    if anchor is None:
        return None, False, {}, False, None
    neighbors = _neighbors(anchor["tags"])
    pool = []
    for book in books:
        if book["id"] == anchor["id"] or _same_series(book, anchor):
            continue
        if book["tags"] & anchor["tags"]:
            pool.append((book, _("Shares a tag with %(title)s", title=anchor["title"])))
        elif book["tags"] & neighbors:
            pool.append((book, _("Neighboring genre to %(title)s", title=anchor["title"])))
    return pool, True, {"book": anchor["title"]}, False, None


def _favorite_pool(books, rng, ctx):
    anchors = [book for book in ctx["catalog"] if book["id"] in ctx["favorite_ids"]]
    if not anchors:
        return None, False, {}, False, None
    anchor = rng.choice(anchors)
    neighbors = _neighbors(anchor["tags"])
    pool = []
    for book in books:
        if book["id"] == anchor["id"] or _same_series(book, anchor):
            continue
        if book["tags"] & anchor["tags"]:
            pool.append((book, _("Shares a tag with %(title)s", title=anchor["title"])))
        elif book["tags"] & neighbors:
            pool.append((book, _("Neighboring genre to %(title)s", title=anchor["title"])))
    return pool, True, {"book": anchor["title"]}, False, None


def _author_pool(books, rng, ctx):
    authors = {}
    for book in ctx["finished"]:
        if book["author_key"]:
            authors.setdefault(book["author_key"], book["author_name"])
    if not authors:
        return None, False, {}, False, None
    key = rng.choice(list(authors))
    name = authors[key]
    pool = [(book, _("Another title by %(author)s", author=name)) for book in books if book["author_key"] == key and book["read"] != 1]
    return pool, True, {"author": name}, False, None


def _ignored_pool(books, ctx):
    if not ctx["finished"] and not ctx["want_ids"]:
        return None, False, {}, False, None
    touched = {book["id"] for book in ctx["finished"]} | set(ctx["want_ids"])
    counts = {}
    for book in ctx["catalog"]:
        for label, canon in book["labels"]:
            bucket = counts.setdefault(canon, {"name": label, "books": 0, "touched": 0})
            bucket["books"] += 1
            if book["id"] in touched:
                bucket["touched"] += 1
    options = [item for item in counts.values() if item["books"] >= 8]
    if not options:
        return None, False, {}, False, None
    options.sort(key=lambda item: (item["touched"], -item["books"], item["name"].lower()))
    chosen = options[0]
    canon = None
    for key, item in counts.items():
        if item is chosen:
            canon = key
            break
    pool = [(book, _("In %(genre)s, a genre you rarely mark", genre=chosen["name"])) for book in books if canon in book["tags"]]
    return pool, True, {"genre": chosen["name"]}, False, None


def _want_pool(books, ctx):
    if not ctx["want_order"]:
        return None, False, {}, False, None
    wanted = set(ctx["want_order"])
    pool = []
    seen = set()
    for book in books:
        members = set(book.get("member_ids") or ())
        if book["id"] in wanted or members & wanted:
            if book["id"] in seen:
                continue
            seen.add(book["id"])
            pool.append((book, _("Still on your Want to Read list")))
    return pool, True, {}, False, None


def _mood_hit(book, wanted):
    text = " ".join(book.get("moods") or ()).casefold()
    if not text or not wanted:
        return False
    if wanted[0] not in text:
        return False
    if wanted[0] == "dark":
        return any(word in text for word in ("grip", "grim", "tense", "intense", "bleak", "unsettling"))
    return len(wanted) > 1 and wanted[1] in text


def _loved_pool(books, ctx):
    def _love(book):
        ids = book.get("member_ids") or [book["id"]]
        return sum((ctx.get("love_counts") or {}).get(book_id, 0) for book_id in ids)

    pool = []
    for book in books:
        local = _love(book)
        count = book.get("rating_count") or 0
        rating = book.get("rating") or 0
        if local > 0:
            pool.append((book, _("Favorited by readers here")))
        elif rating >= 4 and count >= 1000:
            pool.append((book, _("High ratings count")))
    if not pool:
        return None, False, {}, False, None
    return pool, True, {}, False, None


def _wildcard_pool(books, rng):
    counts = {}
    for book in books:
        for label, canon in book["labels"]:
            bucket = counts.setdefault(canon, {"name": label, "count": 0})
            bucket["count"] += 1
            bucket["name"] = label
    if not counts:
        return None, False, {}, False, None
    canon = rng.choice(list(counts))
    name = counts[canon]["name"]
    neighbors = set(ADJACENCY.get(canon, ()))
    pool = []
    for book in books:
        if canon in book["tags"] or name.casefold() in book["raw_tags"]:
            pool.append((book, _("Matched the tag %(name)s", name=name)))
        elif book["tags"] & neighbors:
            pool.append((book, _("Added from a neighboring genre")))
    return pool, False, {"genre": name}, False, None


def _lane_pool(books, rng, names):
    groups = {}
    for book in books:
        for label, canon in book["labels"]:
            groups.setdefault(label, {"canon": canon, "books": []})
            if book not in groups[label]["books"]:
                groups[label]["books"].append(book)
    ranked = sorted(groups, key=lambda label: len(groups[label]["books"]), reverse=True)
    rng.shuffle(ranked[:6])
    lanes = []
    seen = set()
    for label in ranked:
        if len(lanes) >= 3:
            break
        picks = []
        series = set()
        authors = {}
        order = list(groups[label]["books"])
        rng.shuffle(order)
        for book in order:
            if book["id"] in seen:
                continue
            if book["series_id"] and book["series_id"] in series:
                continue
            if book["author_key"] and authors.get(book["author_key"], 0) >= 2:
                continue
            picks.append(book)
            seen.add(book["id"])
            if book["series_id"]:
                series.add(book["series_id"])
            if book["author_key"]:
                authors[book["author_key"]] = authors.get(book["author_key"], 0) + 1
            if len(picks) >= 4:
                break
        if len(picks) < 4:
            for book in picks:
                seen.discard(book["id"])
            continue
        try:
            href = url_for("library_ui.genre_page", name=label)
        except Exception:
            href = "/genres"
        lanes.append({
            "name": label,
            "href": href,
            "ids": [book["id"] for book in picks],
            "pairs": [(book["id"], _("Placed in the %(genre)s lane", genre=label)) for book in picks],
        })
    if len(lanes) < 3:
        return None
    return lanes


def _constrain(pool, limit, used, state, rng, shuffle):
    order = list(pool)
    if shuffle:
        rng.shuffle(order)
    chosen = []
    for book, reason in order:
        if book["id"] in used or book["id"] in state["ids"]:
            continue
        if book["series_id"] and book["series_id"] in state["series"]:
            continue
        if book["author_key"] and state["authors"].get(book["author_key"], 0) >= 2:
            continue
        chosen.append((book, reason))
        state["ids"].add(book["id"])
        if book["series_id"]:
            state["series"].add(book["series_id"])
        if book["author_key"]:
            state["authors"][book["author_key"]] = state["authors"].get(book["author_key"], 0) + 1
        if len(chosen) >= limit:
            break
    return chosen


def _top_up(chosen, books, template, used, state, rng, need):
    if need <= 0:
        return []
    seeds = set(template.get("tags") or ())
    for book, _reason in chosen:
        seeds.update(book["tags"])
    neighbors = _neighbors(seeds)
    if not neighbors:
        return []
    pool = [(book, _("Added from a neighboring genre")) for book in books if book["tags"] & neighbors]
    return _constrain(pool, need, used, state, rng, True)


def _tag_reason(book, template):
    for tag in template["tags"]:
        if tag in book["tags"] or tag in book["raw_tags"]:
            return _("Matched the tag %(name)s", name=tag)
    for word in template["keywords"]:
        if _has_word(book.get("search") or "", word):
            return _("Matched the word %(word)s in the description", word=word)
    return ""


def _minutes_ok(book, bounds):
    lo, hi = bounds or (None, None)
    minutes = book.get("minutes")
    if not minutes:
        return False
    if lo is not None and minutes < lo:
        return False
    if hi is not None and minutes >= hi:
        return False
    return True


def _year_ok(book, bounds):
    lo, hi = bounds or (None, None)
    year = book.get("year")
    if not year:
        return False
    if lo is not None and year < lo:
        return False
    if hi is not None and year > hi:
        return False
    return True


def _short_feeling(book):
    if book.get("kind") == "series":
        return False
    if not _minutes_ok(book, (None, 480)):
        return False
    rating = book.get("rating")
    return rating is None or rating >= 4


def _is_fresh_opener(book, ctx):
    return bool(book["is_first"] and book["series_len"] >= 3 and book["series_id"] not in ctx["started_series"])


def _is_binge(book):
    return bool(book["is_first"] and 3 <= book["series_len"] <= 6)


def _neighbors(tags):
    found = set()
    for tag in tags or ():
        canon = _canonical(tag) or tag
        found.update(ADJACENCY.get(canon, ()))
    return found


def _has_word(text, word):
    folded = (word or "").casefold()
    if not folded:
        return False
    if " " in folded:
        return folded in (text or "")
    return bool(re.search(r"\b%s\b" % re.escape(folded), text or ""))


def _text(pattern, bits):
    text = pattern or ""
    for key, value in (bits or {}).items():
        text = text.replace("{%s}" % key, value or "")
    return text


def _context(catalog, filtered):
    from .. import ub
    from ..cw_login import current_user
    from .models import LibraryFavorite, LibraryWant

    by_id = {book["id"]: book for book in catalog}
    finished = [book for book in catalog if book["read"] == 1]
    finished.sort(key=lambda book: book["read_at"] or datetime.min, reverse=True)
    started = {book["series_id"] for book in catalog if book["series_id"] and book["read"] in (1, 2)}
    want_order = []
    want_ids = set()
    favorite_ids = set()
    love_counts = {}
    user_id = int(current_user.id) if current_user.is_authenticated else 0
    try:
        if user_id:
            wants = (ub.session.query(LibraryWant.book_id)
                     .filter(LibraryWant.user_id == user_id)
                     .order_by(LibraryWant.created.asc())
                     .all())
            want_order = [row[0] for row in wants]
            want_ids = set(want_order)
            favs = (ub.session.query(LibraryFavorite.book_id)
                    .filter(LibraryFavorite.user_id == user_id)
                    .all())
            favorite_ids = {row[0] for row in favs}
        for row in ub.session.query(LibraryFavorite.book_id).all():
            love_counts[row[0]] = love_counts.get(row[0], 0) + 1
    except Exception as error:
        log.debug("Discover personal rows unavailable: %s", error)
        ub.session.rollback()
    from .accolades import award_win_ids

    return {
        "award_wins": award_win_ids(),
        "catalog": catalog,
        "filtered": filtered,
        "by_id": by_id,
        "finished": finished,
        "last_finished": finished[0] if finished else None,
        "started_series": started,
        "want_order": want_order,
        "want_ids": want_ids,
        "favorite_ids": favorite_ids,
        "favorites": [by_id[book_id] for book_id in favorite_ids if book_id in by_id],
        "love_counts": love_counts,
    }


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


def _placed(book, reason):
    return {
        "id": book.get("id"),
        "title": book.get("title") or "",
        "reason": reason,
        "kind": book.get("kind") or "book",
        "member_titles": list(book.get("member_titles") or ()),
    }


def _debug_entry(book, reason):
    kind = "series" if book.get("kind") == "series" else "book"
    if kind == "series":
        inside = ", ".join(title for title in (book.get("member_titles") or []) if title)
        reason = "Books inside this series: %s. %s" % (inside, reason)
    return {"kind": kind, "title": book.get("title") or "", "reason": reason}


def _debug_blocks(rows, grid_ids, by_id, panel_ids, names):
    blocks = []
    if panel_ids:
        blocks.append({
            "title": _("Featured panel"),
            "template": "panel",
            "books": [
                _debug_entry(by_id[book_id], _("Shown in the featured panel"))
                for book_id in panel_ids if book_id in by_id
            ],
        })
    for row in rows:
        blocks.append({
            "title": row["title"],
            "template": row["template"],
            "books": [_debug_entry(item, item["reason"]) for item in row["books"]],
        })
    blocks.append({
        "title": _("Keep exploring"),
        "template": "grid",
        "books": [
            _debug_entry(by_id[book_id], _("Not used in a row, so it waits in the grid"))
            for book_id in grid_ids if book_id in by_id
        ],
    })
    return blocks
