# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Private friends list and sending a book to a friend's Kindle address."""

from datetime import datetime, timedelta, timezone
from email.utils import parseaddr

from flask import abort, jsonify
from flask_babel import gettext as _
from sqlalchemy.exc import IntegrityError

from . import logger_helper
from .models import Friend, SentToFriend

log = logger_helper.log

HOURLY_LIMIT = 20


def _uid():
    from ..cw_login import current_user

    if not current_user or current_user.is_anonymous:
        return None
    return int(current_user.id)


def _session():
    from .. import ub

    return ub.session


def initials(name):
    parts = [part for part in (name or "").split() if part]
    if not parts:
        return "?"
    letters = [part[0] for part in parts[:2]]
    return "".join(letters).upper()


def sending_address():
    """Address from the email server settings, used in the helper line."""
    from .. import config

    raw = getattr(config, "mail_from", "") or ""
    address = parseaddr(raw)[1].strip().lower()
    if not address or address == "mail@example.com":
        return ""
    return address


def helper_line():
    address = sending_address()
    if address:
        return _(
            "Ask your friend to add your sending address (%(address)s) to their "
            "Approved Personal Document Email List in their Amazon account, "
            "or the book will not arrive.",
            address=address,
        )
    return _(
        "Ask your friend to add your sending address to their "
        "Approved Personal Document Email List in their Amazon account, "
        "or the book will not arrive."
    )


def _clean_name(raw):
    name = " ".join((raw or "").split())
    if not name:
        raise ValueError(_("Enter a name."))
    if len(name) > 80:
        raise ValueError(_("That name is too long."))
    return name


def _clean_email(raw):
    from ..helper import valid_email

    text = (raw or "").strip()
    if "," in text or " " in text:
        raise ValueError(_("Enter one email address."))
    try:
        email = valid_email(text)
    except Exception:
        raise ValueError(_("Enter a valid email address."))
    email = email.lower()
    if "," in email:
        raise ValueError(_("Enter one email address."))
    return email


def _owned(friend_id):
    uid = _uid()
    if uid is None:
        abort(403)
    friend = (_session().query(Friend)
              .filter(Friend.id == int(friend_id), Friend.user_id == uid)
              .one_or_none())
    if friend is None:
        abort(404)
    return friend


def list_friends():
    uid = _uid()
    if uid is None:
        return []
    return (_session().query(Friend)
            .filter(Friend.user_id == uid)
            .order_by(Friend.name.asc(), Friend.id.asc())
            .all())


def recent_sends(friend_id, limit=3):
    uid = _uid()
    rows = (_session().query(SentToFriend)
            .filter(SentToFriend.user_id == uid,
                    SentToFriend.friend_id == int(friend_id),
                    SentToFriend.status == "queued")
            .order_by(SentToFriend.sent_at.desc(), SentToFriend.id.desc())
            .limit(limit)
            .all())
    if not rows:
        return []
    from .. import calibre_db, db

    ids = [row.book_id for row in rows]
    books = {book.id: book for book in calibre_db.session.query(db.Books).filter(db.Books.id.in_(ids))}
    items = []
    for row in rows:
        book = books.get(row.book_id)
        if book is None:
            continue
        stamp = row.sent_at or datetime.now(timezone.utc)
        items.append({
            "book_id": book.id,
            "title": book.title,
            "when": "%s %s, %s" % (stamp.strftime("%b"), stamp.day, stamp.year),
        })
    return items


def save_friend(name, email, friend_id=None):
    uid = _uid()
    if uid is None:
        abort(403)
    name = _clean_name(name)
    email = _clean_email(email)
    session = _session()
    duplicate = (session.query(Friend)
                 .filter(Friend.user_id == uid, Friend.kindle_email == email)
                 .one_or_none())
    if friend_id:
        friend = _owned(friend_id)
        if duplicate is not None and duplicate.id != friend.id:
            raise ValueError(_("That email is already saved."))
        friend.name = name
        friend.kindle_email = email
    else:
        if duplicate is not None:
            raise ValueError(_("That email is already saved."))
        friend = Friend(user_id=uid, name=name, kindle_email=email)
        session.add(friend)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ValueError(_("That email is already saved."))
    return friend


def delete_friend(friend_id):
    friend = _owned(friend_id)
    session = _session()
    session.query(SentToFriend).filter(
        SentToFriend.user_id == friend.user_id,
        SentToFriend.friend_id == friend.id,
    ).delete(synchronize_session=False)
    session.delete(friend)
    session.commit()


def _sent_this_hour(uid):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    return (_session().query(SentToFriend)
            .filter(SentToFriend.user_id == uid, SentToFriend.sent_at >= cutoff)
            .count())


def send_book(book_id, friend_ids, book_format, convert):
    from .. import calibre_db, config
    from ..cw_login import current_user
    from ..helper import check_send_to_ereader, send_mail

    uid = _uid()
    if uid is None:
        abort(403)
    if not current_user.role_download():
        abort(403)
    book = calibre_db.get_book(book_id)
    if book is None:
        abort(404)
    allowed = check_send_to_ereader(book)
    convert = int(convert)
    is_allowed = any(
        option.get("format", "").lower() == (book_format or "").lower() and int(option.get("convert", -1)) == convert
        for option in allowed
    )
    if not is_allowed:
        return {"ok": False, "message": _("This book cannot be sent.")}
    if not config.get_mail_server_configured():
        return {"ok": False, "message": _("Email is not ready yet. Ask an admin to set up sending.")}

    ids = []
    for raw in friend_ids:
        text = str(raw).strip()
        if text.isdigit():
            ids.append(int(text))
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {"ok": False, "message": _("Choose a friend.")}

    friends = (_session().query(Friend)
               .filter(Friend.user_id == uid, Friend.id.in_(ids))
               .all())
    if len(friends) != len(ids):
        abort(404)
    if _sent_this_hour(uid) + len(friends) > HOURLY_LIMIT:
        log.warning("Friend send rate limit for user %s", uid)
        return {"ok": False, "message": _("You have sent enough books for this hour. Try again later.")}

    sent_names = []
    failed = False
    session = _session()
    for friend in friends:
        result = send_mail(
            book_id,
            book_format,
            convert,
            friend.kindle_email,
            config.get_book_path(),
            current_user.name,
        )
        status = "queued" if result is None else "failed"
        session.add(SentToFriend(
            user_id=uid,
            friend_id=friend.id,
            book_id=book.id,
            status=status,
        ))
        if result is None:
            sent_names.append(friend.name)
        else:
            failed = True
            log.warning("Friend send failed user %s friend %s book %s: %s", uid, friend.id, book.id, result)
    session.commit()

    if failed and not sent_names:
        return {"ok": False, "message": _("Could not send this book.")}
    if failed:
        return {"ok": False, "message": _("Could not send to every friend.")}
    if len(sent_names) == 1:
        message = _("Sent to %(name)s", name=sent_names[0])
    else:
        message = _("Sent to %(count)s friends", count=len(sent_names))
    return {"ok": True, "message": message}
