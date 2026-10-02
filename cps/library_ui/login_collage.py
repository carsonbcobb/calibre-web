# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import os
import time
from io import BytesIO

from .logger_helper import log

_CACHE = {"at": 0, "ids": []}
_CATALOG = {"at": 0, "ok": False, "rows": []}
_IMAGES = {}
_TTL = 120
_CATALOG_TTL = 3600
_SLOTS = 18
_MAX_EDGE = 200
_QUALITY = 70


def covers_enabled():
    """Admin switch for the public login collage. On unless turned off."""
    from .store import get_setting

    value = str(get_setting("login_covers", "1") or "1").strip().lower()
    return value not in ("0", "false", "off", "no")


def cover_catalog():
    """Every visible book with a real cover. Cached for an hour. No titles or names."""
    now = time.time()
    if _CATALOG["ok"] and now - _CATALOG["at"] < _CATALOG_TTL:
        return _CATALOG["rows"]
    rows = _load_catalog()
    _CATALOG["at"] = now
    _CATALOG["ok"] = True
    _CATALOG["rows"] = rows
    return rows


def catalog_payload():
    from flask import url_for

    if not covers_enabled():
        return []
    payload = []
    for row in cover_catalog():
        payload.append({
            "id": row["id"],
            "url": url_for("library_ui.login_thumb", book_id=row["id"]),
            "genre": row["genre"],
            "series": row["series"],
            "author": row["author"],
        })
    return payload


def thumbnail_response(book_id):
    """About 200px wide, cached on disk. Reuses a Calibre Web thumbnail when one exists."""
    from flask import abort, send_file

    if not covers_enabled():
        abort(404)
    allowed = {row["id"] for row in cover_catalog()}
    if int(book_id) not in allowed:
        abort(404)
    try:
        from .. import calibre_db, db
        book = calibre_db.session.query(db.Books).filter(db.Books.id == int(book_id)).first()
    except Exception as error:
        log.debug("Login thumbnail lookup failed: %s", error)
        book = None
    if book is None:
        abort(404)
    existing = _existing_thumb(book)
    if existing:
        response = send_file(existing, mimetype="image/jpeg")
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response
    path, mime = _ensure_thumb(book)
    if not path:
        abort(404)
    response = send_file(path, mimetype=mime)
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


def _load_catalog():
    rows = []
    try:
        from .. import calibre_db, config, db
        from .home_rows import _canonical

        if calibre_db.session is None:
            return []
        books = (calibre_db.session.query(db.Books)
                 .filter(db.Books.has_cover == 1)
                 .filter(calibre_db.common_filters())
                 .all())
        for book in books:
            if not _has_real_cover(config, book):
                continue
            genre = ""
            for tag in book.tags or []:
                name = _canonical(tag.name)
                if name:
                    genre = name
                    break
            series_id = book.series[0].id if book.series else None
            author_id = book.authors[0].id if book.authors else None
            try:
                series_index = float(book.series_index or 0) if series_id else 0
            except (TypeError, ValueError):
                series_index = 0
            rows.append({
                "id": int(book.id),
                "genre": genre,
                "series": int(series_id) if series_id else None,
                "series_index": series_index,
                "author": int(author_id) if author_id else None,
            })
    except Exception as error:
        log.debug("Login cover catalog unavailable: %s", error)
        return []
    return _one_cover_per_series(rows)


def _one_cover_per_series(rows):
    """A multi book series contributes the first book's cover once."""
    singles = []
    best = {}
    for row in rows:
        series_id = row.get("series")
        if not series_id:
            singles.append(row)
            continue
        current = best.get(series_id)
        if current is None or row.get("series_index", 0) < current.get("series_index", 0):
            best[series_id] = row
    kept = list(best.values())
    # A series with one visible cover stays. Groups of one are already the only cover.
    return singles + kept


def _has_real_cover(config, book):
    if config.config_use_google_drive:
        return bool(book and book.has_cover)
    if not book or not book.path:
        return False
    path = os.path.join(config.get_book_path(), book.path, "cover.jpg")
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 800
    except OSError:
        return False


def _existing_thumb(book):
    try:
        from .. import fs
        from ..constants import CACHE_TYPE_THUMBNAILS, COVER_THUMBNAIL_SMALL
        from ..helper import get_book_cover_thumbnail

        thumb = get_book_cover_thumbnail(book, COVER_THUMBNAIL_SMALL)
        if thumb is None:
            return None
        cache = fs.FileSystem()
        if not cache.get_cache_file_exists(thumb.filename, CACHE_TYPE_THUMBNAILS):
            return None
        return cache.get_cache_file_path(thumb.filename, CACHE_TYPE_THUMBNAILS)
    except Exception as error:
        log.debug("Existing thumbnail skipped: %s", error)
        return None


def _ensure_thumb(book):
    from .. import config

    path = os.path.join(config.get_book_path(), book.path, "cover.jpg")
    try:
        mtime = int(os.path.getmtime(path))
    except OSError:
        return None, ""
    folder = _thumb_dir()
    if not folder:
        return None, ""
    webp = os.path.join(folder, "%s-%s.webp" % (book.id, mtime))
    jpeg = os.path.join(folder, "%s-%s.jpg" % (book.id, mtime))
    if os.path.isfile(webp) and os.path.getsize(webp) > 0:
        return webp, "image/webp"
    if os.path.isfile(jpeg) and os.path.getsize(jpeg) > 0:
        return jpeg, "image/jpeg"
    try:
        from PIL import Image
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((_MAX_EDGE, int(_MAX_EDGE * 1.5)))
            try:
                image.save(webp, format="WEBP", quality=_QUALITY)
                _drop_old_thumbs(folder, book.id, webp)
                return webp, "image/webp"
            except Exception:
                image.save(jpeg, format="JPEG", quality=_QUALITY)
                _drop_old_thumbs(folder, book.id, jpeg)
                return jpeg, "image/jpeg"
    except Exception as error:
        log.debug("Could not build login thumbnail: %s", error)
        return None, ""


def _thumb_dir():
    try:
        from .. import fs
        return fs.FileSystem().get_cache_dir("login-thumbs")
    except Exception as error:
        log.debug("Login thumbnail folder unavailable: %s", error)
        return None


def _drop_old_thumbs(folder, book_id, keep):
    prefix = "%s-" % book_id
    try:
        for name in os.listdir(folder):
            if name.startswith(prefix) and os.path.join(folder, name) != keep:
                os.remove(os.path.join(folder, name))
    except OSError:
        return


def collage_ids():
    """Recent books with covers, respecting the guest user's view limits."""
    now = time.time()
    if now - _CACHE["at"] < _TTL:
        return _CACHE["ids"]
    ids = []
    try:
        from .. import calibre_db, db
        if calibre_db.session is not None:
            rows = (calibre_db.session.query(db.Books.id)
                    .filter(db.Books.has_cover == 1)
                    .filter(calibre_db.common_filters())
                    .order_by(db.Books.timestamp.desc())
                    .limit(_SLOTS)
                    .all())
            ids = [row[0] for row in rows]
    except Exception as error:
        log.debug("Login collage unavailable: %s", error)
        ids = []
    _CACHE["at"] = now
    _CACHE["ids"] = ids
    return ids


def book_for_slot(slot):
    ids = collage_ids()
    if slot < 0 or slot >= len(ids):
        return None
    try:
        from .. import calibre_db, db
        return calibre_db.session.query(db.Books).filter(db.Books.id == ids[slot]).first()
    except Exception as error:
        log.debug("Login collage book missing: %s", error)
        return None


def cover_response(book):
    """Small JPEG for the login collage. Reads the cover and does not write it back."""
    from flask import Response

    from .. import config
    from ..constants import COVER_THUMBNAIL_MEDIUM
    from ..helper import get_book_cover_internal

    if config.config_use_google_drive or not book or not book.path:
        return get_book_cover_internal(book, resolution=COVER_THUMBNAIL_MEDIUM)

    path = os.path.join(config.get_book_path(), book.path, "cover.jpg")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return get_book_cover_internal(book, resolution=COVER_THUMBNAIL_MEDIUM)

    key = (book.id, mtime)
    cached = _IMAGES.get(key)
    if cached is None:
        try:
            from PIL import Image
            with Image.open(path) as image:
                image = image.convert("RGB")
                image.thumbnail((_MAX_EDGE, int(_MAX_EDGE * 1.5)))
                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=_QUALITY)
                cached = buffer.getvalue()
        except Exception as error:
            log.debug("Could not shrink login cover: %s", error)
            return get_book_cover_internal(book, resolution=COVER_THUMBNAIL_MEDIUM)
        if len(_IMAGES) > 40:
            _IMAGES.clear()
        _IMAGES[key] = cached

    response = Response(cached, mimetype="image/jpeg")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response
