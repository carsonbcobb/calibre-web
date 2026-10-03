# -*- coding: utf-8 -*-

"""Age labels stay in the data and stay off the page."""

import os
import re
import sqlite3
import sys
import time
import unittest
import urllib.request
from hashlib import sha512

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cps.library_ui.gates import evaluate
from cps.library_ui.shelf_config import HIDDEN_TAGS, ROW_GATES, ROWS, tag_hidden

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WORDS = re.compile(r"\b(?:young|ya|teens?|kids|children|juvenile|new adult|coming of age)\b", re.I)
_DROP = (
    "library-card-title",
    "library-card-author",
    "cw-hero-title-link",
    "cw-hero-blurb",
    "cw-hero-blurb-rest",
    "cw-about-body",
    "cw-description",
    "cw-quote",
    "cw-hero-series",
    "cw-reader-reviews",
    "cw-feature-quote",
    "cw-praise",
)


def _profile(**kwargs):
    base = {
        "id": 1,
        "title": "Sample",
        "kind": "book",
        "series_id": None,
        "series_index": 0,
        "count": 1,
        "member_ids": [1],
        "pages": 200,
        "minutes": 300,
        "minutes_known": True,
        "year": 2020,
        "rating": 4.2,
        "rating_count": 10,
        "moods": {},
        "tags": {},
        "buckets": {},
        "warnings": {},
        "keywords": {},
        "started": False,
        "finished_count": 0,
        "unread_left": True,
        "accolade": False,
        "author_key": "",
        "stamp": None,
    }
    base.update(kwargs)
    return base


class AgeSignalTests(unittest.TestCase):
    def test_age_labels_are_hidden_and_the_old_row_is_gone(self):
        self.assertTrue(tag_hidden("Young Adult"))
        self.assertTrue(tag_hidden("young-adult"))
        self.assertTrue(tag_hidden("Coming of Age"))
        self.assertFalse(tag_hidden("Epic Fantasy"))
        ids = [row["id"] for row in ROWS]
        self.assertNotIn("young", ids)
        self.assertIn("rulebreakers", ids)
        self.assertNotIn("young", ROW_GATES)
        titles = " ".join(" ".join(row.get("titles") or ()) + " " + (row.get("subtitle") or "") for row in ROWS)
        self.assertIsNone(_WORDS.search(titles))

    def test_two_signals_qualify_and_the_reason_hides_the_label(self):
        passed = evaluate({"id": "rulebreakers"}, _profile(
            tags={"young adult": "calibre"},
            keywords={"orphan": "description"},
            moods={"adventurous": "hardcover"},
        ))
        self.assertTrue(passed["ok"])
        self.assertGreaterEqual(passed["score"], 2)
        self.assertIsNone(_WORDS.search(passed["reason"]))
        self.assertTrue(all(item["ok"] for item in passed["gates"]))
        lone = evaluate({"id": "rulebreakers"}, _profile(tags={"ya": "calibre"}))
        self.assertFalse(lone["ok"])

    def test_dark_and_sad_together_are_excluded(self):
        result = evaluate({"id": "rulebreakers"}, _profile(
            tags={"new adult": "calibre"},
            keywords={"academy": "description"},
            moods={"dark": "hardcover", "sad": "hardcover"},
        ))
        self.assertFalse(result["ok"])

    def test_age_tag_does_not_block_another_row(self):
        result = evaluate({"id": "swords"}, _profile(
            tags={"young adult": "calibre", "epic fantasy": "calibre"},
            buckets={"epic_fantasy": "calibre"},
        ))
        self.assertTrue(result["ok"])


def _mint(user_agent):
    base = "%s|%s" % (b"::ffff:127.0.0.1", user_agent.encode())
    ident = sha512(base.encode("utf8")).hexdigest()
    token = "age-label-" + sha512(user_agent.encode()).hexdigest()[:16]
    con = sqlite3.connect(os.path.join(_ROOT, "app.db"), timeout=5)
    key = con.execute("select flask_session_key from flask_settings").fetchone()[0]
    expiry = int(time.time()) + 900
    con.execute("delete from user_session where random = ?", (token,))
    con.execute(
        "insert into user_session (user_id, session_key, random, expiry) values (?,?,?,?)",
        (1, ident, token, expiry),
    )
    con.commit()
    con.close()
    from flask import Flask, session
    app = Flask("age-label-check")
    app.secret_key = key
    with app.test_request_context("/"):
        session.permanent = True
        session["_user_id"] = "1"
        session["_fresh"] = True
        session["_id"] = ident
        session["_random"] = token
        response = app.response_class()
        app.session_interface.save_session(app, session, response)
        cookie = response.headers.get("Set-Cookie").split(";", 1)[0].split("=", 1)[1]
    return cookie, token


def _drop(token):
    con = sqlite3.connect(os.path.join(_ROOT, "app.db"), timeout=5)
    con.execute("delete from user_session where random = ?", (token,))
    con.commit()
    con.close()


class AgePageTests(unittest.TestCase):
    def test_pages_do_not_show_age_labels(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            self.skipTest("Playwright is not installed")
        try:
            urllib.request.urlopen("http://127.0.0.1:8084/login", timeout=3)
        except Exception:
            self.skipTest("The library server is not available")
        user_agent = "age-label-check"
        cookie, token = _mint(user_agent)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(user_agent=user_agent)
                context.add_cookies([{
                    "name": "session",
                    "value": cookie,
                    "url": "http://127.0.0.1:8084/",
                }])
                page = context.new_page()
                hits = []
                for path in ("/", "/discover/stored", "/genres"):
                    page.goto("http://127.0.0.1:8084" + path, wait_until="domcontentloaded", timeout=30000)
                    hits.extend(self._hits(page, path))
                genre = page.evaluate("() => { const el = document.querySelector(\"a[href^='/genres/']\"); return el ? el.getAttribute('href') : ''; }")
                if genre:
                    page.goto("http://127.0.0.1:8084" + genre, wait_until="domcontentloaded", timeout=30000)
                    hits.extend(self._hits(page, genre))
                page.goto("http://127.0.0.1:8084/series", wait_until="domcontentloaded", timeout=30000)
                hits.extend(self._hits(page, "/series"))
                series = page.evaluate("() => { const el = document.querySelector(\"a[href*='/series/']\"); return el ? el.getAttribute('href') : ''; }")
                if series:
                    page.goto("http://127.0.0.1:8084" + series, wait_until="domcontentloaded", timeout=30000)
                    hits.extend(self._hits(page, series))
                book = page.evaluate("() => { const el = document.querySelector(\"a[href*='/book/']\"); return el ? el.getAttribute('href') : ''; }")
                if book:
                    page.goto("http://127.0.0.1:8084" + book, wait_until="domcontentloaded", timeout=30000)
                    hits.extend(self._hits(page, book))
                page.goto("http://127.0.0.1:8084/genres/young-adult", wait_until="domcontentloaded", timeout=30000)
                self.assertTrue(page.url.rstrip("/").endswith("/genres"), page.url)
                hits.extend(self._hits(page, "/genres/young-adult"))
                browser.close()
            self.assertFalse(hits, "Age labels are still visible:\n" + "\n".join(hits[:20]))
        finally:
            _drop(token)

    def _hits(self, page, path):
        html = page.evaluate(
            """(classes) => {
              document.querySelectorAll('meta[property="og:description"]').forEach(node => node.remove());
              classes.forEach(name => document.querySelectorAll('.' + name).forEach(node => node.remove()));
              return document.body ? document.body.innerText : '';
            }""",
            list(_DROP),
        )
        found = []
        for match in _WORDS.finditer(html or ""):
            start = max(0, match.start() - 40)
            found.append("%s: %s" % (path, (html[start:match.end() + 40] or "").replace("\n", " ")))
        return found


if __name__ == "__main__":
    unittest.main()
