# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from .base import RatingProvider

# Goodreads has no public API. To add a scraper later:
# 1. Implement lookup() so it returns a Rating or None.
# 2. Set enabled = True.
# 3. The cache and the book page will pick it up with the other providers.


class GoodreadsProvider(RatingProvider):
    name = "Goodreads"
    slug = "goodreads"
    enabled = False

    def lookup(self, book):
        return None
