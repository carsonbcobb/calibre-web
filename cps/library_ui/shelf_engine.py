# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Fill Home, Discover, and Genres from shelf_config. Reads books. Does not write metadata."""

import random
import re
from datetime import datetime

from .logger_helper import log
from .evidence import missing_report, profiles_for, rating_cutoff, unit_profiles
from .gates import evaluate
from .shelf_config import (
    BUCKETS,
    BUCKET_BY_ID,
    BY_ID,
    DECADES,
    GENRE_SLICES,
    ROW_MIN,
    ROW_TAKE,
    ROWS,
    SPOTLIGHT_NAMES,
    bucket_for_tag,
)

_RECENT = {}
_LAST_HOME = {}
_LAST_AUDIT = {"rows": [], "missing_pages": [], "missing_moods": []}


def last_audit():
    return _LAST_AUDIT


def prepare():
    """Units, tag names, and the raw book catalog for the signed in user."""
    from .browse import _world
    from .units import display_units

    catalog, names = _world()
    years = _year_map(catalog)
    for book in catalog:
        book["year"] = years.get(book["id"])
        raw = set()
        for tag_id in book.get("tag_ids") or ():
            label = (names.get(tag_id) or "").strip().casefold()
            if label:
                raw.add(label)
        book["raw_tags"] = raw
        book["search"] = " ".join([book.get("blurb") or ""] + list(raw))
    from ..cw_login import current_user

    user_id = int(getattr(current_user, "id", 0) or 0)
    return display_units(catalog, user_id), names, catalog


def home_payload(user_id, skip_ids=()):
    plan = _page("home", user_id, skip_ids=skip_ids, avoid=_LAST_HOME.get(user_id) or ())
    _LAST_HOME[user_id] = [row["id"] for row in plan["rows"]]
    _remember(user_id, plan["rows"])
    return [_home_row(row) for row in plan["rows"]], plan


def discover_plan(seed, genre_id, panel_ids):
    from ..cw_login import current_user

    user_id = int(getattr(current_user, "id", 0) or 0) if current_user.is_authenticated else 0
    plan = _page(
        "discover",
        user_id,
        seed=seed,
        genre_id=genre_id,
        skip_ids=panel_ids,
        avoid=_LAST_HOME.get(user_id) or (),
    )
    _remember(user_id, plan["rows"])
    rows = []
    for row in plan["rows"]:
        rows.append({
            "template": row["id"],
            "title": row["title"],
            "subtitle": row["subtitle"],
            "label": row["label"],
            "books": [{"id": unit["id"], "title": unit.get("title") or "", "reason": reason, "kind": unit.get("kind") or "book"} for unit, reason in row["chosen"]],
            "cover_only": row.get("cover_only") or False,
            "lanes": None,
        })
    by_id = {book["id"]: book for book in plan["units"]}
    panel = [book_id for book_id in (panel_ids or []) if book_id in by_id]
    return {
        "rows": rows,
        "by_id": {row["template"]: row for row in rows},
        "grid_ids": plan["grid_ids"],
        "counted": panel,
        "total": len(plan["units"]),
        "debug": _debug(plan, by_id, panel),
        "dropped": plan["dropped"],
        "surfaced": plan["surfaced"],
    }


def genre_landing(user_id=0):
    units, names, catalog = prepare()
    ctx = _context(catalog, units)
    buckets = _assign(units, names)
    rng = random.Random("%s:genres:%s" % (user_id, random.SystemRandom().randrange(1, 2 ** 31 - 1)))
    _bind(units, catalog, ctx, rng)
    used = set()
    rows = []
    dropped = []
    cross = BY_ID.get("rulebreakers")
    if cross is not None:
        placed = _place(cross, units, names, ctx, rng, used)
        if placed is None:
            dropped.append(_personal_title(cross, ctx)[0])
        else:
            for unit, _reason in placed["chosen"]:
                used.add(unit["id"])
            row = _genre_row(placed, {"id": "rulebreakers", "name": "Genres", "label": "RULE BREAKERS"})
            row["href"] = "/genres"
            row["see_all_url"] = "/genres"
            rows.append(row)
    ordered = sorted((bucket for bucket in buckets if bucket["chip"] and bucket["books"]), key=lambda item: (-len(item["books"]), item["name"].lower()))
    for bucket in ordered:
        spec = BY_ID.get(bucket["row"])
        if spec is None:
            continue
        placed = _place(spec, units, names, ctx, rng, used, only_ids={book["id"] for book in bucket["books"]}, adjacent_buckets=bucket["adjacent"])
        if placed is None:
            dropped.append(_personal_title(spec, ctx)[0])
            continue
        for unit, _reason in placed["chosen"]:
            used.add(unit["id"])
        rows.append(_genre_row(placed, bucket))
    chips = [{
        "id": bucket["id"],
        "name": bucket["name"],
        "href": "/genres/%s" % bucket["name"],
        "count": len(bucket["books"]),
        "current": False,
    } for bucket in ordered]
    hero_book = None
    hero_genre = ""
    if rows and rows[0].get("_chosen"):
        hero_book = rng.choice(rows[0]["_chosen"])[0]
        hero_genre = rows[0]["label"]
    return {
        "rows": rows,
        "pills": chips,
        "hero_book": hero_book,
        "hero_genre": hero_genre,
        "buckets": buckets,
        "dropped": dropped,
        "units": units,
        "names": names,
        "catalog": catalog,
    }


def genre_page(name, sort_mode, user_id=0):
    units, names, catalog = prepare()
    ctx = _context(catalog, units)
    buckets = _assign(units, names)
    wanted = (name or "").strip().casefold()
    bucket = None
    for item in buckets:
        if item["id"] == wanted or item["name"].casefold() == wanted:
            bucket = item
            break
    if bucket is None or not bucket["books"]:
        return None
    rng = random.Random("%s:%s:%s" % (user_id, bucket["id"], random.SystemRandom().randrange(1, 2 ** 31 - 1)))
    _bind(units, catalog, ctx, rng)
    inside = {book["id"] for book in bucket["books"]}
    used = set()
    rows = []
    for spec_row in GENRE_SLICES:
        rule = spec_row["rule"]
        spec = {
            "id": spec_row["id"],
            "title": spec_row["title"],
            "titles": spec_row.get("titles") or (spec_row["title"],),
            "subtitle": spec_row["subtitle"],
            "label": bucket["label"],
            "rule": rule,
            "buckets": (bucket["id"],),
            "keywords": (),
            "adjacent": (),
            "author_cap": 2,
            "minimum": ROW_MIN,
        }
        only = inside
        adjacent_buckets = ()
        if rule == "adjacent":
            only = None
            adjacent_buckets = bucket["adjacent"]
            spec["rule"] = "bucket"
            spec["buckets"] = bucket["adjacent"]
        placed = _place(spec, units, names, ctx, rng, used, only_ids=only, adjacent_buckets=adjacent_buckets)
        if placed is None:
            continue
        for unit, _reason in placed["chosen"]:
            used.add(unit["id"])
        rows.append(_genre_row(placed, bucket, row_id=spec_row["id"]))
    hero = rng.choice(bucket["books"]) if bucket["books"] else None
    grid = []
    for unit in bucket["books"]:
        for book_id in unit.get("member_ids") or (unit["id"],):
            if book_id not in grid and (hero is None or book_id != hero["id"]):
                grid.append(book_id)
    chips = []
    for item in sorted((entry for entry in buckets if entry["chip"] and entry["books"]), key=lambda entry: (-len(entry["books"]), entry["name"].lower())):
        chips.append({
            "id": item["id"],
            "name": item["name"],
            "href": "/genres/%s" % item["name"],
            "count": len(item["books"]),
            "current": item["id"] == bucket["id"],
        })
    return {
        "name": bucket["name"],
        "id": bucket["id"],
        "hero_book": hero,
        "rows": rows,
        "grid": grid,
        "grid_title": "All books",
        "grid_label": bucket["name"],
        "grid_subtitle": "",
        "grid_count": len(grid),
        "pills": chips,
        "sort": sort_mode if sort_mode in ("added", "title", "rating", "length") else "added",
    }


def _page(kind, user_id, skip_ids=(), seed=None, genre_id=None, avoid=()):
    units, names, catalog = prepare()
    ctx = _context(catalog, units)
    if genre_id:
        units = [unit for unit in units if genre_id in _buckets(unit, names) or str(genre_id) in {str(item) for item in (unit.get("tag_ids") or ())}]
    skipped = {int(item) for item in (skip_ids or []) if item}
    pool_units = [
        unit for unit in units
        if unit["id"] not in skipped and not (set(unit.get("member_ids") or ()) & skipped)
    ]
    rng = random.Random(seed or "%s:%s:%s" % (kind, user_id, random.SystemRandom().randrange(1, 2 ** 31 - 1)))
    _bind(units, catalog, ctx, rng)
    hidden = _hidden()
    specs = [row for row in ROWS if kind in row["where"] and row["id"] not in hidden]
    personal = [row for row in specs if row["group"] == "personal" and _has_personal(row, ctx)]
    specs = [row for row in specs if row["group"] != "personal"]
    avoid_ids = set(avoid or ())
    preferred = [row for row in specs if row["id"] not in avoid_ids]
    rest = [row for row in specs if row["id"] in avoid_ids]
    rng.shuffle(preferred)
    rng.shuffle(rest)
    queue = preferred + rest
    spare_personal = []
    if personal:
        rng.shuffle(personal)
        spare_personal = personal[1:]
        queue = [personal[0]] + queue
    target = 12 if len(pool_units) >= 72 else 10
    target = min(12, max(10, target))
    if len(pool_units) < 60:
        target = min(target, max(6, len(pool_units) // ROW_MIN))
    ordered = []
    deferred = []
    for spec in queue:
        if ordered and spec["group"] == ordered[-1]["group"]:
            deferred.append(spec)
            continue
        ordered.append(spec)
    ordered.extend(deferred)
    if spare_personal:
        ordered[1:1] = spare_personal
    rows, dropped, used, audit = _allocate(ordered, pool_units, ctx, rng, target)
    missing = missing_report(ctx.get("evidence_books") or {})
    global _LAST_AUDIT
    _LAST_AUDIT = {
        "rows": audit,
        "missing_pages": missing.get("missing_pages") or [],
        "missing_moods": missing.get("missing_moods") or [],
    }
    surfaced = set(skipped)
    for unit in pool_units:
        surfaced.add(unit["id"])
        surfaced.update(unit.get("member_ids") or ())
    grid = [unit["id"] for unit in pool_units if unit["id"] not in used]
    rng.shuffle(grid)
    return {
        "rows": rows,
        "dropped": dropped,
        "units": pool_units,
        "grid_ids": grid,
        "surfaced": len(surfaced),
        "catalog_count": len(catalog),
        "audit": audit,
        "missing": missing,
    }


def _bind(units, catalog, ctx, rng):
    books = profiles_for(catalog)
    ctx["profiles"] = unit_profiles(units, books)
    ctx["evidence_books"] = books
    ctx["rating_cutoff"] = rating_cutoff(books)
    ctx["source_profiles"] = {}
    profiles = ctx["profiles"]
    if ctx.get("last_finished"):
        ctx["source_profiles"]["last_finished"] = profiles.get(ctx["last_finished"]["id"])
    if ctx.get("favorite_unit"):
        ctx["source_profiles"]["favorite"] = profiles.get(ctx["favorite_unit"]["id"])
    awards = ctx.get("awards") or set()
    for profile in profiles.values():
        profile["accolade"] = bool(set(profile.get("member_ids") or ()) & awards)
    band, test = _pick_decade(units, profiles, rng)
    ctx["decade_band"] = band
    ctx["decade_test"] = test


def _pick_decade(units, profiles, rng):
    ready = []
    for band in DECADES:
        start = band.get("start")
        end = band.get("end")

        def test(year, start=start, end=end):
            return (start is None or year >= start) and (end is None or year <= end)

        count = 0
        for unit in units:
            year = (profiles.get(unit["id"]) or {}).get("year")
            if year and test(int(year)):
                count += 1
        if count >= ROW_MIN:
            ready.append((band, test))
    if not ready:
        return None, None
    return rng.choice(ready)


def _allocate(specs, units, ctx, rng, target):
    """Each unit goes to its highest scoring row. Gates are never relaxed."""
    profiles = ctx.get("profiles") or {}
    options = {}
    audits = []
    titled = []
    for index, spec in enumerate(specs):
        spec = dict(spec)
        choices = tuple(spec.get("titles") or ())
        if len(choices) > 1 and spec.get("rule") != "decade":
            spec["title"] = rng.choice(choices)
        subs = tuple(spec.get("subtitles") or ())
        if len(subs) > 1:
            spec["subtitle"] = rng.choice(subs)
        title, subtitle = _personal_title(spec, ctx)
        if spec.get("rule") == "decade" and ctx.get("decade_band"):
            title = ctx["decade_band"]["title"]
            subtitle = ctx["decade_band"]["subtitle"]
        titled.append((spec, title, subtitle))
        fails = {}
        qualified = []
        for unit in units:
            profile = profiles.get(unit["id"])
            if profile is None:
                fails["missing profile"] = fails.get("missing profile", 0) + 1
                continue
            result = evaluate(spec, profile, ctx)
            if result["gates"] and not result["ok"]:
                fails[result["failed"] or "gate"] = fails.get(result["failed"] or "gate", 0) + 1
            floor = result["topup_score"] if result["gates_ok"] else result["min_score"]
            if result["gates_ok"] and result["score"] >= floor:
                qualified.append((unit, result))
            elif not result["ok"]:
                pass
        options[spec["id"]] = qualified
        audits.append({
            "id": spec["id"],
            "title": title,
            "qualified": len(qualified),
            "kept": 0,
            "dropped": False,
            "gates": fails,
        })
    by_unit = {}
    for spec_id, pairs in options.items():
        by_unit[spec_id] = {unit["id"]: (unit, result) for unit, result in pairs}
    others = [item for item in titled if item[0]["id"] != "rulebreakers"]
    cross = [item for item in titled if item[0]["id"] == "rulebreakers"]
    if others and cross:
        titled = others[:1] + cross + others[1:]
    elif cross:
        titled = cross + others
    loose = [spec["id"] for spec, _title, _subtitle in titled if _strict(spec) <= 0]
    active = {spec["id"] for spec, _title, _subtitle in titled if _strict(spec) > 0}
    reserved = None
    if cross:
        spec, title, subtitle = cross[0]
        chosen = _trim(
            options.get("rulebreakers") or [],
            ROW_TAKE,
            int(spec.get("author_cap") or 2),
            _sort_for(spec),
            profiles,
        )
        minimum = int(spec.get("minimum") or ROW_MIN)
        audit = next(item for item in audits if item["id"] == "rulebreakers")
        if len(chosen) >= minimum:
            reserved = (title, subtitle, chosen)
            active.discard("rulebreakers")
            loose = [row_id for row_id in loose if row_id != "rulebreakers"]
            held = {unit["id"] for unit, _result in chosen}
            for spec_id, mapping in by_unit.items():
                if spec_id == "rulebreakers":
                    continue
                for unit_id in held:
                    mapping.pop(unit_id, None)
            audit["kept"] = len(chosen)
            audit["dropped"] = False
        else:
            audit["kept"] = len(chosen)
            audit["dropped"] = True
            active.discard("rulebreakers")
    banned = {}
    final = {}
    for _round in range(4000):
        buckets = {row_id: [] for row_id in active}
        for unit in units:
            best = None
            best_key = None
            blocked = banned.get(unit["id"]) or set()
            for index, (spec, _title, _subtitle) in enumerate(titled):
                if spec["id"] not in active or spec["id"] in blocked:
                    continue
                pair = (by_unit.get(spec["id"]) or {}).get(unit["id"])
                if pair is None:
                    continue
                result = pair[1]
                key = (result["score"], result["strict"], -index)
                if best_key is None or key > best_key:
                    best_key = key
                    best = (spec["id"], pair[0], result)
            if best is not None:
                buckets[best[0]].append((best[1], best[2]))
        overflow = False
        under = []
        kept = {}
        sizes = {}
        for spec, title, subtitle in titled:
            if spec["id"] not in active:
                continue
            cap = int(spec.get("author_cap") or 2)
            minimum = int(spec.get("minimum") or ROW_MIN)
            pool = buckets.get(spec["id"]) or []
            chosen = _trim(pool, ROW_TAKE, cap, _sort_for(spec), profiles)
            chosen_ids = {unit["id"] for unit, _result in chosen}
            sizes[spec["id"]] = len(chosen)
            for unit, _result in pool:
                if unit["id"] not in chosen_ids:
                    banned.setdefault(unit["id"], set()).add(spec["id"])
                    overflow = True
            if len(chosen) < minimum:
                under.append(spec)
                for audit in audits:
                    if audit["id"] == spec["id"]:
                        audit["dropped"] = True
                        audit["kept"] = len(chosen)
                continue
            kept[spec["id"]] = (title, subtitle, chosen)
            for audit in audits:
                if audit["id"] == spec["id"]:
                    audit["dropped"] = False
                    audit["kept"] = len(chosen)
        if overflow:
            continue
        final = kept
        if not under:
            break
        under_ids = {spec["id"] for spec in under}
        needed = set()
        for spec in under:
            for unit, _result in buckets.get(spec["id"]) or []:
                best_id = None
                best_key = None
                for index, (other, _title, _subtitle) in enumerate(titled):
                    if other["id"] not in under_ids or other["id"] == spec["id"]:
                        continue
                    pair = (by_unit.get(other["id"]) or {}).get(unit["id"])
                    if pair is None:
                        continue
                    key = (pair[1]["score"], pair[1]["strict"], -index)
                    if best_key is None or key > best_key:
                        best_key = key
                        best_id = other["id"]
                if best_id:
                    needed.add(best_id)
        leaves = [spec for spec in under if spec["id"] not in needed] or under
        victim = min(leaves, key=lambda spec: (sizes.get(spec["id"], 0), _strict(spec), spec["id"]))
        active.discard(victim["id"])
        for unit, _result in buckets.get(victim["id"]) or []:
            banned.setdefault(unit["id"], set()).add(victim["id"])
    if reserved is not None:
        final["rulebreakers"] = reserved
    taken = set()
    for _title, _subtitle, chosen in final.values():
        for unit, _result in chosen:
            taken.add(unit["id"])
    for spec, title, subtitle in titled:
        if spec["id"] not in loose:
            continue
        pool = []
        for unit, result in options.get(spec["id"]) or ():
            if unit["id"] not in taken:
                pool.append((unit, result))
        cap = int(spec.get("author_cap") or 2)
        minimum = int(spec.get("minimum") or ROW_MIN)
        chosen = _trim(pool, ROW_TAKE, cap, _sort_for(spec), profiles)
        audit = next(item for item in audits if item["id"] == spec["id"])
        if len(chosen) < minimum:
            audit["dropped"] = True
            audit["kept"] = len(chosen)
            continue
        audit["dropped"] = False
        final[spec["id"]] = (title, subtitle, chosen)
        for unit, _result in chosen:
            taken.add(unit["id"])
    rows = []
    dropped = []
    used = set()
    for spec, title, subtitle in titled:
        audit = next(item for item in audits if item["id"] == spec["id"])
        if spec["id"] not in final:
            if audit["dropped"] or audit["qualified"] < int(spec.get("minimum") or ROW_MIN):
                dropped.append(title)
            continue
        if len(rows) >= target:
            continue
        title, subtitle, chosen = final[spec["id"]]
        audit["kept"] = len(chosen)
        audit["dropped"] = False
        for unit, _result in chosen:
            used.add(unit["id"])
        rows.append({
            "id": spec["id"],
            "group": spec.get("group") or "",
            "title": title,
            "subtitle": subtitle,
            "label": spec.get("label") or "",
            "cover_only": spec.get("cover_only") or False,
            "chosen": [(unit, result["reason"]) for unit, result in chosen],
            "scores": {unit["id"]: result["score"] for unit, result in chosen},
            "checks": {unit["id"]: {"gates": result["gates"], "signals": result["signals"], "score": result["score"]} for unit, result in chosen},
        })
    return rows, dropped, used, audits


def _strict(spec):
    from .shelf_config import ROW_GATES
    gate = ROW_GATES.get(spec.get("id") or "") or {}
    return int(gate.get("strict") or 0)


def _sort_for(spec):
    from .shelf_config import ROW_GATES
    gate = ROW_GATES.get(spec.get("id") or "") or {}
    if spec.get("rule") == "short":
        return "shortest"
    return gate.get("sort") or "score"


def _trim(pairs, take, cap, sort, profiles=None):
    profiles = profiles or {}

    def key(item):
        unit, result = item
        profile = profiles.get(unit["id"]) or {}
        if sort == "shortest":
            length = profile.get("pages") if profile.get("pages") else profile.get("minutes") or 10 ** 9
            return (int(length), -result["score"])
        if sort == "rating":
            return (-float(profile.get("rating") or 0), -result["score"])
        if sort == "newest":
            stamp = unit.get("stamp")
            stamp = stamp.timestamp() if hasattr(stamp, "timestamp") else 0
            return (-stamp, -result["score"])
        return (-result["score"], 0)
    ordered = sorted(pairs, key=key)
    chosen = []
    authors = {}
    for unit, result in ordered:
        author = unit.get("author_key") or ""
        if author and authors.get(author, 0) >= cap:
            continue
        if author:
            authors[author] = authors.get(author, 0) + 1
        chosen.append((unit, result))
        if len(chosen) >= take:
            break
    return chosen


def _place(spec, units, names, ctx, rng, used, only_ids=None, adjacent_buckets=()):
    spec = dict(spec)
    choices = tuple(spec.get("titles") or ())
    if len(choices) > 1 and spec.get("rule") != "decade":
        spec["title"] = rng.choice(choices)
    subs = tuple(spec.get("subtitles") or ())
    if len(subs) > 1:
        spec["subtitle"] = rng.choice(subs)
    if spec.get("rule") == "adjacent":
        spec["rule"] = "bucket"
    profiles = ctx.get("profiles") or {}
    primary = []
    for unit in units:
        if unit["id"] in (used or ()):
            continue
        if only_ids is not None and unit["id"] not in only_ids:
            continue
        profile = profiles.get(unit["id"])
        if profile is None:
            continue
        result = evaluate(spec, profile, ctx)
        if result["ok"]:
            primary.append((unit, result))
    title, subtitle = _personal_title(spec, ctx)
    spec["title"] = title
    spec["subtitle"] = subtitle
    cap = int(spec.get("author_cap") or 2)
    minimum = int(spec.get("minimum") or ROW_MIN)
    chosen = _trim(primary, ROW_TAKE, cap, _sort_for(spec), profiles)
    if len(chosen) < minimum:
        return None
    return {
        "id": spec["id"],
        "group": spec.get("group") or "",
        "title": spec["title"],
        "subtitle": spec["subtitle"],
        "label": spec.get("label") or "",
        "cover_only": spec.get("cover_only") or False,
        "chosen": [(unit, result["reason"]) for unit, result in chosen],
        "scores": {unit["id"]: result["score"] for unit, result in chosen},
        "checks": {unit["id"]: {"gates": result["gates"], "signals": result["signals"], "score": result["score"]} for unit, result in chosen},
    }


def _match(spec, unit, names, ctx, rng):
    rule = spec.get("rule")
    text = _hay(unit, names)
    buckets = _buckets(unit, names)
    wanted = set(spec.get("buckets") or ())
    words = tuple(spec.get("keywords") or ())
    if rule == "bucket":
        if wanted & buckets:
            return "Matches the genre"
        if _hit(text, words):
            return "Keyword match"
        return ""
    if rule == "keywords":
        if _hit(text, words):
            return "Keyword match"
        return ""
    if rule == "magic":
        special = ("allomancy", "magic system", "runes", "stormlight", "mistborn")
        if _hit(text, special):
            return "Rules based magic"
        if "epic_fantasy" in buckets and _hit(text, ("magic",)):
            return "Epic fantasy with magic"
        return ""
    if rule == "robots":
        machine = ("robot", "android", "murderbot", "artificial")
        funny = ("humor", "funny", "snark", "joke")
        if _hit(text, machine) and ("humor" in buckets or _hit(text, funny)):
            return "A machine with a personality"
        return ""
    if rule == "timeless":
        if "classics" in buckets:
            return "Classics shelf"
        year = unit.get("year")
        rating = unit.get("rating")
        if year and year < 1990 and rating is not None and rating >= 4:
            return "Published before 1990 and rated 4 or higher"
        return ""
    if rule == "series_new":
        if unit.get("kind") == "series" and not unit.get("started") and int(unit.get("count") or unit.get("series_len") or 0) >= 3:
            return "A series you have not started"
        return ""
    if rule == "series_next":
        if unit.get("kind") == "series" and unit.get("started") and unit.get("unread_left"):
            return "You already started this series"
        return ""
    if rule == "binge":
        count = int(unit.get("count") or unit.get("series_len") or 0)
        if unit.get("kind") == "series" and 2 <= count <= 5 and unit.get("series_id") not in ctx["incomplete"]:
            return "A short series you can finish"
        return ""
    if rule == "big_series":
        if unit.get("kind") == "series" and int(unit.get("count") or unit.get("series_len") or 0) >= 5:
            return "Five books or more"
        return ""
    if rule == "standalone":
        if unit.get("kind") != "series" and not unit.get("series_id"):
            return "Not part of a series"
        return ""
    if rule == "short":
        minutes = unit.get("minutes")
        if unit.get("kind") != "series" and not unit.get("series_id") and minutes and minutes <= 360:
            return "Under six hours"
        return ""
    if rule == "snacks":
        minutes = unit.get("minutes") or 0
        if unit.get("kind") != "series" and not unit.get("series_id") and minutes >= 900:
            return "Over fifteen hours"
        if unit.get("kind") == "series" and minutes >= 3600:
            return "Series runs past sixty hours"
        return ""
    if rule == "fresh":
        if unit.get("stamp"):
            return "Recently added"
        return ""
    if rule == "unread":
        if not unit.get("started") and unit.get("read") != 1:
            return "Still unopened"
        return ""
    if rule == "gems":
        rating = unit.get("rating")
        if rating is not None and rating >= 4:
            return "Rated 4 or higher with a smaller ratings count"
        return ""
    if rule == "award":
        members = set(unit.get("member_ids") or ()) | {unit.get("id")}
        if members & ctx["awards"]:
            return "Recorded accolade"
        return ""
    if rule == "rated":
        if unit.get("rating") is not None:
            return "Highest rated in this genre"
        return ""
    if rule == "covers" or rule == "dice":
        return "Picked at random"
    if rule == "wildcard":
        pick = (ctx or {}).get("wildcard") or {}
        if pick.get("id") and pick["id"] in buckets:
            return "Wildcard genre"
        return ""
    if rule == "ignored":
        pick = (ctx or {}).get("ignored") or {}
        if pick.get("id") and pick["id"] in buckets:
            return "Least finished genre"
        return ""
    if rule == "because":
        source = ctx.get("last_finished")
        if source is None:
            return ""
        if unit["id"] == source["id"] or (source.get("series_id") and unit.get("series_id") == source.get("series_id")):
            return ""
        if set(unit.get("tags") or ()) & set(source.get("tags") or ()):
            return "Shares a genre with %s" % (source.get("title") or "the last book")
        return ""
    if rule == "favorite":
        fav = ctx.get("favorite_unit")
        if fav is None:
            return ""
        if unit["id"] == fav["id"] or (fav.get("series_id") and unit.get("series_id") == fav.get("series_id")):
            return ""
        if set(unit.get("tags") or ()) & set(fav.get("tags") or ()):
            return "Close to a favorite"
        return ""
    if rule == "author":
        author = ctx.get("finished_author")
        if not author:
            return ""
        if (unit.get("author_key") or "") != author:
            return ""
        if unit["id"] in ctx.get("finished_ids", ()):
            return ""
        return "Same author you finished"
    if rule == "spotlight":
        name = (ctx.get("spotlight") or {}).get("key") or ""
        if name and name in (unit.get("author_key") or ""):
            return "Part of the author spotlight"
        return ""
    if rule == "decade":
        return ""
    return ""


def _decade(units, rng, only_ids):
    bands = []
    for band in DECADES:
        start = band.get("start")
        end = band.get("end")
        bands.append((
            band["title"],
            band["subtitle"],
            lambda year, start=start, end=end: (start is None or year >= start) and (end is None or year <= end),
        ))
    ready = []
    for title, subtitle, test in bands:
        pool = []
        for unit in units:
            if only_ids is not None and unit["id"] not in only_ids:
                continue
            year = unit.get("year")
            if year and test(int(year)):
                pool.append((unit, title, _score(unit, {})))
        if len(pool) >= ROW_MIN:
            ready.append((pool, title, subtitle))
    if not ready:
        return [], "", ""
    pool, title, subtitle = rng.choice(ready)
    return pool, title, subtitle


def _personal_title(spec, ctx):
    rule = spec.get("rule")
    spotlight = ctx.get("spotlight") or {}
    wildcard = ctx.get("wildcard") or {}
    ignored = ctx.get("ignored") or {}
    if rule == "spotlight":
        author = spotlight.get("name") or ""
    else:
        author = ctx.get("finished_author_name") or ""
    if rule == "wildcard":
        bucket = wildcard.get("name") or ""
    else:
        bucket = ignored.get("name") or ""
    filled = {
        "book": ctx.get("last_finished_title") or "a book",
        "favorite": ctx.get("favorite_title") or "a favorite",
        "author": author or "them",
        "bucket": bucket or "this shelf",
    }
    return _fill_title(spec["title"], filled), _fill_title(spec["subtitle"], filled)


def _fill_title(text, filled):
    for key, value in filled.items():
        text = (text or "").replace("{%s}" % key, value or "")
    return text


def _has_personal(spec, ctx):
    if spec["rule"] == "because":
        return ctx.get("last_finished") is not None
    if spec["rule"] == "favorite":
        return ctx.get("favorite_unit") is not None
    if spec["rule"] == "author":
        return bool(ctx.get("finished_author"))
    return True


def _take(pool, rng, used, limit, author_cap, allow_repeat):
    ranked = list(pool)
    rng.shuffle(ranked)
    ranked.sort(key=lambda item: item[2], reverse=True)
    chosen = []
    seen = set()
    authors = {}
    for unit, reason, score in ranked:
        if unit["id"] in seen:
            continue
        if not allow_repeat and unit["id"] in used:
            continue
        author = unit.get("author_key") or ""
        if author and authors.get(author, 0) >= author_cap:
            continue
        chosen.append((unit, reason, score))
        seen.add(unit["id"])
        if author:
            authors[author] = authors.get(author, 0) + 1
        if len(chosen) >= limit:
            break
    return chosen


def _score(unit, ctx):
    recent = set((ctx or {}).get("recent") or ())
    score = 100
    if unit.get("id") in recent:
        score -= 40
    if unit.get("rating"):
        score += int(float(unit["rating"]) * 2)
    return score


def _context(catalog, units):
    from .. import ub
    from ..cw_login import current_user
    from .accolades import award_win_ids
    from .models import LibraryFavorite, LibraryWant

    user_id = int(getattr(current_user, "id", 0) or 0) if getattr(current_user, "is_authenticated", False) else 0
    finished = [book for book in catalog if book.get("read") == 1]
    finished.sort(key=lambda book: book.get("read_at") or datetime.min, reverse=True)
    last = finished[0] if finished else None
    favorite_ids = set()
    want_ids = set()
    try:
        if user_id:
            favorite_ids = {row[0] for row in ub.session.query(LibraryFavorite.book_id).filter(LibraryFavorite.user_id == user_id).all()}
            want_ids = {row[0] for row in ub.session.query(LibraryWant.book_id).filter(LibraryWant.user_id == user_id).all()}
    except Exception as error:
        log.debug("Shelf personal data unavailable: %s", error)
        ub.session.rollback()
    by_member = {}
    for unit in units:
        for book_id in unit.get("member_ids") or (unit["id"],):
            by_member[book_id] = unit
    favorite_unit = None
    for book_id in favorite_ids:
        if book_id in by_member:
            favorite_unit = by_member[book_id]
            break
    author_key = ""
    author_name = ""
    if last and last.get("author_key"):
        author_key = last["author_key"]
        author_name = last.get("author_name") or ""
    spotlight = _spotlight(units)
    wildcard, ignored = _genre_picks(units, catalog, finished, want_ids)
    awards = set(award_win_ids())
    try:
        from .models import BookAccolade
        awards.update(row[0] for row in ub.session.query(BookAccolade.book_id).all())
    except Exception:
        ub.session.rollback()
    incomplete = set()
    try:
        from .models import SeriesInfo
        for series_id, done in ub.session.query(SeriesInfo.series_id, SeriesInfo.is_complete).all():
            if done is False or done == 0:
                incomplete.add(series_id)
    except Exception:
        ub.session.rollback()
    by_book = {book["id"]: book for book in catalog}
    favorite_title = ""
    for book_id in favorite_ids:
        book = by_book.get(book_id)
        if book is not None:
            favorite_title = book.get("title") or ""
            break
    return {
        "last_finished": by_member.get(last["id"]) if last else None,
        "last_finished_title": (last.get("title") if last else "") or "",
        "favorite_unit": favorite_unit,
        "favorite_title": favorite_title,
        "finished_author": author_key,
        "finished_author_name": author_name,
        "finished_ids": {book["id"] for book in finished},
        "want_ids": want_ids,
        "spotlight": spotlight,
        "wildcard": wildcard,
        "ignored": ignored,
        "awards": awards,
        "incomplete": incomplete,
        "recent": _RECENT.get(user_id, ()),
    }


def _spotlight(units):
    piles = {}
    for unit in units:
        key = unit.get("author_key") or ""
        for name in SPOTLIGHT_NAMES:
            if name in key:
                piles.setdefault(name, []).append(unit)
    ready = [(name, pile) for name, pile in piles.items() if len(pile) >= 3]
    if not ready:
        return None
    name, pile = random.choice(ready)
    return {"key": name, "name": pile[0].get("author_name") or name.title()}


def _genre_picks(units, catalog, finished, want_ids):
    counts = {}
    touched = {}
    finished_ids = {book["id"] for book in finished}
    for unit in units:
        buckets = set()
        for tag in unit.get("raw_tags") or ():
            bucket_id = bucket_for_tag(tag)
            if bucket_id and BUCKET_BY_ID.get(bucket_id, {}).get("chip"):
                buckets.add(bucket_id)
        members = set(unit.get("member_ids") or ()) | {unit["id"]}
        hit = bool(members & finished_ids or members & want_ids)
        for bucket_id in buckets:
            counts[bucket_id] = counts.get(bucket_id, 0) + 1
            if hit:
                touched[bucket_id] = touched.get(bucket_id, 0) + 1
    ready = [bucket_id for bucket_id, count in counts.items() if count >= ROW_MIN]
    if not ready:
        return None, None
    wildcard_id = random.choice(ready)
    ignored_id = sorted(ready, key=lambda bucket_id: (touched.get(bucket_id, 0), -counts[bucket_id]))[0]
    return (
        {"id": wildcard_id, "name": BUCKET_BY_ID[wildcard_id]["name"]},
        {"id": ignored_id, "name": BUCKET_BY_ID[ignored_id]["name"]},
    )


def _assign(units, names):
    buckets = []
    by_id = {}
    for spec in BUCKETS:
        bucket = dict(spec)
        bucket["books"] = []
        buckets.append(bucket)
        by_id[spec["id"]] = bucket
    for unit in units:
        for bucket_id in _buckets(unit, names):
            if bucket_id in by_id:
                by_id[bucket_id]["books"].append(unit)
    return buckets


def _year_map(catalog):
    years = {}
    try:
        from .. import calibre_db, db

        ids = [book["id"] for book in catalog or []]
        if not ids:
            return years
        for book_id, pubdate in calibre_db.session.query(db.Books.id, db.Books.pubdate).filter(db.Books.id.in_(ids)):
            year = getattr(pubdate, "year", None)
            if year and 1800 <= int(year) <= 2100:
                years[book_id] = int(year)
    except Exception as error:
        log.debug("Publish years unavailable: %s", error)
    return years


def _hit(text, words):
    for word in words or ():
        if not word:
            continue
        if " " in word:
            if word in text:
                return True
            continue
        if re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(word), text):
            return True
    return False


def _reason_score(reason, score):
    if score is None or "Score " in (reason or ""):
        return reason
    return "%s. Score %s" % (reason, score)


def _buckets(unit, names):
    found = set()
    for tag_id in unit.get("tag_ids") or ():
        bucket_id = bucket_for_tag((names or {}).get(tag_id) or "")
        if bucket_id:
            found.add(bucket_id)
    for tag in unit.get("raw_tags") or ():
        bucket_id = bucket_for_tag(tag)
        if bucket_id:
            found.add(bucket_id)
    return found


def _hay(unit, names):
    parts = [unit.get("blurb") or "", unit.get("title") or "", unit.get("series_name") or ""]
    for tag_id in unit.get("tag_ids") or ():
        parts.append((names or {}).get(tag_id) or "")
    parts.extend(unit.get("raw_tags") or ())
    return " ".join(parts).casefold()


def _home_row(row):
    counts = {}
    ids = []
    reasons = []
    for unit, reason in row["chosen"]:
        ids.append(unit["id"])
        reasons.append((unit.get("title") or "", _reason_score(reason, (row.get("scores") or {}).get(unit["id"]))))
        count = int(unit.get("count") or unit.get("series_len") or 1)
        if count > 1:
            counts[unit["id"]] = count
    return {
        "id": row["id"],
        "title": row["title"],
        "subtitle": row["subtitle"],
        "label": row["label"],
        "book_ids": ids,
        "counts": counts,
        "reasons": reasons,
        "cover_only": bool(row.get("cover_only")),
        "kind": "discovery",
        "source": row["id"],
        "link": None,
        "pinned": False,
        "sort_order": 0,
    }


def _genre_row(placed, bucket, title=None, subtitle=None, row_id=None):
    ids = [unit["id"] for unit, _reason in placed["chosen"]]
    return {
        "id": row_id or placed["id"],
        "slug": row_id or placed["id"],
        "label": placed["label"] or bucket["label"],
        "title": title or placed["title"],
        "name": bucket["name"],
        "subtitle": subtitle or placed["subtitle"],
        "count": len(ids),
        "href": "/genres/%s" % bucket["name"],
        "see_all_url": "/genres/%s" % bucket["name"],
        "book_ids": ids,
        "reasons": [(unit.get("title") or "", _reason_score(reason, (placed.get("scores") or {}).get(unit["id"]))) for unit, reason in placed["chosen"]],
        "bucket": bucket["id"],
        "_chosen": placed["chosen"],
    }


def _hidden():
    try:
        from .home_rows import _override_map
        return {slug for slug, row in _override_map().items() if row.hidden}
    except Exception:
        return set()


def _remember(user_id, rows):
    found = list(_RECENT.get(user_id) or ())
    for row in rows:
        for unit, _reason in row["chosen"]:
            if unit["id"] not in found:
                found.append(unit["id"])
    _RECENT[user_id] = found[-80:]


def _debug(plan, by_id, panel):
    blocks = []
    if panel:
        blocks.append({
            "title": "Featured panel",
            "template": "panel",
            "books": [{"kind": "book", "title": (by_id.get(book_id) or {}).get("title") or "", "reason": "Shown in the featured panel"} for book_id in panel],
        })
    for row in plan["rows"]:
        blocks.append({
            "title": row["title"],
            "template": row["id"],
            "books": [{"kind": unit.get("kind") or "book", "title": unit.get("title") or "", "reason": _reason_score(reason, (row.get("scores") or {}).get(unit["id"]))} for unit, reason in row["chosen"]],
        })
    if plan["dropped"]:
        blocks.append({
            "title": "Dropped rows",
            "template": "dropped",
            "books": [{"kind": "book", "title": title, "reason": "Fewer than 6 units passed every gate"} for title in plan["dropped"]],
        })
    for row in plan.get("audit") or []:
        fails = ", ".join("%s %s" % (name, count) for name, count in sorted((row.get("gates") or {}).items()))
        blocks.append({
            "title": row["title"],
            "template": "audit",
            "books": [{"kind": "book", "title": "qualified %s, kept %s" % (row["qualified"], row["kept"]), "reason": fails or "No gate failures"}],
        })
    missing = plan.get("missing") or {}
    if missing.get("missing_pages") or missing.get("missing_moods"):
        blocks.append({
            "title": "Missing evidence",
            "template": "missing",
            "books": [
                {"kind": "book", "title": "No page count", "reason": ", ".join(missing.get("missing_pages") or [])},
                {"kind": "book", "title": "No moods", "reason": ", ".join(missing.get("missing_moods") or [])},
            ],
        })
    blocks.append({
        "title": "Books surfaced",
        "template": "surfaced",
        "books": [{"kind": "book", "title": "%s of %s books" % (plan["surfaced"], plan["catalog_count"]), "reason": "Member books reached by the rows and the grid"}],
    })
    return blocks
