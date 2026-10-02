# -*- coding: utf-8 -*-

"""Accolade lookups that run during the background scan.

Each provider records whether it matched, which identifier or title it used,
and why it failed. Nothing here runs on a book page request.
"""

import json
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .logger_helper import log
from .ratings.match import confident, identifiers, match_detail, title_forms

_USER_AGENT = "DeadMediaSociety/1.0 (local library catalog; accolades)"
_FRESH = timedelta(days=30)
_WIKIDATA = "https://query.wikidata.org/sparql"
_ACTION = "https://www.wikidata.org/w/api.php"
_WORK_TYPES = {"Q47461344", "Q7725634", "Q8261", "Q3331189", "Q571"}
_EDITION = "Q3331189"

# Parent awards. Category awards (Best Novel, and so on) are included
# because they are an instance of, or part of, the parent item.
AWARDS = (
    ("Q188914", "Hugo Award"),
    ("Q194285", "Nebula Award"),
    ("Q754655", "Locus Award"),
    ("Q594886", "World Fantasy Award"),
    ("Q708830", "Arthur C. Clarke Award"),
    ("Q833633", "Pulitzer Prize for Fiction"),
    ("Q160082", "Booker Prize"),
    ("Q572316", "National Book Award"),
    ("Q622813", "Newbery Medal"),
    ("Q833154", "Edgar Awards"),
    ("Q16515422", "Goodreads Choice Awards"),
    ("Q18884", "Women's Prize for Fiction"),
    ("Q848963", "Bram Stoker Award"),
)
_LABEL_AWARDS = (
    ("Bram Stoker Award", "Bram Stoker Award"),
    ("Bram Stoker Awards", "Bram Stoker Award"),
)

_rate_limited = False


def prepare():
    """Load or refresh the award lists once. Safe to call at the start of a scan."""
    missing = [(qid, label) for qid, label in AWARDS if _cache_get(qid) is None]
    if missing:
        _fetch_batched(missing)
    _wiki_rows()


def lookup(book, text):
    """Return accepted accolades and one attempt row per provider."""
    found = []
    attempts = []
    for fn in (_reverse, _wikipedia, _forward, _isfdb, _openlibrary, _google, _hardcover, _nyt, _cover):
        try:
            items, attempt = fn(book, text)
        except Exception as error:
            log.error("Accolade provider failed for book %s: %s", getattr(book, "id", None), error)
            continue
        found.extend(items or [])
        if attempt:
            attempts.append(attempt)
    return found, attempts


def save_attempts(book_id, attempts):
    from .. import ub
    from .models import AccoladeAttempt

    ub.session.query(AccoladeAttempt).filter(AccoladeAttempt.book_id == int(book_id)).delete(
        synchronize_session=False
    )
    for row in attempts:
        score = row.get("score")
        count = row.get("results")
        ub.session.add(AccoladeAttempt(
            book_id=int(book_id),
            provider=(row.get("provider") or "")[:32],
            matched=bool(row.get("matched")),
            identifier=(row.get("identifier") or "")[:200],
            reason=(row.get("reason") or "")[:80],
            query_text=(row.get("query") or "")[:400],
            result_count=int(count) if isinstance(count, int) else None,
            score=int(score) if isinstance(score, int) else None,
        ))


def accolade_report():
    """Per book provider results for the coverage page. Reads stored attempts only."""
    from collections import Counter

    from .. import calibre_db, db, ub
    from .models import AccoladeAttempt, BookAccolade

    books = calibre_db.session.query(db.Books).order_by(db.Books.sort).all()
    attempts = ub.session.query(AccoladeAttempt).all()
    by_book = {}
    for row in attempts:
        by_book.setdefault(row.book_id, []).append(row)
    have = {row.book_id for row in ub.session.query(BookAccolade.book_id).distinct()}
    report = []
    missing = []
    gaps = []
    reasons = Counter()
    for book in books:
        rows = by_book.get(book.id) or []
        providers = [_provider_row(row) for row in rows]
        if book.id not in have:
            missing.append(book.title)
            for row in rows:
                if not row.matched and row.reason:
                    reasons[row.reason] += 1
            ids = identifiers(book)
            id_bits = []
            for kind, values in ids.items():
                for value in values:
                    id_bits.append("%s %s" % (kind, value))
            gaps.append({
                "id": book.id,
                "title": book.title,
                "author": _authors(book),
                "identifiers": ", ".join(id_bits),
                "providers": providers,
            })
        report.append({
            "id": book.id,
            "title": book.title,
            "has_accolade": book.id in have,
            "providers": providers,
        })
    from .store import get_setting
    return {
        "books": report,
        "missing": missing,
        "gaps": gaps,
        "reasons": [{"name": name, "count": count} for name, count in reasons.most_common(5)],
        "nyt_key": bool((get_setting("nyt_books_key", "") or "").strip()),
        "scanned": bool(attempts),
    }


def _provider_row(row):
    return {
        "name": row.provider,
        "matched": bool(row.matched),
        "identifier": row.identifier or "",
        "reason": row.reason or "",
        "query": row.query_text or row.identifier or "",
        "results": row.result_count,
        "score": row.score,
    }


def _reverse(book, text):
    title = book.title or ""
    author = _authors(book)
    query = "%s / %s" % (title, author)
    if len(title_forms(title)) == 0:
        return [], _attempt("wikidata reverse", False, title, "no identifier", query=query, results=0)
    hits = []
    used = []
    limited = False
    best = 0
    best_author = 0
    seen = 0
    wanted = set()
    for form in title_forms(title):
        wanted.update(form.split())
    for qid, label in AWARDS:
        rows = _cached_rows(qid, label)
        if rows is None:
            if _rate_limited:
                limited = True
            continue
        seen += len(rows)
        for row in rows:
            other = set()
            for form in title_forms(row.get("title") or ""):
                other.update(form.split())
            if wanted and other and not (wanted & other):
                continue
            title_score, author_score, ok = match_detail(
                title, author, row.get("title") or "", row.get("author") or "", strict=True
            )
            if title_score > best or (title_score == best and author_score > best_author):
                best = title_score
                best_author = author_score
            if ok:
                hits.append(_award_item(label, row, qid))
                used.append(label)
                break
    kept = _keep(hits)
    if kept:
        return kept, _attempt("wikidata reverse", True, ", ".join(used[:3]), "matched", query=query, results=seen, score=best)
    if limited and not hits:
        return [], _attempt("wikidata reverse", False, title, "rate limited", query=query, results=seen, score=best)
    if hits and not kept:
        return [], _attempt("wikidata reverse", False, title, "filtered by the allowlist", query=query, results=seen, score=best)
    if best >= 80 and best_author < 80:
        reason = "author mismatch"
    elif best:
        reason = "title mismatch"
    else:
        reason = "no results"
    return [], _attempt("wikidata reverse", False, query, reason, query=query, results=seen, score=best)


_WIKI_PAGES = (
    ("Hugo Award", "Hugo Award for Best Novel"),
    ("Nebula Award", "Nebula Award for Best Novel"),
    ("Locus Award", "Locus Award for Best Science Fiction Novel"),
    ("Locus Award", "Locus Award for Best Fantasy Novel"),
    ("World Fantasy Award", "World Fantasy Award—Novel"),
    ("Arthur C. Clarke Award", "Arthur C. Clarke Award"),
    ("Pulitzer Prize", "Pulitzer Prize for Fiction"),
    ("Booker Prize", "List of winners and nominated authors of the Booker Prize"),
    ("National Book Award", "National Book Award for Fiction"),
    ("Newbery Medal", "Newbery Medal"),
    ("Edgar Award", "Edgar Award"),
    ("Bram Stoker Award", "Bram Stoker Award for Best Novel"),
    ("Women's Prize", "Women's Prize for Fiction"),
    ("Goodreads Choice", "Goodreads Choice Awards"),
)
_YEAR_HEADING = re.compile(r"^=+\s*(1[89]\d{2}|20\d{2})\b")
_ROW_YEAR = re.compile(r"\[\[(?:[^|\]]+\|)?(1[89]\d{2}|20\d{2})\]\]")
_SORTNAME = re.compile(r"\{\{sortname\|([^|{}]+)\|([^|{}]+)", re.I)
_SORTNAME_NAMED = re.compile(r"\{\{sortname\|last=([^|}]+)\|first=([^|}]+)", re.I)
_SORT_AUTHOR = re.compile(r"\{\{sort\|[^|{}]+\|\[\[([^|\]]+)(?:\|([^\]]+))?\]\]\}\}")
_PLAIN_AUTHOR = re.compile(r"^\|\s*\[\[([^|\]]+)(?:\|([^\]]+))?\]\]\s*$")
_ITALIC_LINK = re.compile(r"'{2,5}\[\[([^\]|#]+)(?:\|([^\]#]+))?\]\]'{2,5}")


def _wikipedia(book, text):
    """Match the book against cached Wikipedia award list pages."""
    title = book.title or ""
    author = _authors(book)
    query = "%s / %s" % (title, author)
    rows, problem = _wiki_rows()
    if problem and not rows:
        return [], _attempt("wikipedia", False, query, problem, query=query, results=0)
    hits = []
    used = []
    best = 0
    best_author = 0
    for row in rows:
        other = set()
        for form in title_forms(row.get("title") or ""):
            other.update(form.split())
        wanted = set()
        for form in title_forms(title):
            wanted.update(form.split())
        if wanted and other and not (wanted & other):
            continue
        title_score, author_score, ok = match_detail(
            title, author, row.get("title") or "", row.get("author") or "", strict=True
        )
        if title_score > best or (title_score == best and author_score > best_author):
            best = title_score
            best_author = author_score
        if ok:
            item = _award_item(row.get("award") or "", row, "")
            item["source"] = "wikipedia"
            item["source_url"] = row.get("url") or ""
            hits.append(item)
            used.append(row.get("award") or "")
            if len(hits) >= 3:
                break
    kept = _keep(hits)
    if kept:
        return kept, _attempt("wikipedia", True, ", ".join(used[:3]), "matched", query=query, results=len(rows), score=best)
    if best >= 80 and best_author < 80:
        reason = "author mismatch"
    elif best:
        reason = "title mismatch"
    else:
        reason = "no results"
    return [], _attempt("wikipedia", False, query, reason, query=query, results=len(rows), score=best)


def _wiki_rows():
    """Every parsed winner and nominee from the allowlisted list pages."""
    rows = []
    problem = ""
    for award, page in _WIKI_PAGES:
        cached = _cache_get("wiki:" + page)
        if cached is None:
            cached, problem = _wiki_page(award, page)
            if problem in ("rate limited", "request error"):
                return rows, problem
            _cache_put("wiki:" + page, cached or [], "")
            cached = cached or []
        rows.extend(cached or [])
    return rows, problem


def _wiki_page(award, page):
    quoted = urllib.parse.quote(page.replace(" ", "_"))
    payload, problem = _wiki_action({
        "action": "parse",
        "page": page,
        "prop": "wikitext",
        "format": "json",
    })
    if problem:
        return None, problem
    wikitext = (((payload or {}).get("parse") or {}).get("wikitext") or {}).get("*") or ""
    redirect = re.match(r"#REDIRECT\s*\[\[([^|\]]+)", wikitext or "", re.I)
    if redirect:
        return _wiki_page(award, redirect.group(1).strip())
    if not wikitext:
        return [], ""
    return _wiki_table(award, wikitext, "https://en.wikipedia.org/wiki/" + quoted), ""


def _wiki_table(award, wikitext, url):
    year = ""
    found = []
    seen = set()
    pending_author = ""
    pending_win = False
    for line in (wikitext or "").splitlines():
        heading = _YEAR_HEADING.match(line.strip())
        if heading:
            year = heading.group(1)
            pending_author = ""
            continue
        if 'scope="row' in line or line.strip().startswith("!"):
            row_year = _ROW_YEAR.search(line)
            if row_year:
                year = row_year.group(1)
            elif re.search(r"\b(1[89]\d{2}|20\d{2})\b", line) and "literature" not in line.casefold() and "''" not in line:
                bare = re.search(r"\b(1[89]\d{2}|20\d{2})\b", line)
                if bare and "scope" in line:
                    year = bare.group(1)
        person, starred = _line_author(line)
        title_match = _ITALIC_LINK.search(line)
        if person and not title_match:
            pending_author = person
            pending_win = starred
            continue
        if title_match and not person and pending_author:
            person = pending_author
            starred = pending_win
            pending_author = ""
            pending_win = False
        if title_match and not person:
            rest = line[title_match.end():]
            link = re.search(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]", rest)
            if not link:
                before = re.findall(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]", line[:title_match.start()])
                if before:
                    link_name = before[-1]
                    person = (link_name[1] or link_name[0] or "").strip()
            else:
                person = (link.group(2) or link.group(1) or "").strip()
        if not person or not title_match:
            if "{{Won" in line and found:
                found[-1]["kind"] = "win"
            continue
        raw_title = (title_match.group(2) or title_match.group(1) or "").strip()
        raw_title = re.sub(r"\s*\((novel|novella|book)\)$", "", raw_title, flags=re.I)
        if len(raw_title) < 2 or _wiki_skip_title(raw_title):
            continue
        bold = "'''''" in line
        kind = "win" if starred or bold else "nominee"
        key = (raw_title.casefold(), person.casefold(), year)
        if key in seen:
            continue
        seen.add(key)
        found.append({
            "title": raw_title,
            "author": person,
            "year": year,
            "kind": kind,
            "award": award,
            "url": url,
        })
    return found


def _line_author(line):
    named = _SORTNAME_NAMED.search(line)
    if named:
        return "%s %s" % (named.group(2).strip(), named.group(1).strip()), "}}*" in line[named.end():named.end() + 40]
    match = _SORTNAME.search(line)
    if match and not match.group(1).lower().startswith("last="):
        return "%s %s" % (match.group(1).strip(), match.group(2).strip()), "}}*" in line[match.end():match.end() + 40]
    if "''" in line:
        return "", False
    match = _SORT_AUTHOR.search(line)
    if match:
        return (match.group(2) or match.group(1) or "").strip(), False
    match = _PLAIN_AUTHOR.match(line.strip())
    if match:
        return (match.group(2) or match.group(1) or "").strip(), False
    return "", False


def _wiki_skip_title(title):
    folded = title.casefold()
    return "magazine" in folded


def _wiki_action(params):
    request = urllib.request.Request(
        "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params),
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        if error.code == 429:
            return None, "rate limited"
        return None, "request error"
    except Exception:
        return None, "request error"
    if (payload or {}).get("error"):
        return None, "no results"
    time.sleep(0.5)
    return payload, ""


def _forward(book, text):
    ids = identifiers(book)
    isbns = ids["isbn"]
    title = book.title or ""
    author = _authors(book)
    if _rate_limited and not isbns:
        return [], _attempt("wikidata forward", False, title, "rate limited")
    entity = None
    used = ""
    for isbn in isbns:
        entity = _entity_by_isbn(isbn)
        used = "ISBN %s" % isbn
        if entity:
            break
        if _rate_limited:
            return [], _attempt("wikidata forward", False, used, "rate limited")
    if entity is None and title and author:
        entity = _entity_by_title(title, author)
        used = "%s / %s" % (title, author)
    if entity is None:
        reason = "no identifier" if not isbns and not title else "no results"
        return [], _attempt("wikidata forward", False, used or title, reason)
    if not entity.get("ok"):
        return [], _attempt("wikidata forward", False, used, entity.get("reason") or "title mismatch")
    kept = _keep(entity.get("items") or [])
    if kept:
        return kept, _attempt("wikidata forward", True, used, "matched")
    if entity.get("items"):
        return [], _attempt("wikidata forward", False, used, "filtered by the allowlist")
    return [], _attempt("wikidata forward", False, used, "no results")


def _openlibrary(book, text):
    ids = identifiers(book)
    title = book.title or ""
    author = _authors(book)
    subjects = []
    used = ""
    for isbn in ids["isbn"]:
        subjects, problem = _ol_isbn(isbn)
        used = "ISBN %s" % isbn
        if problem:
            return [], _attempt("openlibrary", False, used, problem)
        if subjects:
            break
    if not subjects and title:
        subjects, problem, used_title = _ol_search(title, author)
        used = used_title or title
        if problem:
            return [], _attempt("openlibrary", False, used, problem)
    if not subjects:
        reason = "no identifier" if not ids["isbn"] and not title else "no results"
        return [], _attempt("openlibrary", False, used or title, reason)
    hits = []
    for subject in subjects:
        phrase = _subject_phrase(subject)
        if not phrase:
            continue
        from .accolades import parse_accolades
        hits.extend(parse_accolades(phrase))
    kept = _keep(hits)
    if kept:
        return kept, _attempt("openlibrary", True, used, "matched")
    if hits:
        return [], _attempt("openlibrary", False, used, "filtered by the allowlist")
    return [], _attempt("openlibrary", False, used, "no results")


def _google(book, text):
    title = book.title or ""
    author = _authors(book)
    ids = identifiers(book)
    info, used, problem = _google_volume(title, author, ids)
    if problem:
        return [], _attempt("google", False, used or title, problem)
    if not info:
        return [], _attempt("google", False, used or title, "no results")
    blob = " ".join([
        info.get("description") or "",
        " ".join(info.get("categories") or []),
    ])
    from .accolades import parse_accolades
    hits = parse_accolades(blob)
    kept = _keep(hits)
    if kept:
        return kept, _attempt("google", True, used or title, "matched")
    if hits:
        return [], _attempt("google", False, used or title, "filtered by the allowlist")
    return [], _attempt("google", False, used or title, "no results")


def _google_volume(title, author, ids):
    import requests

    url = "https://www.googleapis.com/books/v1/volumes"
    headers = {"User-Agent": _USER_AGENT}
    queries = [("isbn:" + isbn, "ISBN %s" % isbn) for isbn in ids["isbn"][:2]]
    if title and author:
        queries.append(("intitle:%s inauthor:%s" % (title.split(":")[0], author), "%s / %s" % (title, author)))
    for query, used in queries:
        try:
            response = requests.get(url, params={"q": query, "maxResults": 3}, headers=headers, timeout=12)
        except requests.RequestException:
            return None, used, "request error"
        if response.status_code == 429:
            return None, used, "rate limited"
        if response.status_code >= 400:
            return None, used, "request error"
        for item in (response.json() or {}).get("items") or []:
            info = item.get("volumeInfo") or {}
            names = ", ".join(info.get("authors") or [])
            if query.startswith("isbn:") or confident(title, author, info.get("title") or "", names):
                return info, used, ""
        if query.startswith("isbn:"):
            continue
        return None, used, "title mismatch"
    return None, title, "no identifier" if not ids["isbn"] and not title else "no results"


def _hardcover(book, text):
    from .. import ub
    from .models import HardcoverBook

    row = ub.session.query(HardcoverBook).filter(HardcoverBook.book_id == book.id).one_or_none()
    blob = ""
    if row is not None:
        blob = " ".join([row.description or "", row.series_name or ""])
    if not blob.strip():
        return [], _attempt("hardcover", False, book.title or "", "no results")
    from .accolades import parse_accolades
    hits = parse_accolades(blob)
    kept = _keep(hits)
    if kept:
        return kept, _attempt("hardcover", True, book.title or "", "matched")
    if hits:
        return [], _attempt("hardcover", False, book.title or "", "filtered by the allowlist")
    return [], _attempt("hardcover", False, book.title or "", "no results")


def _nyt(book, text):
    from .store import get_setting

    key = (get_setting("nyt_books_key", "") or "").strip()
    if not key:
        return [], None
    isbns = identifiers(book)["isbn"]
    if not isbns:
        return [], _attempt("nyt", False, book.title or "", "no identifier")
    isbn = isbns[0]
    url = "https://api.nytimes.com/svc/books/v3/lists/best-sellers/history.json?" + urllib.parse.urlencode({
        "isbn": isbn,
        "api-key": key,
    })
    payload, problem = _get_json(url)
    if problem:
        return [], _attempt("nyt", False, "ISBN %s" % isbn, problem)
    results = (payload or {}).get("results") or []
    if not results:
        return [], _attempt("nyt", False, "ISBN %s" % isbn, "no results")
    year = ""
    first = results[0] or {}
    published = str(first.get("published_date") or first.get("bestsellers_date") or "")
    match = re.search(r"(19|20)\d{2}", published)
    if match:
        year = match.group(0)
    item = {
        "type": "bestseller",
        "label": "New York Times bestseller",
        "year": year,
        "source": "nyt",
        "source_url": "https://www.nytimes.com/books/best-sellers/",
    }
    kept = _keep([item])
    if not kept:
        return [], _attempt("nyt", False, "ISBN %s" % isbn, "filtered by the allowlist")
    return kept, _attempt("nyt", True, "ISBN %s" % isbn, "matched")


def _cover(book, text):
    plain = re.sub(r"\s+", " ", text or "").strip()
    if len(plain) >= 280:
        return [], None
    binary = shutil.which("tesseract")
    if not binary:
        return [], _attempt("cover", False, book.title or "", "cover text unavailable")
    from .. import config
    import os
    folder = os.path.join(config.get_book_path(), book.path or "", "cover.jpg")
    if not os.path.isfile(folder):
        return [], _attempt("cover", False, book.title or "", "no results")
    import subprocess
    try:
        result = subprocess.run(
            [binary, folder, "stdout", "--psm", "6"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [], _attempt("cover", False, book.title or "", "request error")
    from .accolades import parse_accolades
    hits = parse_accolades(result.stdout or "")
    kept = _keep(hits)
    if kept:
        return kept, _attempt("cover", True, "cover.jpg", "matched")
    if hits:
        return [], _attempt("cover", False, "cover.jpg", "filtered by the allowlist")
    return [], _attempt("cover", False, "cover.jpg", "no results")


def _fetch_batched(awards):
    """A few SPARQL calls for every award. Wikidata allows about one a minute."""
    qids = " ".join("wd:%s" % qid for qid, _label in awards)
    bindings = _sparql_slow("""
SELECT ?parent ?award ?awardLabel WHERE {
  VALUES ?parent { %s }
  { ?award wdt:P31 ?parent } UNION { ?award wdt:P361 ?parent }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
""" % qids)
    by_parent = {qid: [] for qid, _label in awards}
    owners = {}
    for binding in bindings or []:
        parent = ((binding.get("parent") or {}).get("value") or "").rsplit("/", 1)[-1]
        label = ((binding.get("awardLabel") or {}).get("value") or "")
        category = ((binding.get("award") or {}).get("value") or "").rsplit("/", 1)[-1]
        if parent in by_parent and category and _book_category(label):
            by_parent[parent].append(category)
            owners[category] = parent
    batch = []
    grouped = {qid: [] for qid, _label in awards}
    for qid, _label in awards:
        categories = by_parent.get(qid) or [qid]
        for category in categories[:6]:
            owners[category] = qid
            batch.append(category)
            if len(batch) >= 6:
                _pull_batch(batch, owners, grouped)
                batch = []
    if batch:
        _pull_batch(batch, owners, grouped)
    for qid, _label in awards:
        _cache_put(qid, grouped.get(qid) or [], "")


def _pull_batch(categories, owners, grouped):
    values = " ".join("wd:%s" % qid for qid in categories)
    bindings = _sparql_slow("""
SELECT ?award ?workLabel ?authorLabel ?year ?kind WHERE {
  VALUES ?award { %s }
  {
    ?person p:P166 ?st .
    ?st ps:P166 ?award .
    ?st pq:P1686 ?work .
    BIND(?person AS ?author)
    BIND("win" AS ?kind)
  } UNION {
    ?person p:P1411 ?st .
    ?st ps:P1411 ?award .
    ?st pq:P1686 ?work .
    BIND(?person AS ?author)
    BIND("nominee" AS ?kind)
  } UNION {
    ?work p:P166 ?st .
    ?st ps:P166 ?award .
    FILTER NOT EXISTS { ?work wdt:P31 wd:Q5 }
    OPTIONAL { ?work wdt:P50 ?author }
    BIND("win" AS ?kind)
  } UNION {
    ?work p:P1411 ?st .
    ?st ps:P1411 ?award .
    FILTER NOT EXISTS { ?work wdt:P31 wd:Q5 }
    OPTIONAL { ?work wdt:P50 ?author }
    BIND("nominee" AS ?kind)
  }
  OPTIONAL { ?st pq:P585 ?time . BIND(YEAR(?time) AS ?year) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
""" % values)
    for binding in bindings or []:
        award = ((binding.get("award") or {}).get("value") or "").rsplit("/", 1)[-1]
        parent = owners.get(award)
        title = ((binding.get("workLabel") or {}).get("value") or "").strip()
        author = ((binding.get("authorLabel") or {}).get("value") or "").strip()
        if not parent or not title or title.startswith("Q"):
            continue
        grouped[parent].append({
            "title": title,
            "author": author,
            "year": (binding.get("year") or {}).get("value") or "",
            "kind": (binding.get("kind") or {}).get("value") or "win",
        })


def _sparql_slow(query):
    """Retry when Wikidata answers 429. One successful call, then a minute of quiet."""
    global _rate_limited
    for _try in range(4):
        _rate_limited = False
        try:
            rows = _sparql(query)
        except _Limited:
            time.sleep(65)
            continue
        time.sleep(65)
        return rows
    return []


def _award_rows(qid, label):
    cached = _cache_get(qid)
    if cached is not None:
        return cached
    if _rate_limited:
        return None
    rows = []
    try:
        for category in _book_categories(qid):
            if _rate_limited:
                break
            rows.extend(_category_rows(category))
            time.sleep(0.8)
    except _Limited:
        return None
    except Exception as error:
        log.error("Award list %s failed: %s", label, error)
        return []
    if not rows and _rate_limited:
        return None
    _cache_put(qid, rows, "")
    return rows


def _book_categories(qid):
    query = """
SELECT ?award ?awardLabel WHERE {
  { ?award wdt:P31 wd:%s } UNION { ?award wdt:P361 wd:%s } UNION { BIND(wd:%s AS ?award) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
""" % (qid, qid, qid)
    found = []
    for binding in _sparql(query):
        label = ((binding.get("awardLabel") or {}).get("value") or "").strip()
        uri = ((binding.get("award") or {}).get("value") or "")
        category = uri.rsplit("/", 1)[-1]
        if not category or not _book_category(label):
            continue
        found.append(category)
    if not found:
        found.append(qid)
    return found[:8]


def _book_category(label):
    folded = (label or "").casefold()
    if any(word in folded for word in ("reviewer", "publisher", "editor", "artist", "fan", "magazine", "dramatic", "game", "podcast", "related work", "cover")):
        return False
    return any(word in folded for word in ("novel", "novella", "novelette", "short story", "fiction", "children", "picture book", "poetry", "graphic story", "book", "literature"))


def _category_rows(qid):
    query = """
SELECT ?workLabel ?authorLabel ?year ?kind WHERE {
  {
    ?person p:P166 ?st .
    ?st ps:P166 wd:%s .
    ?st pq:P1686 ?work .
    BIND(?person AS ?author)
    BIND("win" AS ?kind)
  } UNION {
    ?person p:P1411 ?st .
    ?st ps:P1411 wd:%s .
    ?st pq:P1686 ?work .
    BIND(?person AS ?author)
    BIND("nominee" AS ?kind)
  } UNION {
    ?work p:P166 ?st .
    ?st ps:P166 wd:%s .
    FILTER NOT EXISTS { ?work wdt:P31 wd:Q5 }
    OPTIONAL { ?work wdt:P50 ?author }
    BIND("win" AS ?kind)
  } UNION {
    ?work p:P1411 ?st .
    ?st ps:P1411 wd:%s .
    FILTER NOT EXISTS { ?work wdt:P31 wd:Q5 }
    OPTIONAL { ?work wdt:P50 ?author }
    BIND("nominee" AS ?kind)
  }
  OPTIONAL { ?st pq:P585 ?time . BIND(YEAR(?time) AS ?year) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
""" % (qid, qid, qid, qid)
    rows = []
    for binding in _sparql(query):
        title = ((binding.get("workLabel") or {}).get("value") or "").strip()
        author = ((binding.get("authorLabel") or {}).get("value") or "").strip()
        if not title or title.startswith("Q") or author.startswith("Q"):
            continue
        rows.append({
            "title": title,
            "author": author,
            "year": (binding.get("year") or {}).get("value") or "",
            "kind": (binding.get("kind") or {}).get("value") or "win",
        })
    return rows


def _cached_rows(qid, label):
    if qid:
        cached = _cache_get(qid)
        return cached
    for name, award_label in _LABEL_AWARDS:
        if award_label != label:
            continue
        found = _qid_for_label(name)
        if found:
            return _cache_get(found)
    return []


def _qid_for_label(name):
    cached = _cache_get("label:" + name)
    if cached is not None:
        return (cached[0].get("qid") if cached else "")
    if _rate_limited:
        return ""
    safe = name.replace("\\", "").replace('"', "")
    query = """
SELECT ?item WHERE { ?item rdfs:label "%s"@en . } LIMIT 1
""" % safe
    try:
        bindings = _sparql(query)
    except _Limited:
        return ""
    except Exception:
        return ""
    qid = ""
    if bindings:
        uri = (bindings[0].get("item") or {}).get("value") or ""
        qid = uri.rsplit("/", 1)[-1]
    _cache_put("label:" + name, [{"qid": qid}] if qid else [], "")
    return qid


def _entity_by_isbn(isbn):
    global _rate_limited
    digits = re.sub(r"[^0-9Xx]", "", isbn or "")
    prop = "P212" if len(digits) == 13 else "P957"
    payload, problem = _action({
        "action": "query",
        "list": "search",
        "srsearch": "haswbstatement:%s=%s" % (prop, digits),
        "srlimit": "1",
    })
    if problem == "rate limited":
        _rate_limited = True
        return None
    if problem:
        return {"ok": False, "reason": problem, "items": []}
    hits = ((payload or {}).get("query") or {}).get("search") or []
    if not hits:
        return None
    return _entity_awards(hits[0].get("title") or "")


def _entity_by_title(title, author):
    payload, problem = _action({
        "action": "wbsearchentities",
        "search": title.split(":")[0],
        "language": "en",
        "type": "item",
        "limit": "5",
    })
    if problem == "rate limited":
        return {"ok": False, "reason": "rate limited", "items": []}
    if problem:
        return {"ok": False, "reason": problem, "items": []}
    for hit in (payload or {}).get("search") or []:
        entity = _entity_awards(hit.get("id") or "", title, author)
        if entity and entity.get("ok"):
            return entity
    return None


def _entity_awards(qid, title="", author=""):
    if not qid:
        return None
    payload, problem = _action({
        "action": "wbgetentities",
        "ids": qid,
        "props": "claims|labels",
        "languages": "en",
    })
    if problem:
        return {"ok": False, "reason": problem, "items": []}
    entity = ((payload or {}).get("entities") or {}).get(qid) or {}
    claims = entity.get("claims") or {}
    types = _claim_ids(claims, "P31")
    if types and not (types & _WORK_TYPES):
        return {"ok": False, "reason": "title mismatch", "items": []}
    work_id = qid
    if _EDITION in types:
        parents = _claim_ids(claims, "P629") or _claim_ids(claims, "P747")
        if parents:
            work_id = sorted(parents)[0]
            if work_id != qid:
                parent = _entity_awards(work_id, title, author)
                if parent and parent.get("items"):
                    return parent
    if title and author:
        label = ((entity.get("labels") or {}).get("en") or {}).get("value") or ""
        names = _author_names(_claim_ids(claims, "P50"))
        if label and names and not confident(title, author, label, ", ".join(names)):
            return {"ok": False, "reason": "title mismatch", "items": []}
    items = []
    for prop, kind in (("P166", "win"), ("P1411", "nominee")):
        for claim in claims.get(prop) or []:
            award_id = (((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}).get("id")
            year = _qualifier_year(claim)
            if not award_id or not year:
                continue
            items.append({
                "type": "award_win" if kind == "win" else "award_nominee",
                "label": _award_label(award_id),
                "year": year,
                "source": "wikidata",
                "source_url": "https://www.wikidata.org/wiki/" + award_id,
            })
    return {"ok": True, "items": items}


def _award_label(qid):
    for known, label in AWARDS:
        if known == qid:
            return label
    payload, problem = _action({
        "action": "wbgetentities",
        "ids": qid,
        "props": "labels",
        "languages": "en",
    })
    if problem or not payload:
        return ""
    entity = ((payload.get("entities") or {}).get(qid) or {})
    return ((entity.get("labels") or {}).get("en") or {}).get("value") or ""


def _author_names(qids):
    names = []
    for qid in list(qids)[:4]:
        payload, problem = _action({
            "action": "wbgetentities",
            "ids": qid,
            "props": "labels",
            "languages": "en",
        })
        if problem or not payload:
            continue
        entity = ((payload.get("entities") or {}).get(qid) or {})
        name = ((entity.get("labels") or {}).get("en") or {}).get("value") or ""
        if name:
            names.append(name)
    return names


def _ol_isbn(isbn):
    digits = re.sub(r"[^0-9Xx]", "", isbn or "")
    payload, problem = _get_json("https://openlibrary.org/isbn/%s.json" % digits)
    if problem:
        return [], problem
    works = (payload or {}).get("works") or []
    if not works:
        subjects = (payload or {}).get("subjects") or []
        return subjects, ""
    key = (works[0] or {}).get("key") or ""
    if not key:
        return [], ""
    work, problem = _get_json("https://openlibrary.org%s.json" % key)
    if problem:
        return [], problem
    return (work or {}).get("subjects") or [], ""


def _ol_search(title, author):
    query = urllib.parse.urlencode({
        "title": title.split(":")[0],
        "author": author,
        "limit": 5,
        "fields": "key,title,author_name,subject",
    })
    payload, problem = _get_json("https://openlibrary.org/search.json?" + query)
    if problem:
        return [], problem, title
    for doc in (payload or {}).get("docs") or []:
        names = ", ".join(doc.get("author_name") or [])
        if confident(title, author, doc.get("title") or "", names):
            return doc.get("subject") or [], "", doc.get("title") or title
    return [], "", title


def _subject_phrase(subject):
    text = (subject or "").strip()
    folded = text.casefold()
    if folded.startswith("nyt:") or folded.startswith("nyt "):
        return "New York Times bestseller"
    return text


def _award_item(label, row, qid):
    kind = row.get("kind") or "win"
    return {
        "type": "award_win" if kind == "win" else "award_nominee",
        "label": "%s %s" % (label, "winner" if kind == "win" else "nominee"),
        "year": row.get("year") or "",
        "source": "wikidata",
        "source_url": ("https://www.wikidata.org/wiki/" + qid) if qid else "",
    }


def _keep(items):
    from .accolades import _accept_item
    kept = []
    seen = set()
    for item in items or []:
        accepted = _accept_item(item)
        if not accepted:
            continue
        key = (accepted.get("label") or "").casefold()
        if key in seen:
            continue
        seen.add(key)
        accepted["_ready"] = True
        kept.append(accepted)
    return kept


def _attempt(provider, matched, identifier, reason, query="", results=None, score=None):
    return {
        "provider": provider,
        "matched": matched,
        "identifier": identifier or "",
        "reason": "matched" if matched else reason,
        "query": query or identifier or "",
        "results": results,
        "score": score,
    }


_isfdb_down = False


def _isfdb(book, text):
    """ISFDB publication record, matched by ISBN. Cached. Stops after one outage."""
    global _isfdb_down
    title = book.title or ""
    isbns = identifiers(book)["isbn"]
    if not isbns:
        return [], _attempt("isfdb", False, title, "no identifier", query=title, results=0)
    if _isfdb_down:
        return [], _attempt("isfdb", False, "ISBN %s" % isbns[0], "request error", query="ISBN %s" % isbns[0], results=0)
    isbn = isbns[0]
    query = "ISBN %s" % isbn
    cached = _cache_get("isfdb:" + isbn)
    if cached is None:
        xml, problem = _get_text("https://www.isfdb.org/cgi-bin/rest/getpub.cgi?ISBN+" + isbn)
        if problem or not _isfdb_record(xml):
            _isfdb_down = True
            return [], _attempt("isfdb", False, query, problem or "request error", query=query, results=0)
        awards = _isfdb_awards(xml or "")
        _cache_put("isfdb:" + isbn, awards, "")
        cached = awards
    hits = []
    for label in cached or []:
        hits.append({
            "type": "award_win",
            "label": label,
            "year": "",
            "source": "isfdb",
            "source_url": "https://www.isfdb.org/cgi-bin/se.cgi?arg=%s&type=ISBN" % isbn,
        })
    kept = _keep(hits)
    if kept:
        return kept, _attempt("isfdb", True, query, "matched", query=query, results=len(cached or []), score=100)
    if hits:
        return [], _attempt("isfdb", False, query, "filtered by the allowlist", query=query, results=len(hits))
    return [], _attempt("isfdb", False, query, "no results", query=query, results=0)


def _isfdb_record(xml):
    text = (xml or "").lstrip()
    if not text or "error code" in text[:240].casefold():
        return False
    return "<Title" in text or "<Error" in text or "<Publications" in text


def _isfdb_awards(xml):
    found = []
    for match in re.finditer(r"<Award>(.*?)</Award>", xml or "", re.I | re.S):
        label = re.sub(r"<[^>]+>", " ", match.group(1))
        label = " ".join(label.split())
        if label and label not in found:
            found.append(label)
    return found


def _get_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/xml,text/xml"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return response.read().decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as error:
        if error.code == 429:
            return "", "rate limited"
        return "", "request error"
    except Exception:
        return "", "request error"


def _authors(book):
    names = []
    for author in getattr(book, "authors", None) or []:
        name = (getattr(author, "name", "") or "").replace("|", " ").strip()
        if name:
            names.append(name)
    return ", ".join(names)


def _cache_get(key):
    from .. import ub
    from .models import AwardCache

    row = ub.session.query(AwardCache).filter(AwardCache.award_key == key).one_or_none()
    if row is None or not row.fetched_at:
        return None
    fetched = row.fetched_at
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - fetched > _FRESH:
        return None
    if row.error == "rate limited":
        return None
    try:
        return json.loads(row.payload or "[]")
    except ValueError:
        return None


def _cache_put(key, rows, error):
    from .. import ub
    from .models import AwardCache

    row = ub.session.query(AwardCache).filter(AwardCache.award_key == key).one_or_none()
    if row is None:
        row = AwardCache(award_key=key)
        ub.session.add(row)
    row.payload = json.dumps(rows)
    row.error = (error or "")[:200]
    row.fetched_at = datetime.now(timezone.utc)
    ub.session_commit("Award cache %s" % key)


def _sparql(query):
    global _rate_limited
    url = _WIKIDATA + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/sparql-results+json"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 429:
            _rate_limited = True
            raise _Limited()
        raise
    return ((payload.get("results") or {}).get("bindings") or [])


def _action(params):
    global _rate_limited
    if _rate_limited:
        return None, "rate limited"
    query = dict(params)
    query["format"] = "json"
    url = _ACTION + "?" + urllib.parse.urlencode(query)
    payload, problem = _get_json(url)
    if problem == "rate limited":
        _rate_limited = True
    time.sleep(0.4)
    return payload, problem


def _get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8")), ""
    except urllib.error.HTTPError as error:
        if error.code == 429:
            return None, "rate limited"
        return None, "request error"
    except Exception:
        return None, "request error"


def _claim_ids(claims, prop):
    found = set()
    for claim in claims.get(prop) or []:
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        if isinstance(value, dict) and value.get("id"):
            found.add(value["id"])
    return found


def _qualifier_year(claim):
    for qual in (claim.get("qualifiers") or {}).get("P585") or []:
        value = ((qual.get("datavalue") or {}).get("value") or {})
        match = re.search(r"(19|20)\d{2}", str(value.get("time") or ""))
        if match:
            return match.group(0)
    return ""


class _Limited(Exception):
    pass
