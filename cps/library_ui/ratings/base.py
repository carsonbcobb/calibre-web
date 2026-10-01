# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.


class Rating(object):
    def __init__(self, value, count=None, url=""):
        self.value = value
        self.count = count
        self.url = url or ""


class RatingProvider(object):
    """Look up one external rating for a Calibre book.

    Subclass this and add the class to PROVIDERS in service.py.
    lookup() returns a Rating, or None when this provider has nothing to show.
    """

    name = ""
    slug = ""
    enabled = True

    def available(self):
        return True

    def lookup(self, book):
        raise NotImplementedError
