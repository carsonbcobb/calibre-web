# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Want to Read and Favorite flags, plus the existing finished read status."""

from flask import abort, g
from flask_babel import gettext as _

from .models import LibraryFavorite, LibraryWant


def _uid():
    from ..cw_login import current_user

    if not current_user or current_user.is_anonymous:
        return None
    return int(current_user.id)


def _ids(model):
    from .. import ub

    uid = _uid()
    if uid is None:
        return set()
    rows = ub.session.query(model.book_id).filter(model.user_id == uid).all()
    return {row[0] for row in rows}


def favorite_ids():
    cached = getattr(g, "library_favorite_ids", None)
    if cached is None:
        cached = _ids(LibraryFavorite)
        g.library_favorite_ids = cached
    return cached


def want_ids():
    cached = getattr(g, "library_want_ids", None)
    if cached is None:
        cached = _ids(LibraryWant)
        g.library_want_ids = cached
    return cached


def library_is_favorite(book_id):
    try:
        return int(book_id) in favorite_ids()
    except (TypeError, ValueError):
        return False


def library_is_wanted(book_id):
    try:
        return int(book_id) in want_ids()
    except (TypeError, ValueError):
        return False


def _finished_ids(uid):
    from .. import ub

    rows = (ub.session.query(ub.ReadBook.book_id)
            .filter(ub.ReadBook.user_id == uid)
            .filter(ub.ReadBook.read_status == ub.ReadBook.STATUS_FINISHED)
            .all())
    return {row[0] for row in rows}


def _ordered_books(ids):
    from .. import calibre_db, db

    if not ids:
        return []
    books = (calibre_db.session.query(db.Books)
             .filter(db.Books.id.in_(list(ids)))
             .filter(calibre_db.common_filters())
             .all())
    order = {book_id: index for index, book_id in enumerate(ids)}
    books.sort(key=lambda book: order.get(book.id, len(ids)))
    return books


def books_for(kind):
    from .. import ub

    uid = _uid()
    if uid is None:
        return []
    if kind == "want":
        rows = (ub.session.query(LibraryWant.book_id)
                .filter(LibraryWant.user_id == uid)
                .order_by(LibraryWant.created.desc())
                .all())
        finished = _finished_ids(uid)
        ids = [row[0] for row in rows if row[0] not in finished]
    elif kind == "favorite":
        rows = (ub.session.query(LibraryFavorite.book_id)
                .filter(LibraryFavorite.user_id == uid)
                .order_by(LibraryFavorite.created.desc())
                .all())
        ids = [row[0] for row in rows]
    else:
        rows = (ub.session.query(ub.ReadBook.book_id)
                .filter(ub.ReadBook.user_id == uid)
                .filter(ub.ReadBook.read_status == ub.ReadBook.STATUS_FINISHED)
                .order_by(ub.ReadBook.last_modified.desc())
                .all())
        ids = [row[0] for row in rows]
    return _ordered_books(ids)


def _book_or_404(book_id):
    from .. import calibre_db, db

    book = (calibre_db.session.query(db.Books)
            .filter(db.Books.id == int(book_id))
            .filter(calibre_db.common_filters())
            .first())
    if book is None:
        abort(404)
    return book


def _set_row(model, uid, book_id, on):
    from .. import ub

    row = (ub.session.query(model)
           .filter(model.user_id == uid)
           .filter(model.book_id == book_id)
           .one_or_none())
    if on and row is None:
        ub.session.add(model(user_id=uid, book_id=book_id))
    elif not on and row is not None:
        ub.session.delete(row)


def state_for(book_id):
    from .. import ub

    uid = _uid()
    book_id = int(book_id)
    if uid is None:
        return {"ok": False, "want": False, "finished": False, "favorite": False}
    want = (ub.session.query(LibraryWant.id)
            .filter(LibraryWant.user_id == uid)
            .filter(LibraryWant.book_id == book_id)
            .first()) is not None
    favorite = (ub.session.query(LibraryFavorite.id)
                .filter(LibraryFavorite.user_id == uid)
                .filter(LibraryFavorite.book_id == book_id)
                .first()) is not None
    read = (ub.session.query(ub.ReadBook)
            .filter(ub.ReadBook.user_id == uid)
            .filter(ub.ReadBook.book_id == book_id)
            .first())
    finished = bool(read and read.read_status == ub.ReadBook.STATUS_FINISHED)
    return {"ok": True, "want": want, "finished": finished, "favorite": favorite}


def set_flag(kind, book_id, on):
    from .. import ub
    from ..helper import edit_book_read_status

    uid = _uid()
    if uid is None:
        abort(404)
    book_id = int(book_id)
    _book_or_404(book_id)
    if kind == "want":
        _set_row(LibraryWant, uid, book_id, on)
        ub.session_commit("Want to Read updated")
    elif kind == "favorite":
        _set_row(LibraryFavorite, uid, book_id, on)
        ub.session_commit("Favorite updated")
    elif kind == "finished":
        edit_book_read_status(book_id, True if on else False)
        if on:
            _set_row(LibraryWant, uid, book_id, False)
            ub.session_commit("Want to Read cleared")
    else:
        abort(400)
    g.library_favorite_ids = None
    g.library_want_ids = None
    return state_for(book_id)


def render_flag_list(data):
    from .. import constants
    from ..cw_login import current_user
    from ..render_template import render_title_template

    if data == "rated":
        if not current_user.check_visibility(constants.SIDEBAR_BEST_RATED):
            abort(404)
        title = _("Favorites")
        books = books_for("favorite")
    elif data == "read":
        if not current_user.check_visibility(constants.SIDEBAR_READ_AND_UNREAD):
            abort(404)
        title = _("Finished")
        books = books_for("finished")
    else:
        if not current_user.check_visibility(constants.SIDEBAR_READ_AND_UNREAD):
            abort(404)
        title = _("Want to Read")
        books = books_for("want")
    return render_title_template(
        "library_flags.html",
        title=title,
        entries=books,
        page=data,
    )
