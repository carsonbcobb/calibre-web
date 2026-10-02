# -*- coding: utf-8 -*-

"""Open Library work ratings. Server side only."""

import requests

from .base import Rating, RatingProvider
from .match import confident, identifiers, series_query

_UA = "DeadMediaSociety/1.0 (local library catalog; ratings)"


class OpenLibraryProvider(RatingProvider):
    name = "Open Library"
    slug = "openlibrary"

    def lookup(self, book):
        ids = identifiers(book)
        for key in ids["openlibrary"]:
            work = key if key.startswith("/works/") else ""
            if work:
                found = _work_ratings(work)
                if found is not None:
                    return found
        for isbn in ids["isbn"]:
            found = _isbn(isbn)
            if found is not None:
                return found
        title = (book.title or "").strip()
        author = _author(book)
        if title:
            found = _search(title, author)
            if found is not None:
                return found
        series = ""
        index = None
        if getattr(book, "series", None):
            series = book.series[0].name or ""
            index = getattr(book, "series_index", None)
        query = series_query(series, index)
        if query:
            found = _search(query, author, wanted_title=title or query)
            if found is not None:
                return found
        if not ids["isbn"] and not ids["openlibrary"] and not title:
            return Rating(reason="no identifier")
        return Rating(reason="title mismatch" if title else "no results")


def _isbn(isbn):
    try:
        response = requests.get(
            "https://openlibrary.org/isbn/%s.json" % isbn,
            headers={"User-Agent": _UA},
            timeout=12,
        )
    except requests.RequestException:
        return Rating(reason="request error")
    if response.status_code == 404:
        return None
    if response.status_code == 429:
        return Rating(reason="rate limited")
    if response.status_code >= 400:
        return Rating(reason="request error")
    works = (response.json() or {}).get("works") or []
    if not works:
        return None
    key = (works[0] or {}).get("key") or ""
    if not key:
        return None
    return _work_ratings(key)


def _work_ratings(key):
    if not key.startswith("/"):
        key = "/" + key
    try:
        response = requests.get(
            "https://openlibrary.org%s/ratings.json" % key,
            headers={"User-Agent": _UA},
            timeout=12,
        )
    except requests.RequestException:
        return Rating(reason="request error")
    if response.status_code == 404:
        return None
    if response.status_code == 429:
        return Rating(reason="rate limited")
    if response.status_code >= 400:
        return Rating(reason="request error")
    summary = ((response.json() or {}).get("summary")) or {}
    average = summary.get("average")
    if average is None:
        return None
    count = summary.get("count")
    return Rating(round(float(average), 2), int(count) if count else 0, "https://openlibrary.org" + key)


def _search(title, author, wanted_title=None):
    params = {
        "title": title,
        "limit": 5,
        "fields": "key,title,author_name,ratings_average,ratings_count",
    }
    if author:
        params["author"] = author
    try:
        response = requests.get(
            "https://openlibrary.org/search.json",
            params=params,
            headers={"User-Agent": _UA},
            timeout=12,
        )
    except requests.RequestException:
        return Rating(reason="request error")
    if response.status_code == 429:
        return Rating(reason="rate limited")
    if response.status_code >= 400:
        return Rating(reason="request error")
    docs = (response.json() or {}).get("docs") or []
    wanted = wanted_title or title
    close = False
    for doc in docs:
        names = ", ".join(doc.get("author_name") or [])
        if author and not confident(wanted, author, doc.get("title") or "", names):
            continue
        if not author and not confident(wanted, "", doc.get("title") or "", ""):
            continue
        close = True
        key = doc.get("key") or ""
        if key:
            found = _work_ratings(key)
            if found is not None and found.value is not None:
                return found
        average = doc.get("ratings_average")
        if average is None:
            continue
        count = doc.get("ratings_count")
        url = ("https://openlibrary.org" + key) if key.startswith("/") else ""
        return Rating(round(float(average), 2), int(count) if count else 0, url)
    if docs and not close:
        return Rating(reason="title mismatch")
    return None


def _author(book):
    authors = getattr(book, "authors", None) or []
    if not authors:
        return ""
    return (authors[0].name or "").replace("|", " ")
