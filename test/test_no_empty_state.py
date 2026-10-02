# -*- coding: utf-8 -*-

"""The library must not tell a reader that nothing matches."""

import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"libs", "venv", ".git", "__pycache__"}
SUFFIXES = (".py", ".html", ".js")


def _sources():
    found = []
    for name in ("cps", "cps/themes"):
        base = os.path.join(ROOT, name)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [item for item in dirnames if item not in SKIP_DIRS]
            for filename in filenames:
                if filename.endswith(SUFFIXES):
                    found.append(os.path.join(dirpath, filename))
    return found


class EmptyStateTextTest(unittest.TestCase):
    def test_nothing_matches_is_gone(self):
        hits = []
        for path in _sources():
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                for number, line in enumerate(handle, 1):
                    if "Nothing matches" in line:
                        hits.append("%s:%s" % (os.path.relpath(path, ROOT), number))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
