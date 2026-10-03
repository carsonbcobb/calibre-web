# -*- coding: utf-8 -*-

"""Row gates. A series cannot sit in a one sitting row, and a funny book cannot sit in a bleak row."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cps.library_ui.evidence import _keyword_hits
from cps.library_ui.gates import evaluate
from cps.library_ui.shelf_config import ROW_GATES


def _profile(**kwargs):
    base = {
        "id": 1,
        "title": "Sample",
        "kind": "book",
        "series_id": None,
        "series_index": 0,
        "count": 1,
        "member_ids": [1],
        "pages": None,
        "minutes": None,
        "minutes_known": False,
        "year": None,
        "rating": None,
        "rating_count": None,
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


class ShelfGateTests(unittest.TestCase):
    def test_series_cannot_pass_done_in_one_sitting(self):
        series = _profile(kind="series", series_id=9, count=4, pages=400, minutes=800, minutes_known=True)
        single = _profile(kind="book", series_id=3, series_index=1, pages=200)
        short = _profile(pages=244, minutes=300)
        self.assertFalse(evaluate({"id": "short"}, series)["ok"])
        self.assertFalse(evaluate({"id": "short"}, single)["ok"])
        self.assertTrue(evaluate({"id": "short"}, short)["ok"])
        self.assertEqual(evaluate({"id": "short"}, short)["failed"], "")

    def test_missing_length_does_not_pass(self):
        result = evaluate({"id": "short"}, _profile())
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed"], "length")

    def test_funny_book_cannot_pass_the_bleak_row(self):
        funny = _profile(
            moods={"funny": "hardcover", "dark": "hardcover"},
            tags={"dark fantasy": "calibre"},
            buckets={"dark_fantasy": "calibre"},
            keywords={"grim": "description", "bleak": "description"},
            warnings={"violence": "hardcover"},
        )
        bleak = _profile(
            moods={"dark": "hardcover", "sad": "hardcover"},
            tags={"dark fantasy": "calibre"},
            buckets={"dark_fantasy": "calibre"},
            keywords={"grim": "description"},
        )
        self.assertFalse(evaluate({"id": "dark"}, funny)["ok"])
        passed = evaluate({"id": "dark"}, bleak)
        self.assertTrue(passed["ok"])
        self.assertGreaterEqual(passed["score"], 2)

    def test_negated_keyword_does_not_fire(self):
        hits = _keyword_hits("This is not a grim book, but it is bleak.", ("grim", "bleak"))
        self.assertNotIn("grim", hits)
        self.assertIn("bleak", hits)

    def test_every_passing_result_cleared_its_gates(self):
        samples = (
            ("short", _profile(pages=120)),
            ("alone", _profile()),
            ("big", _profile(kind="series", series_id=1, count=6)),
            ("swords", _profile(buckets={"epic_fantasy": "calibre"})),
            ("love", _profile(buckets={"romance": "calibre"})),
        )
        for row_id, profile in samples:
            result = evaluate({"id": row_id}, profile, {})
            self.assertIn(row_id, ROW_GATES)
            if result["ok"]:
                self.assertTrue(all(item["ok"] for item in result["gates"]), result["reason"])
            else:
                self.assertTrue(any(not item["ok"] for item in result["gates"]))


if __name__ == "__main__":
    unittest.main()
