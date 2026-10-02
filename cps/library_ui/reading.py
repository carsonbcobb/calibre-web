# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import os
import re
import zipfile
from datetime import datetime, timezone

from flask import g
from flask_babel import gettext as _

from .logger_helper import log
from .models import LibraryBookStat

# Comfortable fiction pace. 250 words a minute was reading like a sprint.
WORDS_PER_MINUTE = 175
WORDS_PER_PAGE = 250
_SKIP_EPUB = ("toc", "nav", "cover", "titlepage")


def read_bits(book_id):
    """Short label for cards, such as 320 pages, ~9 hr 8 min."""
    stat = _cached(book_id)
    pages = stat.page_count if stat is not None else None
    if not pages:
        pages = _hardcover_pages(book_id)
    if stat is None and not pages:
        return ""
    parts = []
    if pages:
        if pages == 1:
            parts.append(_("1 page"))
        else:
            parts.append(_("%(count)s pages", count=pages))
    label = _time_label(stat.word_count) if stat is not None else ""
    if label:
        parts.append(label)
    return ", ".join(parts)


def _hardcover_pages(book_id):
    try:
        from .. import ub
        from .models import HardcoverBook
        row = (ub.session.query(HardcoverBook)
               .filter(HardcoverBook.book_id == int(book_id))
               .one_or_none())
    except Exception:
        return None
    if row is None or row.error or not row.pages:
        return None
    return int(row.pages)


def scan_book(book_id):
    """Read an EPUB or PDF and cache counts. Does not write Calibre metadata."""
    from .. import calibre_db, config, db, ub

    book = calibre_db.session.query(db.Books).filter(db.Books.id == int(book_id)).first()
    if book is None:
        return None
    path, fmt = _book_file(book, config.get_book_path())
    if not path:
        return None
    try:
        if fmt == "epub":
            pages, words = _epub_counts(path)
        elif fmt == "pdf":
            pages, words = _pdf_counts(path)
        else:
            return None
    except Exception as error:
        log.debug("Reading scan failed for book %s: %s", book_id, error)
        return None
    row = ub.session.query(LibraryBookStat).filter(LibraryBookStat.book_id == book.id).one_or_none()
    if row is None:
        row = LibraryBookStat(book_id=book.id)
        ub.session.add(row)
    row.page_count = pages
    row.word_count = words
    row.source_format = fmt
    row.scanned_at = datetime.now(timezone.utc)
    ub.session_commit()
    try:
        from flask import has_request_context
        if has_request_context() and hasattr(g, "library_stat_map"):
            g.library_stat_map[book.id] = row
    except Exception:
        pass
    return row


def scan_all():
    from .. import calibre_db, db

    ids = [row[0] for row in calibre_db.session.query(db.Books.id).all()]
    done = 0
    for book_id in ids:
        if scan_book(book_id):
            done += 1
    return done, len(ids)


def _cached(book_id):
    try:
        mapping = getattr(g, "library_stat_map", None)
        if mapping is None:
            from .. import ub
            rows = ub.session.query(LibraryBookStat).all()
            mapping = {row.book_id: row for row in rows}
            g.library_stat_map = mapping
        return mapping.get(int(book_id))
    except Exception:
        return None


def _time_label(words):
    if not words:
        return ""
    minutes = int(round(float(words) / WORDS_PER_MINUTE))
    if minutes < 1:
        minutes = 1
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return _("~%(hours)s hr %(minutes)s min", hours=hours, minutes=mins)
    if hours:
        return _("~%(hours)s hr", hours=hours)
    return _("~%(minutes)s min", minutes=mins)


def _book_file(book, root):
    if not book or not book.path or not root:
        return None, None
    ranked = []
    for item in book.data or []:
        fmt = (item.format or "").lower()
        if fmt not in ("epub", "pdf"):
            continue
        path = os.path.join(root, book.path, item.name + "." + fmt)
        if os.path.isfile(path):
            ranked.append((0 if fmt == "epub" else 1, path, fmt))
    if not ranked:
        return None, None
    ranked.sort()
    return ranked[0][1], ranked[0][2]


def _epub_counts(path):
    words = 0
    pages = None
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            lower = name.lower()
            if lower.endswith(".opf"):
                pages = _pages_from_opf(archive.read(name)) or pages
            if not lower.endswith((".xhtml", ".html", ".htm")):
                continue
            base = os.path.basename(lower)
            if any(skip in base for skip in _SKIP_EPUB):
                continue
            text = _html_text(archive.read(name))
            words += len(re.findall(r"\w+", text, flags=re.UNICODE))
    if pages is None and words:
        pages = max(1, int(round(words / float(WORDS_PER_PAGE))))
    return pages, words or None


def _pages_from_opf(raw):
    text = raw.decode("utf-8", "ignore")
    patterns = (
        r"calibre:pages[\"'][^>]*content=[\"'](\d+)",
        r"content=[\"'](\d+)[\"'][^>]*calibre:pages",
        r"numberOfPages[\"'][^>]*>(\d+)<",
        r"scheme=[\"']page[\"'][^>]*content=[\"'](\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return int(match.group(1))
    return None


def _html_text(raw):
    text = raw.decode("utf-8", "ignore")
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return text


def _pdf_counts(path):
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = len(reader.pages)
    words = 0
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        words += len(re.findall(r"\w+", text, flags=re.UNICODE))
    return pages or None, words or None
