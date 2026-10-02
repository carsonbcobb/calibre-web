# -*- coding: utf-8 -*-

"""Admin list of books and series the scans could not fill. Manual rows stay."""

import csv
import io


def gap_page():
    books = _books()
    series = _series()
    lines = []
    for book in books:
        author = (" by %s" % book["author"]) if book["author"] else ""
        lines.append("%s%s" % (book["title"], author))
    for item in series:
        author = (" by %s" % item["author"]) if item["author"] else ""
        lines.append("%s%s" % (item["name"], author))
    return {"books": books, "series": series, "text": "\n".join(lines)}


def save_book_gap(book_id, label, type_name, year, source_url):
    from .accolade_allowlist import accept
    from .accolades import save_accolade

    kept = accept({
        "label": label,
        "type": type_name or "award_win",
        "year": year,
        "source": "manual",
        "source_url": source_url,
    })
    if not kept:
        return "That label is not an allowlisted recognition."
    save_accolade(book_id, kept["type"], kept["label"], year, source_url)
    return ""


def save_series_gap(series_id, description, source_url):
    from .series_info import save_manual

    save_manual(series_id, description, source_url)
    return ""


def import_csv(text):
    """name, field, value, source url. Field is label or description."""
    saved = 0
    errors = []
    books = {row["title"].casefold(): row for row in _books()}
    series = {row["name"].casefold(): row for row in _all_series()}
    reader = csv.reader(io.StringIO(text or ""))
    for number, cells in enumerate(reader, start=1):
        if not any(cell.strip() for cell in cells):
            continue
        if number == 1 and cells and cells[0].strip().casefold() in ("name", "title"):
            continue
        if len(cells) < 3:
            errors.append("Line %s: need a name, a field, and a value." % number)
            continue
        name = cells[0].strip()
        field = cells[1].strip().casefold()
        value = cells[2].strip()
        source = cells[3].strip() if len(cells) > 3 else ""
        year = cells[4].strip() if len(cells) > 4 else ""
        if field == "description":
            item = series.get(name.casefold())
            if item is None:
                errors.append("Line %s: no series named %s." % (number, name))
                continue
            save_series_gap(item["id"], value, source)
            saved += 1
            continue
        if field != "label":
            errors.append("Line %s: field must be label or description." % number)
            continue
        item = books.get(name.casefold())
        if item is None:
            errors.append("Line %s: no unmatched book named %s." % (number, name))
            continue
        problem = save_book_gap(item["id"], value, "award_win", year, source)
        if problem:
            errors.append("Line %s: %s" % (number, problem))
            continue
        saved += 1
    return saved, errors


def _books():
    from .. import calibre_db, db, ub
    from .models import BookAccolade

    have = {row.book_id for row in ub.session.query(BookAccolade.book_id).distinct()}
    found = []
    for book in calibre_db.session.query(db.Books).order_by(db.Books.sort).all():
        if book.id in have:
            continue
        author = ""
        if book.authors:
            author = (book.authors[0].name or "").replace("|", " ")
        found.append({"id": book.id, "title": book.title or "", "author": author})
    return found


def _series():
    from .series_info import coverage

    return coverage().get("gaps") or []


def _all_series():
    from .. import calibre_db, db

    found = []
    for series in calibre_db.session.query(db.Series).order_by(db.Series.name).all():
        found.append({"id": series.id, "name": series.name or ""})
    return found
