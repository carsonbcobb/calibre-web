# -*- coding: utf-8 -*-

import unittest

from cps.library_ui.units import _assemble


def _book(book_id, title, series_id=None, index=0, minutes=60, rating=None, read=0):
    return {
        "id": book_id,
        "title": title,
        "author_name": "Ada",
        "author_key": "ada",
        "author_ids": {1},
        "tags": {"fantasy"},
        "tag_ids": {9},
        "tag_pairs": [(9, "fantasy")],
        "real_tags": True,
        "series_id": series_id,
        "series_name": "Cycle" if series_id else "",
        "series_index": index,
        "series_len": 1,
        "started": False,
        "unread_left": True,
        "is_first": index == 1,
        "stamp": None,
        "read": read,
        "read_at": None,
        "minutes": minutes,
        "blurb": title.lower(),
        "rating": rating,
        "rating_count": 10 if rating else None,
        "fresh_id": book_id,
    }


class UnitTests(unittest.TestCase):
    def test_series_with_two_books_is_one_unit(self):
        units = _assemble([
            _book(1, "One", 4, 1, minutes=100, rating=4),
            _book(2, "Two", 4, 2, minutes=80, rating=5, read=1),
            _book(3, "Solo"),
        ], {}, {4: "Cycle"})
        kinds = sorted(unit["kind"] for unit in units)
        self.assertEqual(kinds, ["book", "series"])
        series = [unit for unit in units if unit["kind"] == "series"][0]
        self.assertEqual(series["title"], "Cycle")
        self.assertEqual(series["count"], 2)
        self.assertEqual(series["member_ids"], [1, 2])
        self.assertEqual(series["cover_ids"], [1, 2])
        self.assertEqual(series["minutes"], 180)
        self.assertEqual(series["rating"], 4.5)
        self.assertEqual(series["tags"], {"fantasy"})
        self.assertEqual(series["next_id"], 1)
        self.assertIn("2 books", series["meta_line"])

    def test_single_book_series_stays_a_book(self):
        units = _assemble([_book(8, "Only", 3, 1)], {}, {3: "Short"})
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["kind"], "book")
        self.assertEqual(units[0]["id"], 8)


if __name__ == "__main__":
    unittest.main()
