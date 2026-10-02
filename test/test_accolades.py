# -*- coding: utf-8 -*-

import unittest

from cps.library_ui.accolade_allowlist import accept, classify
from cps.library_ui.accolades import parse_accolades, parse_quotes, short_label


class AccoladeTests(unittest.TestCase):
    def test_description_phrases_are_kept(self):
        text = "Winner of the Hugo Award in 2010. A New York Times bestseller."
        found = {item["label"]: item["type"] for item in parse_accolades(text)}
        self.assertEqual(found["Hugo Award"], "award_win")
        self.assertEqual(found["New York Times bestseller"], "bestseller")

    def test_short_labels(self):
        self.assertEqual(short_label("award_win", "Hugo Award", 2015), "Hugo Winner 2015")
        self.assertEqual(short_label("award_nominee", "Nebula Award", None), "Nebula Nominee")
        self.assertEqual(short_label("bestseller", "New York Times bestseller", None), "NYT Bestseller")
        self.assertEqual(short_label("award_win", "Pulitzer Prize", 2018), "Pulitzer Prize")
        self.assertEqual(short_label("list", "Booker Longlist", None), "Booker Longlist")
        self.assertEqual(short_label("adaptation", "Netflix series", None), "Netflix Series")

    def test_allowlist_drops_user_shelves_and_keeps_real_awards(self):
        self.assertIsNone(classify("Owned List"))
        self.assertIsNone(classify("Kindle To Read List"))
        self.assertIsNone(classify("Classics List"))
        self.assertEqual(classify("NPR Top 100 Science Fiction Fantasy List")["label"], "NPR Top 100")
        hugo = accept({"label": "Hugo Award", "type": "award_win", "year": 2016, "source": "wikidata"})
        self.assertEqual(hugo["label"], "Hugo")
        self.assertIsNone(accept({"label": "Hugo Award", "type": "award_win", "year": None, "source": "wikidata"}))
        self.assertIsNone(accept({"label": "literary award", "type": "award_win", "year": 2001, "source": "wikidata"}))

    def test_quotes_need_a_publication_and_stay_short(self):
        text = '"A sharp and lovely book." \u2014 The New York Times'
        found = parse_quotes(text)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["publication"], "The New York Times")
        long_quote = '"' + ("word " * 30) + '" \u2014 The Guardian'
        self.assertEqual(parse_quotes(long_quote), [])
        cut = '"' + ("word " * 30) + '..." \u2014 The Guardian'
        shortened = parse_quotes(cut)
        self.assertEqual(len(shortened), 1)
        self.assertLessEqual(len(shortened[0]["quote"].split()), 25)
        self.assertTrue(shortened[0]["quote"].endswith("..."))


if __name__ == "__main__":
    unittest.main()
