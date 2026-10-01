# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from datetime import datetime, timezone

from .models import LibraryComment

MAX_BODY = 2000


def comments_for_book(book_id, include_hidden=False):
    from .. import ub
    query = ub.session.query(LibraryComment).filter(LibraryComment.book_id == int(book_id))
    if not include_hidden:
        query = query.filter(LibraryComment.hidden == False)  # noqa: E712
    return query.order_by(LibraryComment.created_at.asc()).all()


def recent_comments(limit=50):
    from .. import ub
    return (ub.session.query(LibraryComment)
            .order_by(LibraryComment.created_at.desc())
            .limit(limit)
            .all())


def user_name(user_id):
    from .. import ub
    user = ub.session.query(ub.User).filter(ub.User.id == int(user_id)).first()
    return user.name if user else ""


def add_comment(book_id, user_id, body, stars):
    from .. import ub
    text = _clean_body(body)
    if not text:
        return None
    row = LibraryComment(
        book_id=int(book_id),
        user_id=int(user_id),
        body=text,
        stars=_clean_stars(stars),
        hidden=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    ub.session.add(row)
    ub.session_commit("Library UI comment added")
    return row


def update_comment(comment_id, user_id, body, stars, is_admin=False):
    row = _owned(comment_id, user_id, is_admin)
    if row is None:
        return None
    text = _clean_body(body)
    if not text:
        return None
    row.body = text
    row.stars = _clean_stars(stars)
    row.updated_at = datetime.now(timezone.utc)
    from .. import ub
    ub.session_commit("Library UI comment edited")
    return row


def delete_comment(comment_id, user_id, is_admin=False):
    row = _owned(comment_id, user_id, is_admin)
    if row is None:
        return False
    from .. import ub
    ub.session.delete(row)
    ub.session_commit("Library UI comment deleted")
    return True


def set_hidden(comment_id, hidden):
    from .. import ub
    row = ub.session.query(LibraryComment).filter(LibraryComment.id == int(comment_id)).first()
    if row is None:
        return False
    row.hidden = bool(hidden)
    row.updated_at = datetime.now(timezone.utc)
    ub.session_commit("Library UI comment moderated")
    return True


def _owned(comment_id, user_id, is_admin):
    from .. import ub
    row = ub.session.query(LibraryComment).filter(LibraryComment.id == int(comment_id)).first()
    if row is None:
        return None
    if is_admin or row.user_id == int(user_id):
        return row
    return None


def _clean_body(body):
    text = (body or "").replace("\x00", "").strip()
    return text[:MAX_BODY]


def _clean_stars(stars):
    try:
        value = int(stars)
    except (TypeError, ValueError):
        return None
    if 1 <= value <= 5:
        return value
    return None
