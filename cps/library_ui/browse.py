# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Genre and series browse pages. Reads Calibre data and caches it per user."""

import random
import time
from datetime import datetime

from flask import abort, request, url_for
from flask_babel import gettext as _

from .home_rows import _catalog
from .logger_helper import log
from .reading import WORDS_PER_MINUTE

_CACHE = {}
_TTL = 600
_ROW_MAX = 20


def render_genres_home():
    try:
        payload = _genres_home()
    except Exception as error:
        log.debug("Browse page unavailable: %s", error)
        payload = None
    payload = payload or {"hero": None, "genres": [], "pills": []}
    books = _books_by_id(_ids_in(payload))
    genres = _rows(payload["genres"], books)
    hero = _hero(payload.get("hero"), books)
    _decorate(genres, hero)
    return _render(
        "library_genres.html",
        _("Genres"),
        "genres",
        genres=genres,
        hero=hero,
        pills=payload.get("pills") or [],
    )


def render_genre_page(name):
    try:
        payload = _genre_page(name)
    except Exception as error:
        log.debug("Browse page unavailable: %s", error)
        payload = None
    if payload is None:
        abort(404)
    books = _books_by_id(_ids_in(payload))
    hero = _hero(payload.get("hero"), books)
    rows = _rows(payload["rows"], books)
    grid = [books[book_id] for book_id in payload["grid"] if book_id in books]
    _decorate(rows, hero, grid)
    return _render(
        "library_genre.html",
        payload["name"],
        "genre",
        genre_name=payload["name"],
        hero=hero,
        rows=rows,
        grid=grid,
        grid_title=payload.get("grid_title") or _("All books"),
        grid_label=payload.get("grid_label") or payload["name"],
        grid_subtitle=payload.get("grid_subtitle") or "",
        grid_count=payload.get("grid_count") or len(payload.get("grid") or []),
        sort=payload["sort"],
        pills=payload["pills"],
    )


def render_series_home():
    payload = _remember("series-home", _series_home) or {"hero": None, "series": []}
    books = _books_by_id([payload["hero"]["book_id"]] if payload.get("hero") else [])
    hero = _hero(payload.get("hero"), books) if payload.get("hero") else None
    return _render(
        "library_series.html",
        _("Series"),
        "serieshome",
        hero=hero,
        series=payload["series"],
    )


def render_series_detail(series_id):
    payload = _remember("series:%s" % int(series_id), lambda: _series_detail(int(series_id)))
    if payload is None:
        abort(404)
    books = _books_by_id(_ids_in(payload))
    from .series_info import form_text

    description, source_url = form_text(series_id)
    return _render(
        "library_series_detail.html",
        payload["name"],
        "seriesbook",
        series_id=int(series_id),
        series_description=description,
        series_source_url=source_url,
        hero=_hero(payload.get("hero"), books),
        volumes=[books[book_id] for book_id in payload["volumes"] if book_id in books],
        more=_decorate_more(_rows([payload["more"]], books)[0] if payload.get("more") else None),
    )


def _render(template, title, page, **kwargs):
    from ..render_template import render_title_template

    return render_title_template(template, title=title, page=page, **kwargs)


def _remember(suffix, builder):
    from ..cw_login import current_user

    from .units import metadata_mtime

    key = (
        suffix,
        int(getattr(current_user, "id", 0) or 0),
        str(getattr(current_user, "filter_language", lambda: "all")()),
        metadata_mtime(),
    )
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    try:
        value = builder()
    except Exception as error:
        log.debug("Browse page unavailable: %s", error)
        value = None
    _CACHE[key] = (now, value)
    if len(_CACHE) > 48:
        oldest = sorted(_CACHE, key=lambda item: _CACHE[item][0])[:-24]
        for item in oldest:
            _CACHE.pop(item, None)
    return value


def _decorate(rows, hero=None, grid=None):
    from .units import decorate_books

    for row in rows or []:
        decorate_books(row.get("books"))
    decorate_books(grid)
    if hero and hero.get("book"):
        decorate_books([hero["book"]])


def _decorate_more(row):
    if row and row.get("books"):
        from .units import decorate_books
        decorate_books(row["books"])
    return row


def _genres_home():
    from .genre_rows import build_landing
    from .units import display_units

    catalog, names = _world()
    page = build_landing(display_units(catalog), names)
    hero = None
    pick = _solo_book(page.get("hero_book"), catalog)
    if pick:
        hero = _book_hero(
            pick,
            _("Featured in %(genre)s", genre=page.get("hero_genre") or ""),
            pick["title"],
            pick.get("blurb_text") or "",
            meta=_book_meta(pick),
            system=True,
        )
        _attach_quotes(hero, pick.get("id"))
    return {
        "hero": hero,
        "genres": page["rows"],
        "pills": page["pills"],
    }


def _genre_page(name):
    from .genre_rows import build_genre_page
    from .units import display_units

    catalog, names = _world()
    mode = request.args.get("sort") or "added"
    page = build_genre_page(name, display_units(catalog), names, mode)
    if page is None:
        return None
    pick = _solo_book(page["hero_book"], catalog)
    hero = _book_hero(
        pick,
        _("Featured in %(genre)s", genre=page["name"]),
        pick["title"],
        pick.get("blurb_text") or "",
        meta=_book_meta(pick),
        system=True,
    )
    _attach_quotes(hero, pick.get("id"))
    return {
        "name": page["name"],
        "hero": hero,
        "rows": page["rows"],
        "grid": page["grid"],
        "grid_title": page["grid_title"],
        "grid_label": page["grid_label"],
        "grid_subtitle": page["grid_subtitle"],
        "grid_count": page["grid_count"],
        "sort": page["sort"],
        "pills": page["pills"],
    }


def _series_home():
    catalog, _names, stats = _world(stats=True)
    cards = _series_cards(catalog, stats)
    hero = None
    if cards:
        rng = random.Random("series:%s" % datetime.now().strftime("%Y%m%d"))
        card = rng.choice(cards)
        hero = dict(card["hero"])
    return {"hero": hero, "series": [card["public"] for card in cards]}


def _series_detail(series_id):
    catalog, _names, stats = _world(stats=True)
    cards = {card["public"]["id"]: card for card in _series_cards(catalog, stats)}
    card = cards.get(int(series_id))
    if card is None:
        return None
    members = card["members"]
    first = members[0]
    author_ids = first["author_ids"]
    from .units import display_units

    others = [
        unit for unit in display_units(catalog)
        if unit.get("series_id") != series_id and author_ids and (unit.get("author_ids") & author_ids)
    ]
    unread = [book for book in members if book["read"] != 1]
    focus = unread[0] if unread else first
    started = any(book["read"] in (1, 2) for book in members)
    minutes = _totals(members, stats)[1]
    shown = dict(first)
    shown["cover_ids"] = [book["id"] for book in members[:4]]
    shown["member_ids"] = [book["id"] for book in members]
    shown["count"] = len(members)
    shown["minutes"] = minutes
    hero = _book_hero(
            shown,
            _("Series"),
            card["public"]["name"],
            "",
            meta=_series_meta(len(members), minutes),
            send_book=focus,
            send_label=_("Continue Series") if started else _("Start Series"),
            send_note=_("Sends Book %(num)s: %(title)s", num=_book_num(focus["series_index"]), title=focus["title"]),
            plain_series=True,
            large=True,
            system=True,
        )
    _series_rating(hero, members)
    _attach_series_quotes(hero, members)
    more = None
    if others:
        more = {
            "id": "author",
            "title": _("More from this author"),
            "subtitle": "",
            "book_ids": [book["id"] for book in others[:_ROW_MAX]],
        }
    return {
        "name": card["public"]["name"],
        "hero": hero,
        "volumes": [book["id"] for book in members],
        "more": more,
    }


def _series_cards(catalog, stats):
    groups = {}
    for book in catalog:
        if book["series_id"]:
            groups.setdefault(book["series_id"], []).append(book)
    cards = []
    for series_id, members in groups.items():
        members.sort(key=lambda book: book["series_index"])
        first = members[0]
        finished = sum(1 for book in members if book["read"] == 1)
        started = any(book["read"] in (1, 2) for book in members)
        if finished >= len(members):
            state = "done"
        elif started:
            state = "progress"
        else:
            state = "new"
        if finished:
            progress = int(round(100.0 * finished / len(members)))
            progress_label = _("%(done)s of %(total)s read", done=finished, total=len(members))
        elif started:
            progress = max(8, int(round(100.0 / len(members))))
            progress_label = _("In progress")
        else:
            progress = 0
            progress_label = ""
        updated = max((book["stamp"] or datetime.min) for book in members)
        _pages_total, minutes = _totals(members, stats)
        shown = dict(first)
        shown["cover_ids"] = [book["id"] for book in members[:4]]
        shown["member_ids"] = [book["id"] for book in members]
        shown["series_id"] = series_id
        shown["count"] = len(members)
        shown["minutes"] = minutes
        shown["kind"] = "series"
        shown["href"] = "/series/%s" % series_id
        hero = _book_hero(
            shown,
            _("Series"),
            first.get("series_name") or first["title"],
            first.get("blurb_text") or "",
            meta=_series_meta(len(members), minutes),
            action_url="/series/%s" % series_id,
            action_label=_("Continue Series") if started else _("Start Series"),
            plain_series=True,
            system=True,
        )
        _series_rating(hero, members)
        _attach_series_quotes(hero, members)
        public = {
            "id": series_id,
            "name": hero["title"],
            "author": first["author_name"],
            "count": len(members),
            "count_label": _book_count(len(members)),
            "href": "/series/%s" % series_id,
            "covers": [_cover(book["id"]) for book in members[:3]],
            "progress": progress,
            "progress_label": progress_label,
            "state": state,
            "updated": updated.strftime("%Y%m%d%H%M%S") if isinstance(updated, datetime) else "",
        }
        cards.append({"public": public, "hero": hero, "members": members})
    cards.sort(key=lambda card: card["public"]["name"].lower())
    stored = _series_table_count()
    log.info("Series page counts: %s in metadata.db, %s rendered", stored, len(cards))
    return cards


def _series_table_count():
    try:
        from .. import calibre_db, db

        return int(calibre_db.session.query(db.Series.id).count())
    except Exception as error:
        log.debug("Series table count unavailable: %s", error)
        return None


def _book_count(count):
    if int(count) == 1:
        return _("1 book")
    return _("%(count)s books", count=count)


def _book_num(index):
    try:
        number = float(index or 0)
    except (TypeError, ValueError):
        number = 0
    text = ("%.2f" % number).rstrip("0").rstrip(".")
    return text or "1"


def _solo_book(pick, catalog):
    """Genre heroes show one book. A series pick becomes its first volume."""
    if not pick or pick.get("kind") != "series":
        return pick
    members = pick.get("member_ids") or []
    first_id = members[0] if members else pick.get("cover_id")
    source = None
    for book in catalog or []:
        if book.get("id") == first_id:
            source = book
            break
    if source is None:
        solo = dict(pick)
        solo["kind"] = "book"
        solo["id"] = first_id or pick.get("id")
        solo["title"] = (pick.get("member_titles") or [pick.get("title") or ""])[0]
        solo["cover_ids"] = []
        solo["href"] = ""
        solo["blurb_text"] = pick.get("blurb_text") or ""
        return solo
    from .units import _book_unit, _page_counts

    return _book_unit(source, _page_counts())


def _book_meta(book):
    from .units import reading_time

    return _join([_pages(book.get("pages")), reading_time(book.get("minutes"))])


def _series_meta(count, minutes):
    from .units import _hours

    return _join([_book_count(count), _hours(minutes)])


def _series_rating(hero, members):
    ratings = []
    for book in members or []:
        if book.get("rating") is not None:
            ratings.append(float(book["rating"]))
    if not ratings or not hero:
        return
    hero["rating_value"] = round(sum(ratings) / len(ratings), 1)
    hero["rating_count"] = len(ratings)
    hero["rating_source"] = "Series average"


def _attach_quotes(hero, book_id):
    from .hero_panel import book_quotes

    quotes = book_quotes(book_id)
    if quotes and hero:
        hero["panel"] = {"mode": "quotes", "quotes": quotes}


def _attach_series_quotes(hero, members):
    from .hero_panel import series_quotes

    quotes = series_quotes(members)
    if quotes and hero:
        hero["panel"] = {"mode": "quotes", "quotes": quotes}


def _book_hero(book, kicker, title, blurb, meta="", send_book=None, send_label="", send_note="", action_url="", action_label="", plain_series=False, large=False, system=False, clamp_blurb=True):
    from .units import sentence_case

    action_icon = ""
    if book.get("kind") == "series" and not action_url:
        title = book.get("title") or title
        meta = book.get("count_label") or meta
        plain_series = True
        if send_label:
            send_book = {"id": book.get("next_id")}
            send_note = book.get("send_note") or send_note
        else:
            action_url = book.get("href") or ""
            action_label = _("View series")
            action_icon = "layers"
    target = send_book or book
    send_url = "" if action_url else (_send_url(target["id"]) if send_label else "")
    more_url = ""
    more_label = ""
    more_primary = False
    if action_url:
        send_label = ""
        send_note = ""
    elif send_label and not send_url:
        more_url = url_for("web.show_book", book_id=target["id"])
        more_label = send_label
        send_label = ""
        more_primary = True
    elif not send_label:
        more_url = url_for("web.show_book", book_id=book["id"])
        more_label = _("More info")
    if book.get("kind") == "series" and book.get("href"):
        more_url = book["href"]
        more_label = _("More info")
        more_primary = False
    copy = None
    if large and (plain_series or book.get("kind") == "series") and book.get("series_id"):
        from .series_info import present

        count = book.get("count") or book.get("series_len") or 0
        copy = present(book.get("series_id"), book.get("author_name") or "", count, book.get("minutes"))
        if copy.get("factual"):
            blurb = ""
            copy = None
        else:
            blurb = copy["excerpt"]
            if not clamp_blurb and copy.get("rest"):
                blurb = "%s %s" % (blurb, copy["rest"])
        if book.get("series_id"):
            more_url = "/series/%s" % int(book["series_id"])
        if large:
            more_url = ""
    payload = {
        "book_id": book["id"],
        "cover_book_id": book.get("cover_id") or book["id"],
        "kicker": kicker,
        "title": title or book["title"],
        "headline": title or book["title"],
        "blurb": blurb if copy else sentence_case(blurb or ""),
        "blurb_rest": "",
        "source_name": "",
        "source_url": "",
        "meta": meta,
        "pages": "" if system else (book.get("count_label") or ""),
        "read_time": "" if system else (book.get("hours_label") or ""),
        "rating_value": book.get("rating") if book.get("rating") is not None else "",
        "rating_count": book.get("rating_count"),
        "rating_source": book.get("rating_source") or "",
        "send_url": send_url,
        "send_label": send_label,
        "send_note": "",
        "send_toast": ("Sent %s" % (book.get("next_title") or "")) if book.get("kind") == "series" else "",
        "action_url": action_url,
        "action_label": action_label,
        "action_icon": action_icon,
        "cover_ids": list(book.get("cover_ids") or []) if plain_series else [],
        "more_url": more_url,
        "more_label": more_label,
        "more_primary": more_primary,
        "plain_series": plain_series,
        "large": large,
        "system": system,
        "clamp_blurb": bool(system and clamp_blurb and blurb),
    }
    from .accolades import tags_for_ids

    tags = tags_for_ids(book.get("member_ids") or [book.get("id")], 2)
    folded = (meta or "").casefold()
    payload["accolades"] = [tag for tag in tags if (tag.get("label") or "").casefold() not in folded][:2]
    return payload


def _world(stats=False):
    from .. import calibre_db, db

    catalog = _catalog(int(_user_id()))
    names = {}
    try:
        for tag in calibre_db.session.query(db.Tags).all():
            names[tag.id] = tag.name or ""
    except Exception as error:
        log.debug("Genre names unavailable: %s", error)
    series_names = {}
    try:
        for series in calibre_db.session.query(db.Series).all():
            series_names[series.id] = series.name or ""
    except Exception as error:
        log.debug("Series names unavailable: %s", error)
    for book in catalog:
        book["series_name"] = series_names.get(book["series_id"]) or ""
    if not stats:
        return catalog, names
    return catalog, names, _stat_map()


def _stat_map():
    found = {}
    try:
        from .. import ub
        from .models import LibraryBookStat

        for row in ub.session.query(LibraryBookStat).all():
            found[row.book_id] = row
    except Exception as error:
        log.debug("Reading stats unavailable: %s", error)
    return found


def _totals(members, stats):
    pages = 0
    minutes = 0
    for book in members:
        row = stats.get(book["id"])
        if row is not None and row.page_count:
            pages += int(row.page_count)
        if book["minutes"]:
            minutes += book["minutes"]
        elif row is not None and row.word_count:
            minutes += int(round(float(row.word_count) / WORDS_PER_MINUTE))
    return pages, minutes


def _ids_in(payload):
    if not payload:
        return []
    found = []
    hero = payload.get("hero") or {}
    if hero.get("book_id"):
        found.append(hero["book_id"])
    for row in payload.get("genres") or payload.get("rows") or []:
        found.extend(row.get("book_ids") or [])
    found.extend(payload.get("grid") or [])
    found.extend(payload.get("volumes") or [])
    more = payload.get("more") or {}
    found.extend(more.get("book_ids") or [])
    return found


def _books_by_id(ids):
    if not ids:
        return {}
    from .. import calibre_db, db

    rows = calibre_db.session.query(db.Books).filter(db.Books.id.in_(list(set(ids)))).all()
    return {book.id: book for book in rows}


def _row_title(row):
    for key in ("title", "name", "genre"):
        value = row.get(key)
        if value:
            return value
    return ""


def _rows(rows, books):
    ready = []
    for row in rows or []:
        try:
            if not isinstance(row, dict):
                continue
            title = _row_title(row)
            chosen = [books[book_id] for book_id in row.get("book_ids") or [] if book_id in books]
            if not title or not chosen:
                continue
            href = row.get("href") or row.get("see_all_url") or ""
            ready.append({
                "id": row.get("id") if row.get("id") is not None else row.get("slug") or "",
                "slug": row.get("slug") if row.get("slug") is not None else row.get("id") or "",
                "label": row.get("label") or "",
                "title": title,
                "subtitle": row.get("subtitle") or "",
                "count": row.get("count"),
                "href": href,
                "see_all_url": row.get("see_all_url") or href,
                "books": chosen,
            })
        except Exception as error:
            label = row.get("id") if isinstance(row, dict) else row
            log.error("Browse row skipped: %s (%s)", label, error)
    return ready


def _hero(data, books):
    if not data:
        return None
    book = books.get(data.get("book_id"))
    if book is None:
        return None
    merged = dict(data)
    merged["book"] = book
    return merged


def _cover(book_id):
    return url_for("web.get_cover", book_id=book_id, resolution="og")


def _send_url(book_id):
    from .. import calibre_db, db
    from .send import send_choice

    book = calibre_db.session.query(db.Books).filter(db.Books.id == int(book_id)).first()
    choice = send_choice(book)
    if not choice:
        return ""
    return url_for(
        "web.send_to_ereader",
        book_id=book.id,
        book_format=choice["format"],
        convert=choice["convert"],
    )


def _clock(minutes):
    minutes = int(round(minutes or 0))
    if minutes <= 0:
        return ""
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return _("%(hours)s hr %(minutes)s min", hours=hours, minutes=mins)
    if hours:
        return _("%(hours)s hr", hours=hours)
    return _("%(minutes)s min", minutes=minutes)


def _pages(count):
    count = int(count or 0)
    if count <= 0:
        return ""
    if count == 1:
        return _("1 page")
    return _("%(count)s pages", count=count)


def _join(parts):
    return ", ".join(part for part in parts if part)


def _user_id():
    from ..cw_login import current_user

    return int(getattr(current_user, "id", 0) or 0)
