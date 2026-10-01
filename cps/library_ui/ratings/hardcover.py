# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import requests

from ..store import get_setting
from .base import Rating, RatingProvider

_QUERY = """
query ($title: String!) {
  books(where: {title: {_ilike: $title}}, limit: 1, order_by: {users_count: desc}) {
    title
    rating
    ratings_count
    slug
  }
}
"""


class HardcoverProvider(RatingProvider):
    name = "Hardcover"
    slug = "hardcover"

    def available(self):
        token = (get_setting("hardcover_token", "") or "").strip()
        return bool(token)

    def lookup(self, book):
        token = (get_setting("hardcover_token", "") or "").strip()
        if not token:
            return None
        title = (book.title or "").strip()
        if not title:
            return None
        response = requests.post(
            "https://api.hardcover.app/v1/graphql",
            json={"query": _QUERY, "variables": {"title": title}},
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
            timeout=6,
        )
        response.raise_for_status()
        payload = response.json() or {}
        if payload.get("errors"):
            return None
        books = ((payload.get("data") or {}).get("books")) or []
        if not books or books[0].get("rating") is None:
            return None
        item = books[0]
        slug = item.get("slug") or ""
        url = ("https://hardcover.app/books/" + slug) if slug else "https://hardcover.app"
        count = item.get("ratings_count")
        return Rating(round(float(item["rating"]), 2), int(count) if count else None, url)
