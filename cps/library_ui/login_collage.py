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
_IMAGES = {}
_TTL = 120
_SLOTS = 18
_MAX_EDGE = 280


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
                image.save(buffer, format="JPEG", quality=72)
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
