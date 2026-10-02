# -*- coding: utf-8 -*-

"""Sourced series descriptions. Page loads only read series_info.

Hardcover, then Wikipedia, then Open Library. Manual rows are never overwritten.
Nothing here writes metadata.db.
"""

import re
import time
from datetime import datetime, timedelta, timezone

import requests

from .logger_helper import log
from .units import _hours

_UA = "DeadMediaSociety/1.0 (local library catalog)"
_HIT = timedelta(days=30)
_MISS = timedelta(days=7)
_BOOKISH = ("series", "trilogy", "saga", "novels", "novel", "chronicle", "cycle", "books")
_REJECT = ("video game", "television", "tv series", "film", "movie", "album", "soundtrack", "song")
_SOURCE_LABELS = {
    "hardcover": "Hardcover",
    "wikipedia": "Wikipedia",
    "openlibrary": "Open Library",
    "manual": "Manual",
}
_WIKI_BLOCKED = False

_HC_SEARCH = """
query ($q: String!) {
  search(query: $q, query_type: "Series", per_page: 5, page: 1) {
    results
  }
}
"""

_HC_SERIES = """
query ($ids: [Int!]) {
  series(where: {id: {_in: $ids}}) {
    id
    name
    slug
    description
    books_count
    primary_books_count
    is_completed
    author { name }
  }
}
"""


def present(series_id, author="", count=0, minutes=None):
    """Display copy for a series hero. Never calls the network."""
    row = _row(series_id)
    text = _clean(row.description if row is not None else "")
    complete = row.is_complete if row is not None else None
    if text:
        excerpt, rest = _split(text)
        source = (row.source or "").strip()
        return {
            "excerpt": excerpt,
            "rest": rest,
            "source_name": _SOURCE_LABELS.get(source, ""),
            "source_url": (row.source_url or "").strip(),
            "factual": False,
            "manual": bool(row.manual),
        }
    return {
        "excerpt": _factual(count, author, minutes, complete),
        "rest": "",
        "source_name": "",
        "source_url": "",
        "factual": True,
        "manual": bool(row.manual) if row is not None else False,
    }


def form_text(series_id):
    """Stored description for the admin editor. Empty when the page is on the fallback line."""
    row = _row(series_id)
    if row is None:
        return "", ""
    return _clean(row.description), (row.source_url or "").strip()


def save_manual(series_id, description, source_url):
    """Admin text. An empty description clears the manual lock so a scan can fill it."""
    from .. import ub
    from .models import SeriesInfo

    text = _clean(description)[:4000]
    url = (source_url or "").strip()[:400]
    row = _row(series_id)
    if row is None:
        row = SeriesInfo(series_id=int(series_id))
        ub.session.add(row)
    row.description = text
    row.source_url = url
    row.source = "manual" if text else ""
    row.manual = bool(text)
    row.fetched_at = datetime.now(timezone.utc)
    ub.session_commit("Series description saved")
    return True


def _save_attempts(series_id, attempts):
    from .. import ub
    from .models import SeriesAttempt

    ub.session.query(SeriesAttempt).filter(SeriesAttempt.series_id == int(series_id)).delete(
        synchronize_session=False
    )
    for row in attempts or []:
        score = row.get("score")
        count = row.get("results")
        ub.session.add(SeriesAttempt(
            series_id=int(series_id),
            provider=(row.get("provider") or "")[:32],
            matched=bool(row.get("matched")),
            query_text=(row.get("query") or "")[:400],
            result_count=int(count) if isinstance(count, int) else None,
            score=int(score) if isinstance(score, int) else None,
            reason=(row.get("reason") or "")[:80],
        ))


def coverage():
    """Series with a real description, and names still on the fallback line."""
    from collections import Counter

    from .. import calibre_db, db, ub
    from .models import SeriesAttempt, SeriesInfo

    try:
        rows = ub.session.query(SeriesInfo).all()
        attempts = ub.session.query(SeriesAttempt).all()
    except Exception:
        ub.session.rollback()
        return {"real": 0, "fallback": [], "gaps": [], "reasons": []}
    names = _series_names()
    by_series = {}
    reasons = Counter()
    for row in attempts:
        by_series.setdefault(int(row.series_id), []).append(row)
    authors = {}
    try:
        for book in calibre_db.session.query(db.Books).all():
            if not book.series:
                continue
            series_id = int(book.series[0].id)
            if series_id in authors or not book.authors:
                continue
            authors[series_id] = (book.authors[0].name or "").replace("|", " ")
    except Exception:
        pass
    real = 0
    fallback = []
    gaps = []
    seen = set()
    empty = set()
    for row in rows:
        seen.add(int(row.series_id))
        if (row.description or "").strip() and int(row.series_id) in names:
            real += 1
        elif int(row.series_id) in names:
            empty.add(int(row.series_id))
    for series_id, name in names.items():
        if series_id not in seen or series_id in empty:
            fallback.append(name)
            providers = []
            for attempt in by_series.get(int(series_id), []):
                if not attempt.matched and attempt.reason:
                    reasons[attempt.reason] += 1
                providers.append({
                    "name": attempt.provider,
                    "query": attempt.query_text or "",
                    "results": attempt.result_count,
                    "score": attempt.score,
                    "reason": attempt.reason or "",
                    "matched": bool(attempt.matched),
                })
            gaps.append({
                "id": series_id,
                "name": name,
                "author": authors.get(series_id) or "",
                "providers": providers,
            })
    fallback.sort(key=lambda name: name.lower())
    gaps.sort(key=lambda item: item["name"].lower())
    return {
        "real": real,
        "fallback": fallback,
        "gaps": gaps,
        "reasons": [{"name": name, "count": count} for name, count in reasons.most_common(5)],
    }


def enqueue_scan(user_name, ignore_miss=False):
    from flask import current_app
    from ..services.worker import WorkerThread

    application = current_app._get_current_object()
    WorkerThread.add(user_name or "admin", task_instance(application, ignore_miss), hidden=False)


def scan_library(task, application, ignore_miss=False):
    """Fill series_info. Manual rows stay. Hits last 30 days, misses 7 days.

    ignore_miss retries series that are still on the fallback line.
    """
    global _WIKI_BLOCKED
    from ..services.worker import STAT_CANCELLED, STAT_ENDED

    _WIKI_BLOCKED = False
    groups = _groups(application)
    total = len(groups)
    before = sum(1 for group in groups if _has_text(group["id"]))
    real = 0
    fallback = 0
    limited = 0
    for index, group in enumerate(groups):
        if task is not None and task.stat in (STAT_CANCELLED, STAT_ENDED):
            break
        try:
            status = _scan_one(
                group["id"], group["name"], group["author"], group.get("blurb") or "",
                group.get("book_title") or "", ignore_miss,
            )
        except Exception as error:
            status = "error"
            log.error("Series info scan %s failed: %s", group.get("id"), error)
        if status == "rate limited":
            limited += 1
            fallback += 1
        elif _has_text(group["id"]):
            real += 1
        else:
            fallback += 1
        if task is not None and total:
            task.progress = min(1, float(index + 1) / float(total))
    return before, real, fallback, limited


def task_instance(application, ignore_miss=False):
    from ..services.worker import STAT_CANCELLED, STAT_ENDED, CalibreTask

    class _Task(CalibreTask):
        def __init__(self, app_obj, retry_misses):
            super(_Task, self).__init__("Scan series info")
            self.application = app_obj
            self.retry_misses = retry_misses

        def run(self, worker_thread):
            with self.application.app_context():
                before, real, fallback, limited = scan_library(
                    self, self.application, ignore_miss=self.retry_misses,
                )
            self.progress = 1
            self.message = "Series with a real description: %s before, %s after. %s are still on the fallback line." % (
                before, real, fallback,
            )
            if limited:
                self.message += " %s were rate limited and will be tried again." % limited
            if self.stat not in (STAT_CANCELLED, STAT_ENDED):
                self._handleSuccess()

        @property
        def name(self):
            return "Rescan unmatched" if self.retry_misses else "Scan series info"

        @property
        def is_cancellable(self):
            return True

    return _Task(application, ignore_miss)


def _scan_one(series_id, name, author, book_blurb="", book_title="", ignore_miss=False):
    row = _row(series_id)
    if row is not None and row.manual:
        return "manual"
    if _fresh(row, ignore_miss):
        return "fresh"
    found = _gather(name, author, book_blurb, book_title)
    _save_attempts(series_id, found.get("attempts") or [])
    if found.get("blocked") and not found.get("description"):
        return "rate limited"
    _store(series_id, found, row)
    return "hit" if found.get("description") else "miss"


def _gather(name, author, book_blurb="", book_title=""):
    found = {
        "description": "", "source": "", "source_url": "",
        "is_complete": None, "reported": None, "blocked": False, "attempts": [],
    }
    hardcover, note = _hardcover(name, author, book_blurb)
    found["attempts"].append(note)
    if hardcover:
        found["is_complete"] = hardcover.get("is_complete")
        found["reported"] = hardcover.get("reported")
        if hardcover.get("description"):
            found["description"] = hardcover["description"]
            found["source"] = "hardcover"
            found["source_url"] = hardcover.get("source_url") or ""
            return found
    wiki, note = _wikipedia(name, author, book_blurb)
    found["attempts"].append(note)
    if wiki is None and _WIKI_BLOCKED:
        found["blocked"] = True
    elif wiki and wiki.get("description"):
        found["description"] = wiki["description"]
        found["source"] = "wikipedia"
        found["source_url"] = wiki.get("source_url") or ""
        return found
    page, note = _book_page(name, author, book_title, book_blurb)
    found["attempts"].append(note)
    if page and page.get("description"):
        found["description"] = page["description"]
        found["source"] = "wikipedia"
        found["source_url"] = page.get("source_url") or ""
        return found
    library, note = _openlibrary(name, author, book_blurb)
    found["attempts"].append(note)
    if library and library.get("description"):
        found["description"] = library["description"]
        found["source"] = "openlibrary"
        found["source_url"] = library.get("source_url") or ""
    return found


def _note(provider, query, results, score, reason, matched=False):
    return {
        "provider": provider,
        "query": query or "",
        "results": results,
        "score": score,
        "reason": "matched" if matched else reason,
        "matched": matched,
    }


def _hardcover(name, author, book_blurb=""):
    from .ratings.hardcover import _hits, _post

    query = name if not author else "%s %s" % (name, author)
    payload = _post(_HC_SEARCH, {"q": query})
    if not isinstance(payload, dict):
        return None, _note("hardcover", query, 0, None, "request error")
    hits = _hits(((payload.get("data") or {}).get("search") or {}).get("results"))
    ids = []
    for hit in hits:
        if _name_close(name, hit.get("name") or "") and _author_ok(author, hit.get("author_name") or ""):
            if str(hit.get("id") or "").isdigit():
                ids.append(int(hit["id"]))
    if not ids:
        return None, _note("hardcover", query, len(hits), None, "title mismatch")
    payload = _post(_HC_SERIES, {"ids": ids[:5]})
    if not isinstance(payload, dict):
        return None, _note("hardcover", query, len(ids), None, "request error")
    rows = ((payload.get("data") or {}).get("series")) or []
    best = None
    best_score = -1
    for row in rows:
        if not _name_close(name, row.get("name") or ""):
            continue
        author_name = ((row.get("author") or {}).get("name") or "")
        if not _author_ok(author, author_name):
            continue
        score = _ratio(name, row.get("name") or "")
        text = _clean(row.get("description") or "")
        usable = text if len(text) >= 40 and not _rejected(text) and not _same_book(text, book_blurb) else ""
        if usable:
            score += 20
        if best is not None and best.get("description") and not usable:
            continue
        if score > best_score:
            best_score = score
            reported = row.get("primary_books_count") or row.get("books_count")
            try:
                reported = int(reported) if reported else None
            except (TypeError, ValueError):
                reported = None
            if reported is not None and reported <= 0:
                reported = None
            complete = row.get("is_completed")
            if not isinstance(complete, bool):
                complete = None
            slug = (row.get("slug") or "").strip()
            best = {
                "description": usable,
                "source_url": ("https://hardcover.app/series/" + slug) if slug else "",
                "is_complete": complete,
                "reported": reported,
            }
    if best and best.get("description"):
        return best, _note("hardcover", query, len(rows), best_score, "matched", True)
    if best_score >= 0:
        return best, _note("hardcover", query, len(rows), best_score if best_score >= 0 else None, "no results")
    return None, _note("hardcover", query, len(rows), None, "title mismatch")


def _name_queries(name):
    found = []

    def add(text):
        text = " ".join((text or "").split())
        if text and text.casefold() not in {item.casefold() for item in found}:
            found.append(text)

    add(name)
    words = (name or "").split()
    drop = {"series", "trilogy", "saga", "cycle", "chronicles", "chronicle"}
    if words and words[-1].casefold() in drop:
        add(" ".join(words[:-1]))
    if words and words[0].casefold() == "the":
        add(" ".join(words[1:]))
    queries = []
    for item in list(found):
        queries.append(item)
        extra = "%s novel series" % item
        if extra.casefold() not in {query.casefold() for query in queries}:
            queries.append(extra)
    return queries


def _wikipedia(name, author, book_blurb=""):
    global _WIKI_BLOCKED
    queries = _name_queries(name)
    if _WIKI_BLOCKED:
        return None, _note("wikipedia", queries[0] if queries else name, 0, None, "rate limited")
    best_score = 0
    seen = 0
    for query in queries:
        found, score, count, blocked = _wiki_search(name, author, book_blurb, query)
        seen += count
        if score > best_score:
            best_score = score
        if blocked:
            return None, _note("wikipedia", query, seen, best_score or None, "rate limited")
        if found:
            return found, _note("wikipedia", query, seen, score or None, "matched", True)
    return None, _note("wikipedia", " | ".join(queries[:4]), seen, best_score or None, "no results" if not seen else "title mismatch")


def _wiki_search(name, author, book_blurb, query):
    hits = _wiki_json("https://www.wikidata.org/w/api.php", {
        "action": "wbsearchentities",
        "search": query,
        "language": "en",
        "type": "item",
        "limit": 5,
        "format": "json",
    })
    if hits is None:
        return None, 0, 0, _WIKI_BLOCKED
    results = (hits.get("search") or [])[:5]
    best = 0
    for hit in results:
        label = hit.get("label") or ""
        desc = hit.get("description") or ""
        score = _ratio(name, label)
        if score > best:
            best = score
        base = query.replace(" novel series", "").strip()
        if not (_name_close(name, label) or _name_close(base, label)) or _rejected(desc) or not _series_like(desc):
            continue
        qid = hit.get("id") or ""
        if not qid:
            continue
        entity = _wiki_json("https://www.wikidata.org/w/api.php", {
            "action": "wbgetentities",
            "ids": qid,
            "props": "sitelinks",
            "sitefilter": "enwiki",
            "format": "json",
        })
        if not entity:
            continue
        title = ((((entity.get("entities") or {}).get(qid) or {}).get("sitelinks") or {}).get("enwiki") or {}).get("title") or ""
        if not title:
            continue
        page = _wiki_json("https://en.wikipedia.org/w/api.php", {
            "action": "query",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "redirects": 1,
            "titles": title,
            "format": "json",
        })
        if not page:
            continue
        extract = ""
        for item in ((page.get("query") or {}).get("pages") or {}).values():
            extract = item.get("extract") or ""
        text = _clean(extract)
        if len(text) < 40 or "may refer to" in text.casefold() or _same_book(text, book_blurb):
            continue
        if _rejected(text[:240]) or not (_bookish(desc) or _bookish(text[:400])):
            continue
        if not _author_ok(author, "%s %s" % (desc, text[:500])):
            continue
        slug = title.replace(" ", "_")
        return {
            "description": text[:4000],
            "source_url": "https://en.wikipedia.org/wiki/" + requests.utils.quote(slug),
        }, best, len(results), False
    return None, best, len(results), False


def _book_page(name, author, book_title, book_blurb):
    """Book 1's Wikipedia lead, only when it describes the series."""
    if not book_title or _WIKI_BLOCKED:
        reason = "rate limited" if _WIKI_BLOCKED else "no identifier"
        return None, _note("book 1 wikipedia", book_title or name, 0, None, reason)
    hits = _wiki_json("https://en.wikipedia.org/w/api.php", {
        "action": "query",
        "list": "search",
        "srsearch": "%s %s" % (book_title, author),
        "srlimit": 3,
        "format": "json",
    })
    if hits is None:
        return None, _note("book 1 wikipedia", book_title, 0, None, "rate limited" if _WIKI_BLOCKED else "request error")
    results = ((hits.get("query") or {}).get("search") or [])[:3]
    for hit in results:
        title = hit.get("title") or ""
        if not title or not _name_close(book_title, title):
            continue
        page = _wiki_json("https://en.wikipedia.org/w/api.php", {
            "action": "query",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "redirects": 1,
            "titles": title,
            "format": "json",
        })
        if not page:
            continue
        extract = ""
        for item in ((page.get("query") or {}).get("pages") or {}).values():
            extract = item.get("extract") or ""
        text = _clean(extract)
        folded = text.casefold()
        if len(text) < 40 or not _about_the_series(folded, name):
            continue
        if _same_book(text, book_blurb) or _rejected(text[:240]):
            continue
        if not _author_ok(author, text[:500]):
            continue
        slug = title.replace(" ", "_")
        return {
            "description": text[:4000],
            "source_url": "https://en.wikipedia.org/wiki/" + requests.utils.quote(slug),
        }, _note("book 1 wikipedia", title, len(results), _ratio(book_title, title), "matched", True)
    return None, _note("book 1 wikipedia", book_title, len(results), None, "no results")


def _openlibrary(name, author, book_blurb=""):
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    query = "series:%s" % slug if slug else name
    if not slug:
        return None, _note("openlibrary", query, 0, None, "no identifier")
    url = "https://openlibrary.org/subjects/series:%s.json" % slug
    try:
        response = requests.get(url, headers={"User-Agent": _UA}, timeout=15)
    except requests.RequestException:
        return None, _note("openlibrary", query, 0, None, "request error")
    if response.status_code != 200:
        return None, _note("openlibrary", query, 0, None, "request error" if response.status_code >= 400 else "no results")
    try:
        payload = response.json()
    except ValueError:
        return None, _note("openlibrary", query, 0, None, "request error")
    raw = payload.get("description") or ""
    if isinstance(raw, dict):
        raw = raw.get("value") or ""
    text = _clean(raw)
    works = len(payload.get("works") or [])
    if len(text) < 40 or name.casefold() not in text.casefold() or _same_book(text, book_blurb) or _rejected(text):
        return None, _note("openlibrary", query, works, None, "no results")
    if not _author_ok(author, text):
        return None, _note("openlibrary", query, works, None, "title mismatch")
    return {
        "description": text[:4000],
        "source_url": "https://openlibrary.org/subjects/series:%s" % slug,
    }, _note("openlibrary", query, works, 100, "matched", True)


def _about_the_series(folded, name):
    """True when the lead is about the series, not one novel that mentions it."""
    if "series" not in folded or _flat(name) not in _flat(folded):
        return False
    novel = re.search(r"\bis an? (?:\w+ ){0,6}novel\b", folded)
    if novel and "book series" not in folded and "novel series" not in folded and "is a series" not in folded:
        return False
    return True


def _wiki_json(url, params):
    global _WIKI_BLOCKED
    if _WIKI_BLOCKED:
        return None
    time.sleep(0.8)
    try:
        response = requests.get(url, params=params, headers={"User-Agent": _UA}, timeout=20)
    except requests.RequestException as error:
        log.debug("Series wiki request failed: %s", error)
        return None
    if response.status_code == 429:
        _WIKI_BLOCKED = True
        log.info("Series wiki lookup is rate limited. Later series will wait for the next scan.")
        return None
    if response.status_code >= 400:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _store(series_id, found, row):
    from .. import ub
    from .models import SeriesInfo

    if row is None:
        row = SeriesInfo(series_id=int(series_id))
        ub.session.add(row)
    row.description = found.get("description") or ""
    row.source = found.get("source") or ""
    row.source_url = found.get("source_url") or ""
    if found.get("is_complete") is not None:
        row.is_complete = found.get("is_complete")
    if found.get("reported"):
        row.total_books_reported = found.get("reported")
    row.manual = False
    row.fetched_at = datetime.now(timezone.utc)
    ub.session_commit("Series info stored")


def _fresh(row, ignore_miss=False):
    if row is None or row.fetched_at is None:
        return False
    age = _age(row.fetched_at)
    if age is None:
        return False
    if (row.description or "").strip():
        return age < _HIT
    if ignore_miss:
        return False
    return age < _MISS


def _age(when):
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - when


def _row(series_id):
    from .. import ub
    from .models import SeriesInfo

    if not series_id:
        return None
    try:
        return (ub.session.query(SeriesInfo)
                .filter(SeriesInfo.series_id == int(series_id))
                .one_or_none())
    except Exception:
        ub.session.rollback()
        return None


def _has_text(series_id):
    row = _row(series_id)
    return row is not None and bool((row.description or "").strip())


def _groups(application):
    from .. import db

    worker_db = db.CalibreDB(application)
    books = worker_db.session.query(db.Books).all()
    groups = {}
    for book in books:
        if not book.series:
            continue
        series = book.series[0]
        bucket = groups.setdefault(series.id, {
            "id": series.id, "name": series.name or "", "author": "", "blurb": "", "book_title": "", "index": 999,
        })
        try:
            index = float(book.series_index or 0)
        except (TypeError, ValueError):
            index = 0
        authors = book.authors or []
        author_name = (authors[0].name or "").replace("|", " ") if authors else ""
        blurb = ""
        if book.comments:
            blurb = _clean(book.comments[0].text or "")
        if index and index < bucket["index"]:
            bucket["index"] = index
            bucket["author"] = author_name
            bucket["blurb"] = blurb
            bucket["book_title"] = book.title or ""
        elif not bucket["author"]:
            bucket["author"] = author_name
            if blurb and not bucket["blurb"]:
                bucket["blurb"] = blurb
        if not bucket.get("book_title"):
            bucket["book_title"] = book.title or ""
    return list(groups.values())


def _series_names():
    try:
        from .. import calibre_db, db

        found = {}
        for series in calibre_db.session.query(db.Series).all():
            if series.name:
                found[int(series.id)] = series.name
        return found
    except Exception:
        return {}


def _factual(count, author, minutes, is_complete):
    try:
        count = int(count or 0)
    except (TypeError, ValueError):
        count = 0
    if count == 1:
        books = "1 book"
    else:
        books = "%s books" % count
    if is_complete is True:
        line = "A complete series of %s" % books
    elif is_complete is False:
        line = "An ongoing series of %s" % books
    else:
        line = "A series of %s" % books
    author = (author or "").strip()
    if author:
        line = "%s by %s" % (line, author)
    line = line + "."
    hours = _hours(minutes)
    if hours:
        line = "%s About %s of reading." % (line, hours)
    return line


def _split(text):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chosen = []
    count = 0
    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue
        if chosen and count + len(words) > 60:
            break
        chosen.append(sentence)
        count += len(words)
        if count >= 60:
            break
    excerpt = " ".join(chosen).strip() or text.strip()
    rest = text.strip()[len(excerpt):].strip()
    return excerpt, rest


def _clean(value):
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = text.replace("\u2014", ", ").replace("\u2013", ", ")
    return re.sub(r"\s+", " ", text).strip()


def _name_close(wanted, found):
    if _ratio(wanted, found) >= 85:
        return True
    return _flat(wanted) == _flat(found) and bool(_flat(wanted))


def _ratio(wanted, found):
    from difflib import SequenceMatcher

    left = _flat(wanted)
    right = _flat(found)
    if not left or not right:
        return 0
    if left == right:
        return 100
    return int(round(100 * SequenceMatcher(None, left, right).ratio()))


def _flat(value):
    text = re.sub(r"[^a-z0-9\s]+", " ", (value or "").casefold())
    words = [word for word in text.split() if word not in ("a", "an", "the")]
    return " ".join(words)


def _author_ok(author, text):
    last = _last_name(author)
    if not last:
        return True
    return last in _flat(text).split()


def _last_name(author):
    text = (author or "").replace("|", " ").strip()
    if not text:
        return ""
    if "," in text:
        text = text.split(",", 1)[0]
    parts = _flat(text).split()
    return parts[-1] if parts else ""


def _series_like(text):
    folded = (text or "").casefold()
    return any(word in folded for word in ("series", "trilogy", "saga", "cycle", "chronicle"))


def _bookish(text):
    folded = (text or "").casefold()
    return any(word in folded for word in _BOOKISH)


def _same_book(text, book_blurb):
    if not book_blurb or len(book_blurb) < 40 or not text:
        return False
    return _ratio(text[:500], book_blurb[:500]) >= 72


def _rejected(text):
    folded = " %s " % _flat(text)
    if any(phrase in folded for phrase in ("video game", "television", "tv series", "board game", "role playing", "pen and paper")):
        return True
    return "rpg" in folded.split() or "film" in folded.split() or "movie" in folded.split() or "album" in folded.split()
