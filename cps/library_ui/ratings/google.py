# -*- coding: utf-8 -*-

"""Google Books ratings. Server side only."""

import requests

from .base import Rating, RatingProvider
from .match import confident, identifiers, series_query

_UA = "DeadMediaSociety/1.0 (local library catalog; ratings)"
_URL = "https://www.googleapis.com/books/v1/volumes"


class GoogleBooksProvider(RatingProvider):
    name = "Google Books"
    slug = "google"

    def lookup(self, book):
        ids = identifiers(book)
        for isbn in ids["isbn"]:
            found = _isbn(isbn)
            if found is not None:
                return found
        for volume_id in ids["google"]:
            found = _volume(volume_id)
            if found is not None:
                return found
        title = (book.title or "").strip()
        author = _author(book)
        if title and author:
            found = _fuzzy(title, author, "intitle:%s inauthor:%s" % (title.split(":")[0], author))
            if found is not None:
                return found
        series = ""
        index = None
        if getattr(book, "series", None):
            series = book.series[0].name or ""
            index = getattr(book, "series_index", None)
        query = series_query(series, index)
        if query and author:
            found = _fuzzy(title or query, author, "%s %s" % (query, author))
            if found is not None:
                return found
        if not any(ids.values()) and not title:
            return Rating(reason="no identifier")
        return Rating(reason="title mismatch" if title else "no results")


def _isbn(isbn):
    items, problem = _items({"q": "isbn:" + isbn, "maxResults": 1})
    if problem is not None:
        return problem
    if not items:
        return None
    return _from_item(items[0])


def _volume(volume_id):
    try:
        response = requests.get(_URL + "/" + volume_id, headers={"User-Agent": _UA}, timeout=12)
    except requests.RequestException:
        return Rating(reason="request error")
    if response.status_code == 404:
        return None
    if response.status_code == 429:
        return Rating(reason="rate limited")
    if response.status_code >= 400:
        return Rating(reason="request error")
    return _from_item(response.json() or {})


def _fuzzy(title, author, query):
    items, problem = _items({"q": query, "maxResults": 5})
    if problem is not None:
        return problem
    saw = False
    for item in items:
        info = item.get("volumeInfo") or {}
        names = ", ".join(info.get("authors") or [])
        if not confident(title, author, info.get("title") or "", names):
            continue
        saw = True
        rating = _from_item(item)
        if rating is not None:
            return rating
    if items and not saw:
        return Rating(reason="title mismatch")
    return None


def _items(params):
    try:
        response = requests.get(_URL, params=params, headers={"User-Agent": _UA}, timeout=12)
    except requests.RequestException:
        return [], Rating(reason="request error")
    if response.status_code == 429:
        return [], Rating(reason="rate limited")
    if response.status_code >= 400:
        return [], Rating(reason="request error")
    return (response.json() or {}).get("items") or [], None


def _from_item(item):
    info = item.get("volumeInfo") or {}
    average = info.get("averageRating")
    if average is None:
        return None
    count = info.get("ratingsCount")
    link = info.get("canonicalVolumeLink") or info.get("infoLink") or ""
    return Rating(round(float(average), 2), int(count) if count else 0, link)


def _author(book):
    authors = getattr(book, "authors", None) or []
    if not authors:
        return ""
    return (authors[0].name or "").replace("|", " ")
