# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, LargeBinary, String, Text
try:
    from sqlalchemy.orm import declarative_base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class LibrarySetting(Base):
    """Key value settings for the library UI. Stored only in app.db."""

    __tablename__ = "library_ui_setting"

    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False)
    value = Column(Text, default="")

    def __repr__(self):
        return "<LibrarySetting %r>" % self.key


class LibraryAsset(Base):
    """Logo and favicon bytes. Stored only in app.db."""

    __tablename__ = "library_ui_asset"

    id = Column(Integer, primary_key=True)
    kind = Column(String(16), unique=True, nullable=False)
    mime = Column(String(64), nullable=False)
    data = Column(LargeBinary, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return "<LibraryAsset %r>" % self.kind


class LibraryHero(Base):
    """Featured book or collection shown at the top of the home page."""

    __tablename__ = "library_ui_hero"

    id = Column(Integer, primary_key=True)
    kind = Column(String(16), nullable=False, default="book")
    target_id = Column(Integer, nullable=False)
    headline = Column(String(200), default="")
    blurb = Column(Text, default="")
    sort_order = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)

    def __repr__(self):
        return "<LibraryHero %s %s>" % (self.kind, self.target_id)


class LibraryBookStat(Base):
    """Cached page and word counts. Stored only in app.db."""

    __tablename__ = "library_ui_book_stat"

    book_id = Column(Integer, primary_key=True)
    page_count = Column(Integer)
    word_count = Column(Integer)
    source_format = Column(String(16), default="")
    scanned_at = Column(DateTime)

    def __repr__(self):
        return "<LibraryBookStat %s>" % self.book_id
