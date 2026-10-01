# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from datetime import datetime, timezone

from flask_babel import gettext as _
from sqlalchemy.exc import OperationalError

from .models import LibraryAsset

MAX_BYTES = 2 * 1024 * 1024
KINDS = ("logo", "favicon")


def sniff_image(data):
    """Return a mime type when the bytes look like a real image."""
    if not data:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    return None


def get_asset(kind):
    from .. import ub

    if kind not in KINDS:
        return None
    try:
        return ub.session.query(LibraryAsset).filter(LibraryAsset.kind == kind).one_or_none()
    except OperationalError:
        ub.session.rollback()
        return None


def asset_urls():
    """Public URLs for assets that exist, with a cache busting query."""
    from flask import url_for

    urls = {"logo": "", "favicon": ""}
    for kind in KINDS:
        asset = get_asset(kind)
        if asset is None:
            continue
        version = ""
        if asset.updated_at:
            try:
                version = str(int(asset.updated_at.timestamp()))
            except Exception:
                version = ""
        urls[kind] = url_for("library_ui.brand_asset", kind=kind, v=version)
    return urls


def save_upload(kind, file_storage):
    """Store an uploaded image. Returns an error string, or None on success."""
    from .. import ub

    if kind not in KINDS:
        return _("Unknown image.")
    if file_storage is None or not file_storage.filename:
        return _("Choose an image file first.")
    data = file_storage.read()
    if not data:
        return _("Choose an image file first.")
    if len(data) > MAX_BYTES:
        return _("That file is too large. The limit is 2 MB.")
    mime = sniff_image(data)
    if not mime:
        return _("That file is not a supported image. Use PNG, JPEG, GIF, WebP, or ICO.")

    row = ub.session.query(LibraryAsset).filter(LibraryAsset.kind == kind).one_or_none()
    if row is None:
        row = LibraryAsset(kind=kind, mime=mime, data=data)
        ub.session.add(row)
    else:
        row.mime = mime
        row.data = data
    row.updated_at = datetime.now(timezone.utc)
    ub.session_commit("Library UI %s updated" % kind)
    return None


def delete_asset(kind):
    from .. import ub

    if kind not in KINDS:
        return
    ub.session.query(LibraryAsset).filter(LibraryAsset.kind == kind).delete()
    ub.session_commit("Library UI %s removed" % kind)
