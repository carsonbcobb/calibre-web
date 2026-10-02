# -*- coding: utf-8 -*-

"""Recognitions worth showing on a book.

Edit this file to add or remove an award, bestseller list, adaptation, or
curated list. A stored accolade is kept only when its text matches one entry.
Hardcover shelves that are just user lists do not match and are dropped.
"""

import re

# Longer names first so "national book critics circle" wins over "national book".
AWARDS = (
    ("national book critics circle", "National Book Critics Circle"),
    ("national book award", "National Book Award"),
    ("coretta scott king", "Coretta Scott King"),
    ("arthur c. clarke", "Arthur C. Clarke"),
    ("arthur c clarke", "Arthur C. Clarke"),
    ("goodreads choice", "Goodreads Choice"),
    ("philip k. dick", "Philip K. Dick"),
    ("philip k dick", "Philip K. Dick"),
    ("shirley jackson", "Shirley Jackson"),
    ("world fantasy", "World Fantasy"),
    ("british fantasy", "British Fantasy"),
    ("bram stoker", "Bram Stoker"),
    ("michael l. printz", "Printz"),
    ("women's prize", "Women's Prize"),
    ("womens prize", "Women's Prize"),
    ("orange prize", "Women's Prize"),
    ("lambda literary", "Lambda Literary"),
    ("pen/faulkner", "PEN Faulkner"),
    ("pen faulkner", "PEN Faulkner"),
    ("carnegie medal", "Carnegie"),
    ("pura belpre", "Pura Belpre"),
    ("mythopoeic", "Mythopoeic"),
    ("nobel prize", "Nobel Prize"),
    ("pulitzer", "Pulitzer"),
    ("newbery", "Newbery"),
    ("caldecott", "Caldecott"),
    ("stonewall", "Stonewall"),
    ("nebula", "Nebula"),
    ("printz", "Printz"),
    ("whitbread", "Costa"),
    ("booker", "Booker"),
    ("locus", "Locus"),
    ("edgar", "Edgar"),
    ("costa", "Costa"),
    ("eisner", "Eisner"),
    ("ignyte", "Ignyte"),
    ("hugo", "Hugo"),
)

BESTSELLERS = (
    ("new york times", "NYT"),
    ("usa today", "USA Today"),
    ("sunday times", "Sunday Times"),
    ("nyt", "NYT"),
)

ADAPTATIONS = (
    ("netflix", "Netflix Series"),
    ("motion picture", "Major Motion Picture"),
    ("feature film", "Film"),
    ("tv series", "TV Series"),
    ("television series", "TV Series"),
)

CURATED_LISTS = (
    ("npr top 100", "NPR Top 100"),
    ("npr's top 100", "NPR Top 100"),
    ("bbc big read", "BBC Big Read"),
    ("modern library 100", "Modern Library 100"),
    ("modern library's 100", "Modern Library 100"),
    ("time 100", "Time 100"),
)

_AWARD_WORDS = ("award", "prize", "winner", "nominee", "nominated", "medal", "shortlist", "longlist")
_NOMINEE_WORDS = ("nominee", "nominated", "shortlist", "longlist")


def classify(text):
    """Return a recognition dict, or None when the text is not on the allowlist."""
    folded = (text or "").casefold().replace("’", "'")
    if not folded.strip():
        return None
    for needle, name in CURATED_LISTS:
        if _has(folded, needle):
            return {"group": "list", "type": "list", "label": name}
    for needle, name in AWARDS:
        if not _has(folded, needle):
            continue
        if not any(word in folded for word in _AWARD_WORDS):
            continue
        kind = "award_nominee" if any(word in folded for word in _NOMINEE_WORDS) else "award_win"
        label = name
        if "longlist" in folded:
            label = "%s Longlist" % name
        elif "shortlist" in folded:
            label = "%s Shortlist" % name
        return {"group": "award", "type": kind, "label": label}
    if re.search(r"best[\s-]?seller", folded):
        for needle, name in BESTSELLERS:
            if _has(folded, needle):
                return {"group": "bestseller", "type": "bestseller", "label": name}
    for needle, name in ADAPTATIONS:
        if not _has(folded, needle):
            continue
        if needle == "netflix" and "series" not in folded and "adaptation" not in folded:
            continue
        return {"group": "adaptation", "type": "adaptation", "label": name}
    return None


def accept(item):
    """Normalize one accolade. Wikidata rows need a year and a real award name."""
    if not item:
        return None
    label = (item.get("label") or "").strip()
    hit = classify(label)
    if hit is None:
        return None
    source = (item.get("source") or "").strip()
    year = item.get("year")
    if source == "wikidata":
        if not year:
            return None
        if hit["group"] != "award":
            return None
        kind = item.get("type") if item.get("type") in ("award_win", "award_nominee") else hit["type"]
    else:
        kind = hit["type"]
    return {
        "type": kind,
        "label": hit["label"],
        "year": year,
        "source": source,
        "source_url": item.get("source_url") or "",
    }


def _has(folded, needle):
    return re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", folded) is not None
