# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, LargeBinary, String, Text, UniqueConstraint
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


class HardcoverBook(Base):
    """Cached Hardcover profile for one Calibre book. Stored only in app.db."""

    __tablename__ = "hardcover_books"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, unique=True, index=True)
    hardcover_id = Column(Integer)
    rating = Column(Float)
    ratings_count = Column(Integer)
    reviews_count = Column(Integer)
    users_count = Column(Integer)
    users_read_count = Column(Integer)
    pages = Column(Integer)
    release_date = Column(String(32), default="")
    description = Column(Text, default="")
    cover_url = Column(String(400), default="")
    moods = Column(Text, default="")
    genres = Column(Text, default="")
    tags = Column(Text, default="")
    warnings = Column(Text, default="")
    series_name = Column(String(200), default="")
    series_position = Column(String(32), default="")
    lists_json = Column(Text, default="")
    editions_count = Column(Integer)
    source_url = Column(String(300), default="")
    fetched_at = Column(DateTime)
    error = Column(String(200), default="")

    def __repr__(self):
        return "<HardcoverBook %s>" % self.book_id


class LibraryRating(Base):
    """Cached external rating. Stored only in app.db."""

    __tablename__ = "library_ui_rating"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    rating = Column(Float)
    rating_count = Column(Integer)
    source_url = Column(String(300), default="")
    fetched_at = Column(DateTime)
    error = Column(String(200), default="")

    def __repr__(self):
        return "<LibraryRating %s %s>" % (self.book_id, self.provider)


class LibraryHomeRow(Base):
    """Admin overrides for home shelves. Stored only in app.db."""

    __tablename__ = "library_ui_home_row"

    id = Column(Integer, primary_key=True)
    slug = Column(String(64), unique=True, nullable=False)
    title = Column(String(200), default="")
    subtitle = Column(String(300), default="")
    pinned = Column(Boolean, default=False)
    hidden = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    source_kind = Column(String(16), default="")
    source_value = Column(Text, default="")

    def __repr__(self):
        return "<LibraryHomeRow %s>" % self.slug


class LibraryComment(Base):
    """Reader comment stored only in app.db."""

    __tablename__ = "library_ui_comment"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    body = Column(Text, default="")
    stars = Column(Integer)
    hidden = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return "<LibraryComment %s>" % self.id


class LibraryWant(Base):
    """Per user Want to Read flag. Stored only in app.db."""

    __tablename__ = "library_ui_want"
    __table_args__ = (UniqueConstraint("user_id", "book_id", name="uq_library_ui_want"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    created = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return "<LibraryWant %s %s>" % (self.user_id, self.book_id)


class LibraryFavorite(Base):
    """Per user favorite flag. Stored only in app.db."""

    __tablename__ = "library_ui_favorite"
    __table_args__ = (UniqueConstraint("user_id", "book_id", name="uq_library_ui_favorite"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    created = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return "<LibraryFavorite %s %s>" % (self.user_id, self.book_id)


class Friend(Base):
    """A private friend of one user. Stored only in app.db."""

    __tablename__ = "friends"
    __table_args__ = (UniqueConstraint("user_id", "kindle_email", name="uq_friends_user_email"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String(80), nullable=False)
    kindle_email = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return "<Friend %s>" % self.id


class BookAccolade(Base):
    """A sourced award, list, or adaptation note. Stored only in app.db."""

    __tablename__ = "book_accolades"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    type = Column(String(32), nullable=False, default="critical")
    label = Column(String(200), nullable=False, default="")
    year = Column(Integer)
    source = Column(String(32), default="")
    source_url = Column(String(400), default="")
    manual = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return "<BookAccolade %s %s>" % (self.book_id, self.label)


class BookQuote(Base):
    """A short press quote with a publication. Stored only in app.db."""

    __tablename__ = "book_quotes"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    quote = Column(Text, default="")
    publication = Column(String(160), default="")
    author_of_review = Column(String(160), default="")
    url = Column(String(400), default="")
    source = Column(String(32), default="")
    manual = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return "<BookQuote %s>" % self.book_id


class AwardCache(Base):
    """Winners and nominees for one award, cached for 30 days. Stored only in app.db."""

    __tablename__ = "award_caches"

    award_key = Column(String(64), primary_key=True)
    payload = Column(Text, default="")
    fetched_at = Column(DateTime)
    error = Column(String(200), default="")

    def __repr__(self):
        return "<AwardCache %s>" % self.award_key


class AccoladeAttempt(Base):
    """Why one accolade provider matched or missed a book. Stored only in app.db."""

    __tablename__ = "accolade_attempts"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="")
    matched = Column(Boolean, default=False)
    identifier = Column(String(200), default="")
    reason = Column(String(80), default="")
    query_text = Column(String(400), default="")
    result_count = Column(Integer)
    score = Column(Integer)

    def __repr__(self):
        return "<AccoladeAttempt %s %s>" % (self.book_id, self.provider)


class SeriesAttempt(Base):
    """Why one description provider matched or missed a series. Stored only in app.db."""

    __tablename__ = "series_attempts"

    id = Column(Integer, primary_key=True)
    series_id = Column(Integer, nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="")
    matched = Column(Boolean, default=False)
    query_text = Column(String(400), default="")
    result_count = Column(Integer)
    score = Column(Integer)
    reason = Column(String(80), default="")

    def __repr__(self):
        return "<SeriesAttempt %s %s>" % (self.series_id, self.provider)


class BookReview(Base):
    """A public review cached from a provider. Stored only in app.db."""

    __tablename__ = "book_reviews"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    source = Column(String(32), default="hardcover")
    reviewer = Column(String(120), default="")
    rating = Column(Float)
    reviewed_on = Column(String(32), default="")
    body = Column(Text, default="")
    url = Column(String(400), default="")
    fetched_at = Column(DateTime)

    def __repr__(self):
        return "<BookReview %s>" % self.book_id


class SeriesInfo(Base):
    """A sourced description for one Calibre series. Stored only in app.db."""

    __tablename__ = "series_info"

    series_id = Column(Integer, primary_key=True)
    description = Column(Text, default="")
    source = Column(String(32), default="")
    source_url = Column(String(400), default="")
    is_complete = Column(Boolean, nullable=True)
    total_books_reported = Column(Integer)
    fetched_at = Column(DateTime)
    manual = Column(Boolean, default=False)

    def __repr__(self):
        return "<SeriesInfo %s>" % self.series_id


class BookLookup(Base):
    """When a book was last scanned for accolades and quotes."""

    __tablename__ = "book_lookups"
    __table_args__ = (UniqueConstraint("book_id", "kind", name="uq_book_lookup"),)

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    kind = Column(String(16), nullable=False, default="scan")
    checked_at = Column(DateTime)

    def __repr__(self):
        return "<BookLookup %s>" % self.book_id


class SentToFriend(Base):
    """A book queued for a friend. Stored only in app.db."""

    __tablename__ = "sent_to_friends"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    friend_id = Column(Integer, nullable=False, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(String(16), default="queued")

    def __repr__(self):
        return "<SentToFriend %s>" % self.id
