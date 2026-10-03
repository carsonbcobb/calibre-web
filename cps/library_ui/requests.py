# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from flask_babel import gettext as _

from .logger_helper import log

_STATUSES = ("pending", "fulfilled", "declined")
_DAILY_LIMIT = 10
_MATCH = 0.85
_MAX_LEN = 200


def pending_count():
    from .. import ub
    from .models import BookRequest

    try:
        return int(
            ub.session.query(BookRequest).filter(BookRequest.status == "pending").count() or 0
        )
    except Exception:
        ub.session.rollback()
        return 0


def user_rows(user_id):
    from .. import ub
    from .models import BookRequest

    try:
        rows = (
            ub.session.query(BookRequest)
            .filter(BookRequest.user_id == int(user_id))
            .order_by(BookRequest.created_at.desc())
            .all()
        )
    except Exception:
        ub.session.rollback()
        return []
    return [_public_row(row) for row in rows]


def admin_rows():
    from .. import ub
    from .models import BookRequest

    try:
        rows = ub.session.query(BookRequest).order_by(BookRequest.created_at.desc()).all()
    except Exception:
        ub.session.rollback()
        return []
    names = _user_names({row.user_id for row in rows})
    payload = []
    for row in rows:
        item = _public_row(row)
        item["user"] = names.get(row.user_id) or ""
        item["user_id"] = row.user_id
        payload.append(item)
    return payload


def create_request(user_id, title, author, confirmed=False):
    """Validate, then save. A close library match is returned before the first save."""
    cleaned, errors = _clean(title, author)
    if errors:
        return {"ok": False, "errors": errors}
    if _daily_count(user_id) >= _DAILY_LIMIT:
        return {"ok": False, "code": "limit", "message": _("You can send 10 requests a day")}
    if _duplicate(user_id, cleaned["title"], cleaned["author"]):
        return {"ok": False, "code": "duplicate", "message": _("You already requested this")}
    match = _library_match(cleaned["title"], cleaned["author"])
    if match and not confirmed:
        return {"ok": False, "match": match}
    row = _insert(user_id, cleaned["title"], cleaned["author"])
    if row is None:
        return {"ok": False, "message": _("Could not save that request")}
    payload = {"ok": True, "request": _public_row(row)}
    if match:
        payload["match"] = match
    return payload


def delete_own(user_id, request_id):
    from .. import ub
    from .models import BookRequest

    try:
        row = ub.session.query(BookRequest).filter(BookRequest.id == int(request_id)).one_or_none()
    except Exception:
        ub.session.rollback()
        return False
    if row is None or row.user_id != int(user_id) or row.status != "pending":
        return False
    ub.session.delete(row)
    ub.session_commit("Book request removed")
    return True


def apply_admin(action, ids):
    from .. import ub
    from .models import BookRequest

    wanted = []
    for item in ids or []:
        try:
            wanted.append(int(item))
        except (TypeError, ValueError):
            continue
    if not wanted:
        return []
    if action not in ("fulfilled", "declined", "delete"):
        return []
    try:
        rows = ub.session.query(BookRequest).filter(BookRequest.id.in_(wanted)).all()
    except Exception:
        ub.session.rollback()
        return []
    now = datetime.now(timezone.utc)
    changed = []
    for row in rows:
        if action == "delete":
            changed.append(row.id)
            ub.session.delete(row)
            continue
        row.status = action
        row.updated_at = now
        changed.append(row.id)
    if changed:
        ub.session_commit("Book requests updated")
    return changed


def _clean(title, author):
    title = " ".join((title or "").split())
    author = " ".join((author or "").split())
    errors = {}
    if not title:
        errors["title"] = _("Enter a title")
    elif len(title) > _MAX_LEN:
        errors["title"] = _("Keep the title under 200 characters")
    if not author:
        errors["author"] = _("Enter an author")
    elif len(author) > _MAX_LEN:
        errors["author"] = _("Keep the author under 200 characters")
    return {"title": title, "author": author}, errors


def _insert(user_id, title, author):
    from .. import ub
    from .models import BookRequest

    now = datetime.now(timezone.utc)
    row = BookRequest(
        user_id=int(user_id),
        title=title,
        author=author,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    try:
        ub.session.add(row)
        ub.session_commit("Book request saved")
    except Exception as error:
        ub.session.rollback()
        log.error("Book request save failed: %s", error)
        return None
    return row


def _daily_count(user_id):
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return sum(1 for row in _user_models(user_id) if _as_utc(row.created_at) >= start)


def _duplicate(user_id, title, author):
    wanted = (_norm(title), _norm(author))
    for row in _user_models(user_id):
        if row.status != "pending":
            continue
        if (_norm(row.title), _norm(row.author)) == wanted:
            return True
    return False


def _user_models(user_id):
    from .. import ub
    from .models import BookRequest

    try:
        return ub.session.query(BookRequest).filter(BookRequest.user_id == int(user_id)).all()
    except Exception:
        ub.session.rollback()
        return []


def _library_match(title, author):
    from flask import url_for

    from .. import calibre_db, db

    want_title = _norm(title)
    want_author = _norm(author)
    if not want_title or not want_author:
        return None
    try:
        books = calibre_db.session.query(db.Books).filter(calibre_db.common_filters()).all()
    except Exception as error:
        log.debug("Request match skipped: %s", error)
        return None
    best = None
    best_score = 0
    for book in books:
        names = " ".join((person.name or "").replace("|", " ") for person in (book.authors or []))
        title_score = SequenceMatcher(None, want_title, _norm(book.title)).ratio()
        author_score = SequenceMatcher(None, want_author, _norm(names)).ratio()
        if title_score < _MATCH or author_score < _MATCH:
            continue
        score = title_score + author_score
        if score > best_score:
            best = book
            best_score = score
    if best is None:
        return None
    label = best.title or title
    try:
        href = url_for("web.show_book", book_id=best.id)
    except Exception:
        href = "/book/%s" % best.id
    return {"id": best.id, "title": label, "url": href}


def _public_row(row):
    created = _as_utc(row.created_at)
    return {
        "id": row.id,
        "title": row.title or "",
        "author": row.author or "",
        "status": row.status if row.status in _STATUSES else "pending",
        "created": created.isoformat() if created else "",
        "date": _date_label(created),
        "pending": row.status == "pending",
    }


def _user_names(ids):
    from .. import ub

    if not ids:
        return {}
    try:
        rows = ub.session.query(ub.User).filter(ub.User.id.in_(list(ids))).all()
    except Exception:
        ub.session.rollback()
        return {}
    return {row.id: row.name or "" for row in rows}


def _norm(value):
    text = re.sub(r"[^a-z0-9]+", " ", (value or "").casefold())
    return " ".join(text.split())


def _as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _date_label(value):
    if value is None:
        return ""
    return value.strftime("%b %d, %Y").replace(" 0", " ")
