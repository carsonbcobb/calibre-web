# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import re

import requests

from .base import Rating, RatingProvider


class OpenLibraryProvider(RatingProvider):
    name = "Open Library"
    slug = "openlibrary"

    def lookup(self, book):
        isbn = _isbn(book)
        if isbn:
            found = _search({"isbn": isbn})
            if found:
                return found
        title = (book.title or "").strip()
        if not title:
            return None
        params = {"title": title, "limit": 1}
        author = _author(book)
        if author:
            params["author"] = author
        return _search(params)


def _search(params):
    params = dict(params)
    params["fields"] = "key,title,ratings_average,ratings_count"
    params["limit"] = 1
    response = requests.get(
        "https://openlibrary.org/search.json",
        params=params,
        timeout=6,
        headers={"User-Agent": "Calibre-Web library UI"},
    )
    response.raise_for_status()
    docs = (response.json() or {}).get("docs") or []
    if not docs:
        return None
    doc = docs[0]
    average = doc.get("ratings_average")
    if average is None:
        return None
    key = doc.get("key") or ""
    url = ("https://openlibrary.org" + key) if key.startswith("/") else ""
    count = doc.get("ratings_count")
    return Rating(round(float(average), 2), int(count) if count else None, url)


def _isbn(book):
    for ident in getattr(book, "identifiers", []) or []:
        kind = (getattr(ident, "type", "") or "").lower()
        if kind in ("isbn", "isbn13", "isbn10"):
            digits = re.sub(r"[^0-9Xx]", "", ident.val or "")
            if len(digits) in (10, 13):
                return digits
    return ""


def _author(book):
    authors = getattr(book, "authors", None) or []
    if not authors:
        return ""
    return (authors[0].name or "").replace("|", ", ")
