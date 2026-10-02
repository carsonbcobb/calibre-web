# -*- coding: utf-8 -*-

"""Normalize titles and authors, then decide if a provider hit is the same book."""

import re
from difflib import SequenceMatcher

_ARTICLES = {"a", "an", "the"}
_PUNCT = re.compile(r"[^a-z0-9\s]+")
_SPACE = re.compile(r"\s+")
_SERIES_SUFFIX = re.compile(r"\s*[\(\[][^)\]]*(?:#|book|vol\.?|volume)\s*[\d.]+[^)\]]*[\)\]]\s*$", re.I)
_TAIL = re.compile(r"\s*(?:\([^)]{0,48}\)|\[[^\]]{0,48}\]|,?\s+book\s+\d+|,?\s+volume\s+\d+)$", re.I)
_THRESHOLD = 85


def identifiers(book):
    """Every useful identifier on the book, grouped by kind."""
    found = {"isbn": [], "google": [], "goodreads": [], "amazon": [], "hardcover": [], "openlibrary": [], "oclc": []}
    for ident in getattr(book, "identifiers", None) or []:
        kind = (getattr(ident, "type", "") or "").strip().casefold()
        raw = (getattr(ident, "val", "") or "").strip()
        if not raw:
            continue
        if kind in ("isbn", "isbn13", "isbn10"):
            digits = re.sub(r"[^0-9Xx]", "", raw)
            if len(digits) in (10, 13) and digits not in found["isbn"]:
                found["isbn"].append(digits)
        elif kind == "google":
            found["google"].append(raw)
        elif kind == "goodreads":
            found["goodreads"].append(raw)
        elif kind in ("amazon", "asin", "mobi-asin"):
            found["amazon"].append(raw)
        elif kind == "hardcover":
            found["hardcover"].append(raw)
        elif kind in ("openlibrary", "olid"):
            found["openlibrary"].append(raw)
        elif kind == "oclc":
            found["oclc"].append(raw)
    return found


def title_forms(title):
    raw = title or ""
    head = raw.split(":")[0]
    head = _SERIES_SUFFIX.sub("", head)
    trimmed = _TAIL.sub("", head).strip()
    forms = []
    for text in (raw, head, trimmed):
        normal = _normalize(text, articles=True)
        if normal and normal not in forms:
            forms.append(normal)
    return forms


def author_forms(name):
    text = (name or "").replace("|", " ").strip()
    forms = []
    normal = _normalize(text, articles=False)
    if normal:
        forms.append(normal)
    if "," in text:
        last, _sep, rest = text.partition(",")
        flipped = _normalize("%s %s" % (rest.strip(), last.strip()), articles=False)
        if flipped and flipped not in forms:
            forms.append(flipped)
    else:
        parts = [part for part in re.split(r"\s+", text) if part]
        if len(parts) >= 2:
            flipped = _normalize("%s %s" % (parts[-1], " ".join(parts[:-1])), articles=False)
            if flipped and flipped not in forms:
                forms.append(flipped)
    return forms


def match_detail(wanted_title, wanted_author, found_title, found_author, strict=False):
    """Title score, author score, and whether the hit is the same book.

    strict is for award lists, where one shared word must not score as the same title.
    """
    titles = title_forms(wanted_title)
    found_titles = title_forms(found_title)
    title_score = 0
    if titles and found_titles:
        score_fn = _award_title_ratio if strict else _token_set_ratio
        title_score = max(score_fn(left, right) for left in titles for right in found_titles)
    authors = author_forms(wanted_author)
    found_authors = author_forms(found_author)
    author_score = 0
    if authors and found_authors:
        author_score = max(_token_set_ratio(left, right) for left in authors for right in found_authors)
    if not titles or not found_titles:
        return title_score, author_score, False
    threshold = 80 if author_score == 100 else _THRESHOLD
    if title_score < threshold:
        return title_score, author_score, False
    if not authors or not found_authors:
        return title_score, author_score, title_score >= 92
    if author_score >= 80:
        return title_score, author_score, True
    wanted_last = authors[0].split()[-1] if authors[0].split() else ""
    found_last = found_authors[0].split()[-1] if found_authors[0].split() else ""
    return title_score, author_score, bool(wanted_last) and wanted_last == found_last and title_score >= 90


def confident(wanted_title, wanted_author, found_title, found_author):
    """True when the title is close and the author matches loosely."""
    _title_score, _author_score, ok = match_detail(wanted_title, wanted_author, found_title, found_author)
    return ok


def series_query(series_name, index):
    name = (series_name or "").strip()
    if not name:
        return ""
    try:
        number = float(index or 0)
    except (TypeError, ValueError):
        number = 0
    label = ("%.2f" % number).rstrip("0").rstrip(".") if number else ""
    if label:
        return "%s %s" % (name, label)
    return name


def _normalize(text, articles):
    folded = (text or "").casefold()
    folded = _PUNCT.sub(" ", folded)
    tokens = [token for token in _SPACE.split(folded) if token]
    if articles:
        tokens = [token for token in tokens if token not in _ARTICLES]
    return " ".join(tokens)


def _award_title_ratio(left, right):
    """Token overlap that refuses a one word collision with a longer title."""
    a = set((left or "").split())
    b = set((right or "").split())
    shared = a & b
    if len(shared) == 1 and max(len(a), len(b)) > 1:
        return _ratio(" ".join(sorted(a)), " ".join(sorted(b)))
    return _token_set_ratio(left, right)


def _token_set_ratio(left, right):
    a = set(left.split())
    b = set(right.split())
    if not a or not b:
        return 0
    shared = a & b
    left_rest = a - shared
    right_rest = b - shared
    scores = [
        _ratio(" ".join(sorted(shared)), " ".join(sorted(shared | left_rest))),
        _ratio(" ".join(sorted(shared)), " ".join(sorted(shared | right_rest))),
        _ratio(" ".join(sorted(shared | left_rest)), " ".join(sorted(shared | right_rest))),
    ]
    return max(scores)


def _ratio(left, right):
    if not left and not right:
        return 100
    if not left or not right:
        return 0
    return int(round(SequenceMatcher(None, left, right).ratio() * 100))
