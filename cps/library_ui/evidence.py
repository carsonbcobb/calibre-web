# -*- coding: utf-8 -*-

"""One evidence profile per book, with the source kept on every signal.

Missing pages, moods, ratings, and years stay missing. Nothing here guesses.
"""

import json
import re

from .shelf_config import ROW_GATES, VOCAB, bucket_for_tag

_CACHE = {"key": None, "books": {}}
_NEG = re.compile(r"(?:^|\s)(?:no|not|without|never)(?:\s+\w+){0,3}\s+$")


def clear_evidence_cache():
    _CACHE["key"] = None
    _CACHE["books"] = {}


def profiles_for(catalog):
    """Book profiles keyed by Calibre id. Rebuilt when a provider cache changes."""
    key = (_cache_key(), tuple(sorted(int(book["id"]) for book in catalog or [])))
    if _CACHE["key"] == key:
        return _CACHE["books"]
    hardcover, pages = _loads()
    keywords = _keywords()
    books = {}
    for book in catalog or []:
        books[int(book["id"])] = _book(book, hardcover.get(int(book["id"])), pages.get(int(book["id"])), keywords)
    _CACHE["key"] = key
    _CACHE["books"] = books
    return books


def series_profile(unit, books):
    """Union of tags, majority of moods, total length, average rating."""
    members = [books[book_id] for book_id in (unit.get("member_ids") or ()) if book_id in books]
    if not members:
        return _empty(unit.get("id"), unit.get("title") or "")
    profile = _empty(unit.get("id"), unit.get("title") or members[0]["title"])
    profile["kind"] = "series"
    profile["series_id"] = unit.get("series_id")
    profile["series_index"] = unit.get("series_index") or 0
    profile["count"] = len(members)
    profile["member_ids"] = [item["id"] for item in members]
    profile["author_key"] = members[0].get("author_key") or ""
    profile["started"] = any(item.get("started") for item in members)
    profile["finished_count"] = sum(int(item.get("finished_count") or 0) for item in members)
    profile["unread_left"] = any(item.get("unread_left") for item in members)
    profile["year"] = min((item["year"] for item in members if item.get("year")), default=None)
    profile["stamp"] = max((item["stamp"] for item in members if item.get("stamp")), default=None)
    _union(profile, members, "tags")
    _union(profile, members, "buckets")
    _union(profile, members, "warnings")
    _union(profile, members, "keywords")
    mood_books = [item for item in members if item.get("moods")]
    if mood_books:
        names = set()
        for item in mood_books:
            names.update(item["moods"])
        for name in names:
            count = sum(1 for item in mood_books if name in item["moods"])
            if count * 2 >= len(mood_books):
                profile["moods"][name] = mood_books[0]["moods"].get(name) or "series"
    else:
        profile["missing_moods"] = True
    if all(item.get("pages") is not None for item in members):
        profile["pages"] = sum(int(item["pages"]) for item in members)
        profile["pages_source"] = "series total"
        profile["missing_pages"] = False
    if all(item.get("minutes") is not None for item in members):
        profile["minutes"] = sum(int(item["minutes"]) for item in members)
        profile["minutes_known"] = True
    ratings = [item["rating"] for item in members if item.get("rating") is not None]
    if ratings:
        profile["rating"] = round(sum(ratings) / float(len(ratings)), 2)
    counts = [item["rating_count"] for item in members if item.get("rating_count")]
    if counts and len(counts) == len(members):
        profile["rating_count"] = int(round(sum(counts) / float(len(counts))))
    profile["missing_moods"] = not profile["moods"]
    return profile


def unit_profiles(units, books):
    found = {}
    for unit in units or []:
        if unit.get("kind") == "series":
            found[unit["id"]] = series_profile(unit, books)
        else:
            found[unit["id"]] = books.get(unit["id"]) or _empty(unit.get("id"), unit.get("title") or "")
    return found


def rating_cutoff(books):
    counts = sorted(item["rating_count"] for item in books.values() if item.get("rating_count"))
    if not counts:
        return None
    index = max(0, int(len(counts) * 0.33) - 1)
    return counts[index]


def missing_report(books):
    pages = sorted(item["title"] for item in books.values() if item.get("missing_pages"))
    moods = sorted(item["title"] for item in books.values() if item.get("missing_moods"))
    return {"missing_pages": pages, "missing_moods": moods}


def _book(book, row, page_count, keywords):
    profile = _empty(book.get("id"), book.get("title") or "")
    profile["series_id"] = book.get("series_id")
    profile["series_index"] = book.get("series_index") or 0
    profile["author_key"] = book.get("author_key") or ""
    profile["started"] = bool(book.get("read") in (1, 2) or book.get("started"))
    profile["finished_count"] = 1 if book.get("read") == 1 else 0
    profile["unread_left"] = book.get("read") != 1
    profile["year"] = book.get("year")
    profile["stamp"] = book.get("stamp")
    profile["rating"] = book.get("rating")
    profile["rating_count"] = book.get("rating_count")
    profile["member_ids"] = [book.get("id")]
    if book.get("minutes"):
        profile["minutes"] = int(book["minutes"])
        profile["minutes_known"] = True
    if page_count:
        profile["pages"] = int(page_count)
        profile["pages_source"] = "library"
        profile["missing_pages"] = False
    for tag in book.get("raw_tags") or ():
        _add_tag(profile, tag, "calibre")
    for mood in book.get("moods") or ():
        _add_mood(profile, mood, "hardcover")
    text = book.get("blurb") or ""
    if row is not None:
        if row.get("pages") and profile["pages"] is None:
            profile["pages"] = int(row["pages"])
            profile["pages_source"] = "hardcover"
            profile["missing_pages"] = False
        for tag in row.get("tags") or ():
            _add_tag(profile, tag, "hardcover")
        for genre in row.get("genres") or ():
            _add_tag(profile, genre, "hardcover")
        for mood in row.get("moods") or ():
            _add_mood(profile, mood, "hardcover")
        for warning in row.get("warnings") or ():
            _add_warning(profile, warning)
        if row.get("description"):
            text = text + " " + row["description"]
        if row.get("rating") is not None and profile["rating"] is None:
            profile["rating"] = row["rating"]
        if row.get("ratings_count") and not profile["rating_count"]:
            profile["rating_count"] = int(row["ratings_count"])
    profile["keywords"] = _keyword_hits(text, keywords)
    profile["missing_moods"] = not profile["moods"]
    profile["missing_pages"] = profile["pages"] is None
    return profile


def _empty(book_id, title):
    return {
        "id": book_id,
        "title": title or "",
        "kind": "book",
        "series_id": None,
        "series_index": 0,
        "count": 1,
        "member_ids": [book_id] if book_id else [],
        "pages": None,
        "pages_source": "",
        "minutes": None,
        "minutes_known": False,
        "year": None,
        "rating": None,
        "rating_count": None,
        "moods": {},
        "tags": {},
        "buckets": {},
        "warnings": {},
        "keywords": {},
        "started": False,
        "finished_count": 0,
        "unread_left": True,
        "accolade": False,
        "author_key": "",
        "stamp": None,
        "missing_pages": True,
        "missing_moods": True,
    }


def _union(profile, members, field):
    for item in members:
        for name, source in (item.get(field) or {}).items():
            profile[field].setdefault(name, source)


def _add_tag(profile, tag, source):
    folded = _fold(tag)
    if not folded:
        return
    profile["tags"].setdefault(folded, source)
    for key, spec in VOCAB.items():
        if folded in spec.get("tags") or ():
            profile["tags"].setdefault(key, source)
    bucket = bucket_for_tag(folded)
    if bucket:
        profile["buckets"].setdefault(bucket, source)


def _add_mood(profile, mood, source):
    folded = _fold(mood)
    if not folded:
        return
    profile["moods"].setdefault(folded, source)
    for key, spec in VOCAB.items():
        if folded == key or folded in spec.get("moods") or ():
            profile["moods"].setdefault(key, source)
            profile["moods"].setdefault(folded, source)


def _add_warning(profile, warning):
    folded = _fold(warning)
    if not folded:
        return
    profile["warnings"].setdefault(folded, "hardcover")
    for part in folded.replace(",", " ").split():
        if part:
            profile["warnings"].setdefault(part, "hardcover")


def _keyword_hits(text, keywords):
    folded = _fold(text)
    found = {}
    for word in keywords:
        pattern = re.compile(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(word))
        for match in pattern.finditer(folded):
            prefix = folded[max(0, match.start() - 48):match.start()]
            if _NEG.search(prefix):
                continue
            found[word] = "description"
            break
    return found


def _keywords():
    found = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "keyword_any":
                    found.update(_fold(word) for word in value if word)
                else:
                    walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(ROW_GATES)
    from .shelf_config import PROTAGONIST_CUES
    found.update(_fold(word) for word in PROTAGONIST_CUES if word)
    return tuple(sorted(word for word in found if word))


def _loads():
    hardcover = {}
    pages = {}
    try:
        from .. import ub
        from .models import HardcoverBook, LibraryBookStat

        for row in ub.session.query(LibraryBookStat).all():
            if row.page_count:
                pages[int(row.book_id)] = int(row.page_count)
        for row in ub.session.query(HardcoverBook).all():
            if row.error:
                continue
            hardcover[int(row.book_id)] = {
                "pages": row.pages,
                "moods": _json(row.moods),
                "genres": _json(row.genres),
                "tags": _json(row.tags),
                "warnings": _json(row.warnings),
                "description": row.description or "",
                "rating": row.rating,
                "ratings_count": row.ratings_count,
            }
    except Exception:
        try:
            from .. import ub
            ub.session.rollback()
        except Exception:
            pass
    return hardcover, pages


def _cache_key():
    from .units import metadata_mtime

    stamp = metadata_mtime()
    hardcover = ""
    pages = ""
    try:
        from .. import ub
        from sqlalchemy import func
        from .models import HardcoverBook, LibraryBookStat

        hardcover = str(ub.session.query(func.max(HardcoverBook.fetched_at)).scalar() or "")
        pages = str(ub.session.query(func.max(LibraryBookStat.scanned_at)).scalar() or "")
    except Exception:
        try:
            from .. import ub
            ub.session.rollback()
        except Exception:
            pass
    return (stamp, hardcover, pages)


def _json(text):
    try:
        value = json.loads(text or "[]")
    except ValueError:
        return []
    if isinstance(value, list):
        return [item if isinstance(item, str) else (item.get("name") or item.get("tag") or "") for item in value]
    return []


def _fold(text):
    return " ".join((text or "").replace("-", " ").replace("—", " ").replace("–", " ").split()).casefold()
