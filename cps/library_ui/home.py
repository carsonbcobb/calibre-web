# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import random

from flask_babel import gettext as _
from sqlalchemy import func, or_

from .logger_helper import log
from .heroes import hero_slides


def render_home():
    from ..render_template import render_title_template
    from .home_rows import page_rows

    heroes = _face_heroes(heroes_or_fallback())
    hero_ids = _hero_book_ids(heroes)
    cards = discover_cards(3, hero_ids=hero_ids)
    panel_ids = [card["id"] for card in cards if card.get("id")]
    rows = page_rows(skip_ids=list(hero_ids) + panel_ids)
    first_row = rows[0] if rows else None
    return render_title_template(
        "library_home.html",
        title=_("Home"),
        page="libraryhome",
        first_row=first_row,
        home_rows=rows[1:],
        collections=collection_cards(),
        heroes=heroes,
        discover_cards=cards,
        discover_exclude=list(hero_ids) + panel_ids,
    )


def discover_books(limit=3, exclude_ids=None):
    try:
        from .. import calibre_db, db
        query = (calibre_db.session.query(db.Books)
                 .filter(db.Books.has_cover == 1)
                 .filter(calibre_db.common_filters()))
        excluded = [int(item) for item in (exclude_ids or []) if item]
        if excluded:
            query = query.filter(~db.Books.id.in_(excluded))
        return query.order_by(func.random()).limit(limit).all()
    except Exception as error:
        log.debug("Discover picks unavailable: %s", error)
        return []


def discover_cards(limit=3, exclude_ids=None, hero_ids=None):
    """Random picks for the home panel. Hero books stay out of the fan."""
    heroes = {int(item) for item in (hero_ids or []) if item}
    skipped = {int(item) for item in (exclude_ids or []) if item} | heroes
    cards = []
    try:
        from ..cw_login import current_user
        from .home_rows import _catalog
        from .units import display_units

        user_id = int(getattr(current_user, "id", 0) or 0)
        units = [
            unit for unit in display_units(_catalog(user_id), user_id)
            if unit["id"] not in skipped and not (set(unit.get("member_ids") or []) & skipped)
        ]
        random.Random().shuffle(units)
        for unit in units:
            if len(cards) >= limit:
                break
            try:
                cards.append(_unit_card(unit))
            except Exception as error:
                log.debug("Discover card skipped: %s", error)
    except Exception as error:
        log.debug("Discover picks unavailable: %s", error)
    return cards


def _unit_card(unit):
    from .. import calibre_db, db

    from flask import url_for

    from .series_info import present
    from .units import sentence_case

    book = calibre_db.session.query(db.Books).filter(db.Books.id == int(unit["cover_id"])).first()
    card = _discover_card(book) if book is not None else {}
    if unit.get("kind") != "series":
        return card
    card["id"] = unit["id"]
    card["title"] = unit.get("title") or card.get("title") or ""
    card["author"] = unit.get("author_name") or card.get("author") or ""
    card["series"] = unit.get("count_label") or ""
    card["pages"] = unit.get("count_label") or ""
    card["read_time"] = unit.get("hours_label") or ""
    card["rating"] = unit.get("rating") or ""
    card["rating_count"] = unit.get("rating_count") or ""
    card["rating_source"] = unit.get("rating_source") or ""
    copy = present(unit.get("series_id"), unit.get("author_name") or "", unit.get("count") or 0, unit.get("minutes"))
    card["blurb"] = copy["excerpt"]
    card["blurb_rest"] = copy["rest"]
    card["source_name"] = copy["source_name"]
    card["source_url"] = copy["source_url"]
    card["url"] = unit.get("href") or card.get("url") or ""
    card["send"] = ""
    card["send_note"] = ""
    card["send_toast"] = ""
    card["view_label"] = _("View series")
    card["covers"] = [
        url_for("web.get_cover", book_id=int(cover_id), resolution="og")
        for cover_id in (unit.get("cover_ids") or [])
    ]
    card["accolades"] = _card_accolades(unit.get("member_ids") or [unit["id"]])
    card["kind"] = "series"
    return card


def _row_book_ids(row):
    found = []
    for book in (row or {}).get("books") or []:
        book_id = getattr(book, "id", None)
        if book_id:
            found.append(int(book_id))
    return found


def _face_heroes(heroes):
    """When a featured book belongs to a series, the hero speaks for the series."""
    from .series_info import present
    from .units import sentence_case, series_by_member

    index = series_by_member()
    for slide in heroes or []:
        book = slide.get("book") if isinstance(slide, dict) else None
        if book is None:
            continue
        unit = index.get(book.id)
        if unit:
            slide["headline"] = unit.get("title") or slide.get("headline") or ""
            slide["title"] = unit.get("title") or slide.get("title") or ""
            copy = present(unit.get("series_id"), unit.get("author_name") or "", unit.get("count") or 0, unit.get("minutes"))
            slide["blurb"] = copy["excerpt"]
            slide["blurb_rest"] = copy["rest"]
            slide["source_name"] = copy["source_name"]
            slide["source_url"] = copy["source_url"]
            slide["pages"] = unit.get("count_label") or ""
            slide["read_time"] = unit.get("hours_label") or ""
            slide["send_note"] = ""
            slide["send_toast"] = ""
            slide["send_label"] = ""
            slide["send_url"] = ""
            slide["action_url"] = unit.get("href") or ""
            slide["action_label"] = _("View series")
            slide["action_icon"] = "layers"
            slide["more_url"] = unit.get("href") or ""
            slide["plain_series"] = True
            slide["cover_book_id"] = unit.get("cover_id") or book.id
            slide["cover_ids"] = list(unit.get("cover_ids") or [])
            slide["series_line"] = ""
            slide["rating_value"] = unit.get("rating")
            slide["rating_count"] = unit.get("rating_count")
            slide["rating_source"] = unit.get("rating_source") or ""
            from .accolades import tags_for_ids
            slide["accolades"] = tags_for_ids(unit.get("member_ids") or [book.id], 2)
        slide["blurb"] = sentence_case(slide.get("blurb") or "")
    return heroes


def _hero_book_ids(heroes):
    found = []
    for slide in heroes or []:
        book = slide.get("book") if isinstance(slide, dict) else None
        if book is not None and getattr(book, "id", None):
            found.append(int(book.id))
    return found


def _discover_card(book):
    from flask import url_for

    from .heroes import _comment_excerpt
    from .ratings.service import rating_info
    from .reading import read_bits
    from .send import send_choice
    from .units import sentence_case

    authors = [author.name.replace("|", ", ") for author in (book.authors or [])]
    series = ""
    if book.series:
        series = _("Book %(index)s of %(name)s", index=_index_label(book.series_index), name=book.series[0].name)
    pages = ""
    read_time = ""
    for part in (read_bits(book.id) or "").split(", "):
        clean = part.replace("~", "").strip()
        if not clean:
            continue
        if "page" in clean:
            pages = clean
        else:
            read_time = clean
    rating = rating_info(book.id) or {}
    choice = send_choice(book)
    send_url = ""
    if choice:
        send_url = url_for(
            "web.send_to_ereader",
            book_id=book.id,
            book_format=choice["format"],
            convert=choice["convert"],
        )
    stamp = ""
    if getattr(book, "timestamp", None) is not None:
        try:
            stamp = book.timestamp.strftime("%Y%m%d%H%M%S")
        except Exception:
            stamp = ""
    return {
        "id": book.id,
        "title": book.title or "",
        "author": " & ".join(authors),
        "series": series,
        "pages": pages,
        "read_time": read_time,
        "rating": rating.get("value") or "",
        "rating_count": rating.get("count") or "",
        "rating_source": rating.get("source") or "",
        "blurb": sentence_case(_comment_excerpt(book)),
        "cover": url_for("web.get_cover", book_id=book.id, resolution="og", c=stamp),
        "url": url_for("web.show_book", book_id=book.id),
        "send": send_url,
        "accolades": _card_accolades(book.id),
    }


def _card_accolades(book_ids):
    from .accolades import tags_for_ids

    if isinstance(book_ids, int):
        book_ids = [book_ids]
    return tags_for_ids(book_ids, 2)


def _index_label(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    text = ("%.2f" % number).rstrip("0").rstrip(".")
    return text or "0"


def recent_books(limit=24):
    try:
        from .. import calibre_db, db
        return (calibre_db.session.query(db.Books)
                .filter(calibre_db.common_filters())
                .order_by(db.Books.timestamp.desc())
                .limit(limit)
                .all())
    except Exception as error:
        log.debug("Recent books unavailable: %s", error)
        return []


# Broad tags that should not get their own row. A book can appear in
# every real genre it is tagged with, so each shelf stays full.
_GENERIC_TAGS = {
    "fiction",
    "general",
    "general fiction",
    "literature",
    "novel",
    "novels",
    "books",
    "ebook",
    "ebooks",
    "kindle",
}


def heroes_or_fallback():
    slides = hero_slides()
    if slides:
        return slides
    picks = discover_books(1)
    if not picks:
        return []
    book = picks[0]
    from .heroes import _comment_excerpt
    return [{
        "id": 0,
        "kind": "book",
        "book": book,
        "title": book.title,
        "headline": book.title,
        "blurb": _comment_excerpt(book),
        "href_kind": "book",
    }]


def _tag_name(tag):
    return (tag.name or "").strip().casefold()


# Shelf headings. The books still come from the real tag.
_ROW_TITLES = {
    "fantasy": "Worlds with magic in them",
    "science fiction": "Worlds beyond this one",
    "action & adventure": "Stories that keep moving",
    "action and adventure": "Stories that keep moving",
    "epic": "Big worlds, long roads",
    "classics": "The ones people keep",
    "thrillers": "Hard to put down",
    "thriller": "Hard to put down",
    "space opera": "Empires among the stars",
    "historical": "Lives in another century",
    "litrpg": "Levels, loot, and last stands",
    "litrpg (literary role-playing game)": "Levels, loot, and last stands",
    "dark fantasy": "Magic with the lights off",
    "hard science fiction": "Where the science holds",
    "horror": "For a darker night",
    "romance": "Love in the story",
    "humorous": "Something lighter",
    "humour": "Something lighter",
    "humor": "Something lighter",
    "adventure": "The journey is the point",
    "alien contact": "First meetings",
    "dystopian": "When the future fails",
    "fairy tales; folk tales; legends & mythology": "Old stories, still sharp",
    "suspense": "Something is about to happen",
    "crime": "The case is open",
    "mystery": "Questions first",
    "literary": "Sentences worth slowing down for",
}


def _row_title(tag):
    name = _tag_name(tag)
    if name in _ROW_TITLES:
        return _ROW_TITLES[name]
    cleaned = (tag.name or "").strip()
    if "(" in cleaned:
        cleaned = cleaned.split("(", 1)[0].strip()
    if ";" in cleaned:
        cleaned = cleaned.split(";", 1)[0].strip()
    return cleaned or (tag.name or "").strip()


def genre_rows(row_count=8, per_row=24, minimum=2):
    try:
        from .. import calibre_db, db
        counts = (calibre_db.session.query(db.Tags, func.count(db.Books.id))
                  .join(db.books_tags_link, db.Tags.id == db.books_tags_link.c.tag)
                  .join(db.Books, db.Books.id == db.books_tags_link.c.book)
                  .filter(calibre_db.common_filters())
                  .group_by(db.Tags.id)
                  .order_by(func.count(db.Books.id).desc(), db.Tags.name.asc())
                  .all())
        ranked = []
        for tag, count in counts:
            if _tag_name(tag) in _GENERIC_TAGS or int(count) < minimum:
                continue
            ranked.append((tag, int(count)))
            if len(ranked) >= row_count:
                break
        if not ranked:
            return []
        wanted = {tag.id for tag, _count in ranked}
        books = (calibre_db.session.query(db.Books)
                 .filter(db.Books.tags.any(db.Tags.id.in_(list(wanted))))
                 .filter(calibre_db.common_filters())
                 .order_by(db.Books.timestamp.desc())
                 .all())
        buckets = {tag_id: [] for tag_id in wanted}
        for book in books:
            for tag in book.tags:
                bucket = buckets.get(tag.id)
                if bucket is not None and len(bucket) < per_row:
                    bucket.append(book)
        rows = []
        for tag, count in ranked:
            chosen = buckets[tag.id]
            if len(chosen) < minimum:
                continue
            rows.append({
                "tag": tag,
                "count": count,
                "books": chosen,
                "title": _row_title(tag),
            })
        return rows
    except Exception as error:
        log.debug("Genre rows unavailable: %s", error)
        return []


def collection_cards():
    try:
        from ..cw_login import current_user

        from .. import calibre_db, db, ub
        user_id = int(current_user.id) if current_user.is_authenticated else -1
        shelves = (ub.session.query(ub.Shelf)
                   .filter(or_(ub.Shelf.is_public == 1, ub.Shelf.user_id == user_id))
                   .order_by(ub.Shelf.name.asc())
                   .all())
        cards = []
        for shelf in shelves:
            link = shelf.books.order_by(ub.BookShelf.order.asc()).first()
            book = None
            if link is not None:
                book = (calibre_db.session.query(db.Books)
                        .filter(db.Books.id == link.book_id)
                        .first())
            count = shelf.books.count()
            if count:
                cards.append({"shelf": shelf, "book": book, "count": count})
        return cards
    except Exception as error:
        log.debug("Collections unavailable: %s", error)
        return []


def continue_series_books(limit=16):
    try:
        from ..cw_login import current_user

        from .. import calibre_db, db, ub
        if not current_user.is_authenticated or getattr(current_user, "is_anonymous", False):
            return []
        reads = (ub.session.query(ub.ReadBook)
                 .filter(ub.ReadBook.user_id == int(current_user.id))
                 .filter(ub.ReadBook.read_status.in_([
                     ub.ReadBook.STATUS_IN_PROGRESS,
                     ub.ReadBook.STATUS_FINISHED,
                 ]))
                 .order_by(ub.ReadBook.last_modified.desc())
                 .all())
        if not reads:
            return []
        books = (calibre_db.session.query(db.Books)
                 .filter(db.Books.id.in_([row.book_id for row in reads]))
                 .all())
        by_id = {book.id: book for book in books}
        chosen = []
        seen = set()
        for row in reads:
            book = by_id.get(row.book_id)
            if book is None or not book.series:
                continue
            series_id = book.series[0].id
            if series_id in seen:
                continue
            seen.add(series_id)
            if row.read_status == ub.ReadBook.STATUS_IN_PROGRESS:
                chosen.append(book)
            else:
                nxt = _next_in_series(series_id, book)
                if nxt is not None:
                    chosen.append(nxt)
            if len(chosen) >= limit:
                break
        return chosen
    except Exception as error:
        log.debug("Continue series unavailable: %s", error)
        return []


def _series_index(book):
    try:
        return float(book.series_index or 0)
    except (TypeError, ValueError):
        return 0.0


def _next_in_series(series_id, finished_book):
    from .. import calibre_db, db

    current = _series_index(finished_book)
    candidates = (calibre_db.session.query(db.Books)
                  .join(db.books_series_link, db.Books.id == db.books_series_link.c.book)
                  .filter(db.books_series_link.c.series == series_id)
                  .filter(calibre_db.common_filters())
                  .all())
    later = [book for book in candidates if _series_index(book) > current + 0.001]
    later.sort(key=_series_index)
    return later[0] if later else None
