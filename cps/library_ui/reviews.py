# -*- coding: utf-8 -*-

"""Cached public reviews. Page loads only read the table."""

from datetime import datetime, timedelta, timezone

_FRESH = timedelta(days=30)
_QUERY = """
query($id: Int!) {
  books(where: {id: {_eq: $id}}) {
    slug
    user_books(limit: 15, where: {has_review: {_eq: true}}) {
      rating
      reviewed_at
      review_raw
      user { username }
    }
  }
}
"""


def reviews_for(book_id):
    """Stored reviews for the page. Never calls the network."""
    from .. import ub
    from .models import BookReview

    try:
        rows = (ub.session.query(BookReview)
                .filter(BookReview.book_id == int(book_id))
                .all())
    except Exception:
        ub.session.rollback()
        return []
    found = []
    for row in rows:
        body = (row.body or "").strip()
        if not body:
            continue
        words = body.split()
        excerpt = " ".join(words[:60])
        if len(words) > 60:
            excerpt = excerpt + "..."
        found.append({
            "reviewer": row.reviewer or "Reader",
            "rating": row.rating,
            "date": _date(row.reviewed_on),
            "excerpt": excerpt,
            "url": row.url or "",
            "source": "Hardcover",
        })
    return found[:15]


def cache_reviews(book):
    """Fetch Hardcover reviews during a background scan. Skip when the cache is fresh."""
    from .. import ub
    from .models import BookReview, HardcoverBook
    from .ratings.hardcover import _post

    if _fresh(book.id):
        return
    profile = ub.session.query(HardcoverBook).filter(HardcoverBook.book_id == book.id).one_or_none()
    hardcover_id = getattr(profile, "hardcover_id", None) if profile is not None else None
    if not hardcover_id:
        return
    payload = _post(_QUERY, {"id": int(hardcover_id)})
    if not isinstance(payload, dict):
        return
    books = ((payload.get("data") or {}).get("books") or [])
    if not books:
        _touch(book.id)
        return
    slug = (books[0].get("slug") or "").strip()
    url = ("https://hardcover.app/books/" + slug) if slug else "https://hardcover.app"
    ub.session.query(BookReview).filter(BookReview.book_id == book.id).delete(synchronize_session=False)
    now = datetime.now(timezone.utc)
    for item in (books[0].get("user_books") or [])[:15]:
        body = (item.get("review_raw") or "").strip()
        if not body:
            continue
        user = item.get("user") or {}
        ub.session.add(BookReview(
            book_id=book.id,
            source="hardcover",
            reviewer=((user.get("username") or "Reader").strip())[:120],
            rating=_rating(item.get("rating")),
            reviewed_on=str(item.get("reviewed_at") or "")[:32],
            body=body,
            url=url[:400],
            fetched_at=now,
        ))
    _touch(book.id)
    ub.session_commit("Review cache for book %s" % book.id)


def _fresh(book_id):
    from .. import ub
    from .models import BookLookup

    row = (ub.session.query(BookLookup)
           .filter(BookLookup.book_id == int(book_id))
           .filter(BookLookup.kind == "review")
           .one_or_none())
    if row is None or not row.checked_at:
        return False
    checked = row.checked_at
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - checked < _FRESH


def _touch(book_id):
    from .. import ub
    from .models import BookLookup

    row = (ub.session.query(BookLookup)
           .filter(BookLookup.book_id == int(book_id))
           .filter(BookLookup.kind == "review")
           .one_or_none())
    if row is None:
        row = BookLookup(book_id=int(book_id), kind="review")
        ub.session.add(row)
    row.checked_at = datetime.now(timezone.utc)


def _rating(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 5:
        number = number / 2.0
    if number <= 0:
        return None
    return round(number, 2)


def _date(value):
    text = (value or "").strip()
    if len(text) < 10:
        return ""
    try:
        parsed = datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return ""
    return parsed.strftime("%b %d, %Y").replace(" 0", " ")
