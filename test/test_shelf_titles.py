# -*- coding: utf-8 -*-

"""Fail if a retired shelf title is still in the app."""

import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".git", "venv", ".venv", "node_modules", "__pycache__"}
SUFFIXES = (".py", ".html", ".js")
BANNED = (
    "Lost in space",
    "Lose yourself in another world",
    "Worlds with magic in them",
    "Pulled from the stars",
    "Pulled from the stacks",
    "Start something new",
    "Short and sweet",
    "Something big",
    "Never opened",
    "Magic systems you can map",
    "Wizards, vampires, and things that bite",
    "Fantasy for people who hate the usual fantasy",
    "The end of the world, but make it interesting",
    "Whodunit and who did what",
    "Found family energy",
    "Plot twists you will not see coming",
    "Timeless and worth the hype",
    "Start a new series",
    "Series you can binge right now",
    "Big series, big commitment",
    "Standalones, no commitment",
    "Bring snacks, you are not leaving the couch",
    "Award winners and acclaimed reads",
    "Another from",
    "Stories that still feel like the first time",
    "One decade with enough books to fill a row",
    "Adjacent genres you might like",
    "The highest rated books in this genre",
    "Series in this genre you have not started",
    "A series here that you already opened",
    "Nearby shelves, if this one runs out",
    "Books published from 2010 through 2019",
    "Published before 1995",
    "A turn through",
    "is the shelf you have barely touched",
    "Quests, kingdoms, and wars",
    "Grim roads, revenge, and blood",
    "Gods, prophecy, and stories older",
    "Rules, costs, and power you can diagram",
    "Gothic nights and supernatural trouble",
    "Steampunk, magical realism, westerns",
    "Fleets, empires, and the long dark",
    "Hard science, machines, and minds",
    "Aliens, invasions, and greetings",
    "Collapse, survival, and what people do next",
    "Games, systems, and one more floor",
    "Machines that insist they are fine",
    "Horror, dread, and the chapter",
    "Detectives, crimes, and the turn",
    "Funny, snarky, and easy to fall into",
    "Uprisings, outcasts, and people",
    "Crews, companions, and the people who stay",
    "Antiheroes, assassins, and revenge",
    "Secrets, betrayals, and a truth",
    "Romance with a plot that refuses",
    "Soldiers, battles, and the cost",
    "Classics and older books people still pass",
    "Book one, when the series still has room",
    "The next unread book in a series you started",
    "A whole set, two to five books",
    "Five books or more, so clear your calendar",
    "One book, then you are free",
    "Standalones under six hours",
    "Long books, and series that run past",
    "The latest books to land in the library",
    "Four stars or better, without a huge",
    "Books with a real accolade already on file",
    "Close to the last book you finished",
    "In the neighborhood of a favorite",
    "More from an author you already finished",
    "Series and books from one writer",
    "Titles stay hidden until you hover",
    "No agenda, just the next thing",
    "One book, then you are free",
    "Young at heart, mean at times",
    "Teen angst with a body count",
    "Chosen ones with attitude",
)


class ShelfTitleTests(unittest.TestCase):
    def test_old_row_titles_are_gone(self):
        hits = []
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [name for name in dirs if name not in SKIP and not name.startswith(".")]
            for name in files:
                if not name.endswith(SUFFIXES):
                    continue
                path = os.path.join(folder, name)
                if os.path.abspath(path) == os.path.abspath(__file__):
                    continue
                try:
                    with open(path, encoding="utf-8", errors="ignore") as handle:
                        text = handle.read()
                except OSError:
                    continue
                for phrase in BANNED:
                    if phrase in text:
                        hits.append("%s: %s" % (os.path.relpath(path, ROOT), phrase))
        self.assertFalse(hits, "Retired shelf titles are still in the tree:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
