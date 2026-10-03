# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""One shelf list for Home, Discover, and Genres.

Tone: titles are blunt, dark, funny, or a little unhinged. Never corporate.
Never "Discover", "Explore", "Curated", "Top picks", or "You might like".
Titles stay under 7 words. Subtitles are one short deadpan line.
Each row lists two titles. The engine picks one at random per load.
The small uppercase label stays fixed.

How to add a row: append one dict to ROWS and one dict to ROW_GATES.
Give the row an id, a group, titles (two strings), a subtitle, a label, and
where it may show ("home", "discover", "genres"). ROW_GATES holds the gates
and the score signals. Every gate must pass. A short row is dropped. Neighbor
rows cannot relax a gate.

How to remove a row: delete that dict. Do not leave the old title anywhere else.

How to file a tag: add the folded tag to TAG_BUCKETS. Add a tag to NOISE_TAGS
or NATIONALITY_TAGS to ignore it. Generic Fantasy and Science Fiction are not
buckets, because they cover almost the whole library.

Buckets with chip True appear on the genre bar, largest first, after All.
"""

ROW_MIN = 6
ROW_TAKE = 8

NOISE_TAGS = {
    "fiction",
    "general",
    "general fiction",
    "novel",
    "novels",
    "novela",
    "books",
    "ebook",
    "ebooks",
    "kindle",
    "adult",
    "places",
    "family life",
    "siblings",
    "21st century",
    "20th century",
    "19th century",
    "18th century",
    "china",
    "contemporary",
    "social themes",
    "women",
    "politics",
    "fantasy - series",
    "fantasy fiction",
    "fiction - fantasy",
    "no data",
    "read",
    "working",
    "domestic fiction",
    "animals",
    "friendship",
}

# Age labels stay in Calibre. They never render. The rule breaker row may read them.
HIDDEN_TAGS = {
    "young adult",
    "young adult fiction",
    "new adult",
    "juvenile fiction",
    "juvenile",
    "teen",
    "teens",
    "children",
    "kids",
    "ya",
    "coming of age",
}

NOISE_TAGS = NOISE_TAGS | HIDDEN_TAGS

# Description cues for the lead's age. Never shown.
PROTAGONIST_CUES = (
    "teenager",
    "teenage",
    "seventeen",
    "eighteen",
    "nineteen",
    "early twenties",
    "high school",
    "freshman",
)

NATIONALITY_TAGS = {
    "american",
    "british",
    "english",
    "french",
    "german",
    "irish",
    "scottish",
    "welsh",
    "australian",
    "canadian",
    "russian",
    "chinese",
    "japanese",
    "korean",
    "indian",
    "african",
    "european",
    "asian",
    "hispanic",
    "latino",
    "latina",
    "latinx",
    "mexican",
    "italian",
    "spanish",
    "europe",
    "africa",
    "asia",
}

# Folded raw tag -> bucket id. Fantasy and Science Fiction stay unmapped on purpose.
TAG_BUCKETS = {
    "epic": "epic_fantasy",
    "epic fantasy": "epic_fantasy",
    "fantasy - epic": "epic_fantasy",
    "high fantasy": "epic_fantasy",
    "dark fantasy": "dark_fantasy",
    "grimdark": "dark_fantasy",
    "myths and legends": "myths",
    "myths & legends": "myths",
    "mythology": "myths",
    "myth": "myths",
    "folklore": "myths",
    "folklore & mythology": "myths",
    "fairy tales": "myths",
    "fairy tales, folk tales, legends & mythology": "myths",
    "fairy tales; folk tales; legends & mythology": "myths",
    "dragons": "myths",
    "dragons & mythical creatures": "myths",
    "dragons and mythical creatures": "myths",
    "mythical creatures": "myths",
    "paranormal": "paranormal",
    "vampires": "paranormal",
    "vampire": "paranormal",
    "gothic": "paranormal",
    "supernatural": "paranormal",
    "steampunk": "weird",
    "gaslamp": "weird",
    "magical realism": "weird",
    "westerns": "weird",
    "western": "weird",
    "western stories": "weird",
    "alternative history": "weird",
    "alternate history": "weird",
    "space opera": "space_opera",
    "hard science fiction": "hard_sf",
    "technological": "hard_sf",
    "androids and ai": "hard_sf",
    "androids & ai": "hard_sf",
    "androids, robots & artificial intelligences": "hard_sf",
    "androids; robots & artificial intelligences": "hard_sf",
    "artificial intelligence": "hard_sf",
    "alien contact": "aliens",
    "aliens": "aliens",
    "first contact": "aliens",
    "dystopian": "dystopian",
    "dystopia": "dystopian",
    "apocalyptic": "dystopian",
    "apocalyptic & post-apocalyptic": "dystopian",
    "apocalyptic and post-apocalyptic": "dystopian",
    "post-apocalyptic": "dystopian",
    "post apocalyptic": "dystopian",
    "litrpg": "litrpg",
    "litrpg (literary role-playing game)": "litrpg",
    "lit rpg": "litrpg",
    "horror": "horror",
    "psychological": "horror",
    "psychological thriller": "horror",
    "mystery": "mystery",
    "mystery and thriller": "mystery",
    "thriller": "mystery",
    "thrillers": "mystery",
    "suspense": "mystery",
    "crime": "mystery",
    "crime and mystery": "mystery",
    "crime & mystery": "mystery",
    "humour": "humor",
    "humor": "humor",
    "humorous": "humor",
    "comedy": "humor",
    "romance": "romance",
    "romantic comedy": "romance",
    "military": "military",
    "war": "military",
    "war & military": "military",
    "war and military": "military",
    "classics": "classics",
    "classic": "classics",
    "literary": "classics",
    "literary fiction": "classics",
    "historical": "classics",
    "historical fiction": "classics",
    "adventure": "adventure",
    "action & adventure": "adventure",
    "action and adventure": "adventure",
}

BUCKETS = (
    {"id": "epic_fantasy", "name": "Epic Fantasy", "label": "EPIC FANTASY", "row": "swords", "adjacent": ("dark_fantasy", "myths", "adventure"), "chip": True},
    {"id": "dark_fantasy", "name": "Dark Fantasy", "label": "DARK FANTASY", "row": "dark", "adjacent": ("epic_fantasy", "horror", "mystery"), "chip": True},
    {"id": "myths", "name": "Myths and Dragons", "label": "MYTHS AND DRAGONS", "row": "dragons", "adjacent": ("epic_fantasy", "dark_fantasy"), "chip": True},
    {"id": "space_opera", "name": "Space Opera", "label": "SPACE OPERA", "row": "space", "adjacent": ("hard_sf", "aliens"), "chip": True},
    {"id": "hard_sf", "name": "Hard Science Fiction and AI and Robots", "label": "HARD SCIENCE FICTION", "row": "hard", "adjacent": ("space_opera", "aliens", "dystopian"), "chip": True},
    {"id": "aliens", "name": "Alien Contact", "label": "ALIEN CONTACT", "row": "aliens", "adjacent": ("space_opera", "hard_sf"), "chip": True},
    {"id": "dystopian", "name": "Dystopian and Apocalyptic", "label": "DYSTOPIAN AND APOCALYPTIC", "row": "apocalypse", "adjacent": ("hard_sf", "horror", "military"), "chip": True},
    {"id": "litrpg", "name": "LitRPG", "label": "LITRPG", "row": "litrpg", "adjacent": ("humor", "adventure", "epic_fantasy"), "chip": True},
    {"id": "horror", "name": "Horror and Psychological", "label": "HORROR", "row": "sleep", "adjacent": ("mystery", "dark_fantasy"), "chip": True},
    {"id": "mystery", "name": "Mystery and Thriller", "label": "MYSTERY AND THRILLER", "row": "whodunit", "adjacent": ("horror", "dark_fantasy"), "chip": True},
    {"id": "humor", "name": "Humor", "label": "HUMOR", "row": "candy", "adjacent": ("litrpg", "adventure"), "chip": True},
    {"id": "romance", "name": "Romance", "label": "ROMANCE", "row": "love", "adjacent": ("classics",), "chip": True},
    {"id": "military", "name": "Military", "label": "MILITARY", "row": "war", "adjacent": ("epic_fantasy", "space_opera", "dystopian"), "chip": True},
    {"id": "classics", "name": "Classics and Literary and Historical", "label": "CLASSICS", "row": "timeless", "adjacent": ("military", "romance"), "chip": True},
    {"id": "adventure", "name": "Adventure", "label": "ADVENTURE", "row": "candy", "adjacent": ("epic_fantasy", "humor", "litrpg"), "chip": False},
    {"id": "paranormal", "name": "Paranormal", "label": "PARANORMAL", "row": "bite", "adjacent": ("dark_fantasy", "romance"), "chip": False},
    {"id": "weird", "name": "Weird", "label": "WEIRD", "row": "hate", "adjacent": ("classics", "epic_fantasy"), "chip": False},
)

# rule: bucket, keywords, series_new, series_next, binge, big_series,
# standalone, short, snacks, fresh, decade, gems, award, because, favorite,
# author, spotlight, covers, dice, wildcard, ignored, unread, magic, robots
# titles: two options. The first is also stored as title for the admin list.
ROWS = (
    {"id": "swords", "group": "fantasy", "titles": ("Swords, sorcery, and bad decisions", "Everyone here is about to be stabbed"), "title": "Swords, sorcery, and bad decisions", "subtitle": "Kingdoms fall. Nobody learns.", "label": "EPIC FANTASY", "rule": "bucket", "buckets": ("epic_fantasy",), "keywords": ("quest", "kingdom", "sword", "throne", "war"), "adjacent": ("dark", "dragons"), "where": ("home", "discover", "genres")},
    {"id": "dark", "group": "fantasy", "titles": ("Dark, bloody, and worth it", "Nobody gets a happy ending"), "title": "Dark, bloody, and worth it", "subtitle": "Grimdark, but make it a page turner.", "label": "DARK FANTASY", "rule": "bucket", "buckets": ("dark_fantasy",), "keywords": ("grim", "revenge", "blood", "dark"), "adjacent": ("swords", "sleep"), "where": ("home", "discover", "genres")},
    {"id": "dragons", "group": "fantasy", "titles": ("Dragons and old legends", "Gods are petty. So are dragons."), "title": "Dragons and old legends", "subtitle": "Prophecies with terrible fine print.", "label": "MYTHS AND DRAGONS", "rule": "bucket", "buckets": ("myths",), "keywords": ("dragon", "prophecy", "myth", "god", "legend"), "adjacent": ("swords", "dark"), "where": ("home", "discover", "genres")},
    {"id": "magic", "group": "fantasy", "titles": ("Magic with rules, and consequences", "Read the magic system. Cry anyway."), "title": "Magic with rules, and consequences", "subtitle": "Spreadsheet energy, wizard edition.", "label": "EPIC FANTASY", "rule": "magic", "buckets": ("epic_fantasy",), "keywords": ("allomancy", "magic system", "runes", "stormlight", "mistborn", "magic"), "adjacent": ("swords", "litrpg"), "where": ("home", "discover")},
    {"id": "bite", "group": "fantasy", "titles": ("Fangs, curses, and things that bite", "Do not invite them in"), "title": "Fangs, curses, and things that bite", "subtitle": "Vampires with attitude problems.", "label": "PARANORMAL", "rule": "bucket", "buckets": ("paranormal",), "keywords": ("vampire", "wizard", "supernatural", "gothic"), "adjacent": ("dark", "love"), "where": ("home", "discover")},
    {"id": "hate", "group": "fantasy", "titles": ("Fantasy for people who hate fantasy", "Weird, wild, and not elves"), "title": "Fantasy for people who hate fantasy", "subtitle": "Steampunk, western, and magic gone sideways.", "label": "WEIRD", "rule": "bucket", "buckets": ("weird",), "keywords": ("steampunk", "gaslamp", "magical realism", "western", "alternative history"), "adjacent": ("timeless", "swords"), "where": ("home", "discover")},
    {"id": "space", "group": "science", "titles": ("Out there in the stars", "Space is big and trying to kill you"), "title": "Out there in the stars", "subtitle": "Empires, fleets, and long lonely voids.", "label": "SPACE OPERA", "rule": "bucket", "buckets": ("space_opera",), "keywords": ("starship", "fleet", "empire", "galaxy"), "adjacent": ("hard", "aliens"), "where": ("home", "discover", "genres")},
    {"id": "hard", "group": "science", "titles": ("Science you could almost believe", "Math, but make it terrifying"), "title": "Science you could almost believe", "subtitle": "Hard SF that does the homework.", "label": "HARD SCIENCE FICTION", "rule": "bucket", "buckets": ("hard_sf",), "keywords": ("android", "robot", "artificial intelligence", "physics"), "adjacent": ("space", "robots"), "where": ("home", "discover", "genres")},
    {"id": "aliens", "group": "science", "titles": ("First contact, bad manners", "They came. They did not knock."), "title": "First contact, bad manners", "subtitle": "Aliens have notes on humanity.", "label": "ALIEN CONTACT", "rule": "bucket", "buckets": ("aliens",), "keywords": ("alien", "invasion", "first contact"), "adjacent": ("space", "hard"), "where": ("home", "discover", "genres")},
    {"id": "apocalypse", "group": "science", "titles": ("The end of the world, but fun", "Everything burned. Keep reading."), "title": "The end of the world, but fun", "subtitle": "Collapse, survival, and bad governments.", "label": "DYSTOPIAN AND APOCALYPTIC", "rule": "bucket", "buckets": ("dystopian",), "keywords": ("apocalypse", "survival", "wasteland", "collapse"), "adjacent": ("hard", "sleep"), "where": ("home", "discover", "genres")},
    {"id": "litrpg", "group": "science", "titles": ("Dungeons, levels, and dark humor", "Press start. Try not to die."), "title": "Dungeons, levels, and dark humor", "subtitle": "Loot boxes with a body count.", "label": "LITRPG", "rule": "bucket", "buckets": ("litrpg",), "keywords": ("dungeon", "leveling", "system", "stats"), "adjacent": ("candy", "swords"), "where": ("home", "discover", "genres")},
    {"id": "robots", "group": "science", "titles": ("Robots with feelings, allegedly", "Please do not talk to me"), "title": "Robots with feelings, allegedly", "subtitle": "Machines who just want to be left alone.", "label": "AI AND ROBOTS", "rule": "robots", "buckets": ("hard_sf", "humor"), "keywords": ("robot", "android", "murderbot", "artificial"), "adjacent": ("hard", "candy"), "where": ("home", "discover")},
    {"id": "sleep", "group": "mood", "titles": ("Can't sleep after this", "Leave the lights on"), "title": "Can't sleep after this", "subtitle": "You will check the closet. Twice.", "label": "HORROR", "rule": "bucket", "buckets": ("horror",), "keywords": ("horror", "nightmare", "haunted", "psychological"), "adjacent": ("whodunit", "dark"), "where": ("home", "discover", "genres")},
    {"id": "whodunit", "group": "mood", "titles": ("Who did it, and why is it you", "Everyone is lying. Fun."), "title": "Who did it, and why is it you", "subtitle": "Cops, killers, and a twist in chapter nine.", "label": "MYSTERY AND THRILLER", "rule": "bucket", "buckets": ("mystery",), "keywords": ("detective", "crime", "murder", "twist"), "adjacent": ("sleep", "dark"), "where": ("home", "discover", "genres")},
    {"id": "candy", "group": "mood", "titles": ("Brain candy", "Turn your brain off. It is fine."), "title": "Brain candy", "subtitle": "Funny, fast, and slightly irresponsible.", "label": "HUMOR", "rule": "bucket", "buckets": ("humor", "adventure"), "keywords": ("funny", "snark", "comedy", "humor"), "adjacent": ("litrpg", "space"), "where": ("home", "discover", "genres")},
    {"id": "rebels", "group": "mood", "titles": ("Rebels and underdogs", "Burn it down, politely"), "title": "Rebels and underdogs", "subtitle": "Small people. Huge empires. Bad odds.", "label": "REBELS", "rule": "keywords", "buckets": (), "keywords": ("rebellion", "rebel", "uprising", "slave", "orphan", "caste", "empire"), "adjacent": ("war", "apocalypse", "swords"), "where": ("home", "discover")},
    {"id": "family", "group": "mood", "titles": ("Found family, found trauma", "A crew of idiots you will love"), "title": "Found family, found trauma", "subtitle": "Nobody planned to be friends.", "label": "FOUND FAMILY", "rule": "keywords", "buckets": (), "keywords": ("found family", "crew", "companion", "companions", "band of", "friends"), "adjacent": ("swords", "space", "litrpg"), "where": ("home", "discover")},
    {"id": "villains", "group": "mood", "titles": ("Villains with a point", "They are not wrong, exactly"), "title": "Villains with a point", "subtitle": "Root for the wrong side.", "label": "VILLAINS", "rule": "keywords", "buckets": (), "keywords": ("villain", "antihero", "revenge", "assassin"), "adjacent": ("dark", "whodunit"), "where": ("home", "discover")},
    {"id": "twists", "group": "mood", "titles": ("Plot twists that ruin your week", "You will not see this coming"), "title": "Plot twists that ruin your week", "subtitle": "Put the book down. You cannot.", "label": "TWISTS", "rule": "keywords", "buckets": (), "keywords": ("twist", "secret", "betrayal", "truth", "memory"), "adjacent": ("whodunit", "sleep"), "where": ("home", "discover")},
    {"id": "love", "group": "mood", "titles": ("Love, but make it complicated", "Nobody communicates. Delightful."), "title": "Love, but make it complicated", "subtitle": "Slow burns and bad timing.", "label": "ROMANCE", "rule": "bucket", "buckets": ("romance",), "keywords": ("romance", "love"), "adjacent": ("timeless",), "where": ("home", "discover", "genres")},
    {"id": "war", "group": "mood", "titles": ("War stories", "Boots, blood, and bad orders"), "title": "War stories", "subtitle": "Soldiers who did not sign up for this.", "label": "MILITARY", "rule": "bucket", "buckets": ("military",), "keywords": ("soldier", "battle", "war", "military"), "adjacent": ("swords", "space"), "where": ("home", "discover", "genres")},
    {"id": "rulebreakers", "group": "mood", "titles": ("Chosen ones and rule breakers", "Out on their own, minus the training wheels"), "title": "Chosen ones and rule breakers", "subtitle": "Big destinies. Bad judgment.", "subtitles": ("Big destinies. Bad judgment.", "They were not ready. They went anyway."), "label": "RULE BREAKERS", "rule": "rulebreakers", "buckets": (), "keywords": (), "adjacent": (), "where": ("home", "discover", "genres")},
    {"id": "timeless", "group": "mood", "titles": ("Old books that still hit", "Dead authors, living burns"), "title": "Old books that still hit", "subtitle": "Classics that earned the hype.", "label": "CLASSICS", "rule": "timeless", "buckets": ("classics",), "keywords": (), "adjacent": ("war", "love"), "where": ("home", "discover", "genres")},
    {"id": "start", "group": "format", "titles": ("Start a series you will regret", "One more chapter. Sure."), "title": "Start a series you will regret", "subtitle": "Book one. Your weekend is gone.", "label": "SERIES", "rule": "series_new", "buckets": (), "keywords": (), "adjacent": ("binge", "big"), "where": ("home", "discover")},
    {"id": "next", "group": "format", "titles": ("Keep the story going", "You left them hanging. Rude."), "title": "Keep the story going", "subtitle": "Next book in the series you started.", "label": "SERIES", "rule": "series_next", "buckets": (), "keywords": (), "adjacent": ("start", "binge"), "where": ("home", "discover")},
    {"id": "binge", "group": "format", "titles": ("Binge it and disappear", "Cancel your plans"), "title": "Binge it and disappear", "subtitle": "Complete series, no waiting.", "label": "SERIES", "rule": "binge", "buckets": (), "keywords": (), "adjacent": ("start", "alone"), "where": ("home", "discover")},
    {"id": "big", "group": "format", "titles": ("Big series, big problem", "A long, beautiful mistake"), "title": "Big series, big problem", "subtitle": "Five or more books. Pack snacks.", "label": "SERIES", "rule": "big_series", "buckets": (), "keywords": (), "adjacent": ("snacks", "start"), "where": ("home", "discover")},
    {"id": "alone", "group": "format", "titles": ("Standalones, no strings", "One book. No sequel. No drama."), "title": "Standalones, no strings", "subtitle": "Finish it and walk away.", "label": "STANDALONES", "rule": "standalone", "buckets": (), "keywords": (), "adjacent": ("short", "timeless"), "where": ("home", "discover")},
    {"id": "short", "group": "format", "titles": ("Done in one sitting", "Short, sharp, and over by midnight"), "title": "Done in one sitting", "subtitle": "Quick reads that still hurt.", "label": "SHORT READS", "rule": "short", "buckets": (), "keywords": (), "adjacent": ("alone",), "where": ("home", "discover")},
    {"id": "snacks", "group": "format", "titles": ("Do not plan to leave the couch", "Hours vanish. You will not notice."), "title": "Do not plan to leave the couch", "subtitle": "Giant books and bigger series.", "label": "LONG READS", "rule": "snacks", "buckets": (), "keywords": (), "adjacent": ("big", "timeless"), "where": ("home", "discover")},
    {"id": "fresh", "group": "format", "titles": ("Fresh on the shelf", "New arrivals. Still warm."), "title": "Fresh on the shelf", "subtitle": "Just added to the library.", "label": "NEW", "rule": "fresh", "buckets": (), "keywords": (), "adjacent": (), "where": ("home", "discover"), "repeat": True},
    {"id": "decade", "group": "format", "titles": ("From the 2010s, with feeling", "The 2000s, unfiltered"), "title": "From the 2010s, with feeling", "subtitle": "One decade. Enough books.", "label": "DECADE", "rule": "decade", "buckets": (), "keywords": (), "adjacent": ("fresh", "timeless"), "where": ("home", "discover")},
    {"id": "gems", "group": "format", "titles": ("Hidden gems", "Nobody talks about these"), "title": "Hidden gems", "subtitle": "Underrated and slightly dangerous.", "label": "HIDDEN GEMS", "rule": "gems", "buckets": (), "keywords": (), "adjacent": ("award", "alone"), "where": ("home", "discover")},
    {"id": "award", "group": "format", "titles": ("Award winners, allegedly deserved", "The trophy shelf"), "title": "Award winners, allegedly deserved", "subtitle": "Prizes, bestsellers, and receipts.", "label": "AWARDS", "rule": "award", "buckets": (), "keywords": (), "adjacent": ("gems", "timeless"), "where": ("home", "discover")},
    {"id": "because", "group": "personal", "titles": ("Because you finished {book}", "You liked that. Now suffer more."), "title": "Because you finished {book}", "subtitle": "Same itch, new book.", "label": "FOR YOU", "rule": "because", "buckets": (), "keywords": (), "adjacent": ("favorite", "author"), "where": ("home", "discover")},
    {"id": "favorite", "group": "personal", "titles": ("More like {favorite}", "More like {favorite}"), "title": "More like {favorite}", "subtitle": "Same itch, new book.", "label": "FOR YOU", "rule": "favorite", "buckets": (), "keywords": (), "adjacent": ("because", "author"), "where": ("home", "discover")},
    {"id": "author", "group": "personal", "titles": ("More of {author}, obviously", "More of {author}, obviously"), "title": "More of {author}, obviously", "subtitle": "Same itch, new book.", "label": "FOR YOU", "rule": "author", "buckets": (), "keywords": (), "adjacent": ("spotlight", "because"), "where": ("home", "discover")},
    {"id": "spotlight", "group": "format", "titles": ("Author spotlight: {author}", "Meet your new obsession"), "title": "Author spotlight: {author}", "subtitle": "Everything they wrote, in one place.", "label": "AUTHOR", "rule": "spotlight", "buckets": (), "keywords": (), "adjacent": (), "where": ("home", "discover"), "author_cap": 99, "minimum": 3},
    {"id": "covers", "group": "format", "titles": ("Judge a book by its cover", "Pretty covers, questionable choices"), "title": "Judge a book by its cover", "subtitle": "Titles hidden. Trust your gut.", "label": "COVERS", "rule": "covers", "buckets": (), "keywords": (), "adjacent": ("dice",), "where": ("home", "discover"), "cover_only": True},
    {"id": "dice", "group": "format", "titles": ("Roll the dice", "Pure chaos. No refunds."), "title": "Roll the dice", "subtitle": "Random picks. Zero logic.", "label": "RANDOM", "rule": "dice", "buckets": (), "keywords": (), "adjacent": ("covers",), "where": ("home", "discover")},
    {"id": "wildcard", "group": "discover", "titles": ("Wildcard: {bucket}", "Today we gamble on {bucket}"), "title": "Wildcard: {bucket}", "subtitle": "You did not ask. You will thank us.", "label": "WILDCARD", "rule": "wildcard", "buckets": (), "keywords": (), "adjacent": (), "where": ("discover",)},
    {"id": "ignored", "group": "discover", "titles": ("Your most ignored genre", "You have been avoiding this"), "title": "Your most ignored genre", "subtitle": "Time to face it.", "label": "IGNORED", "rule": "ignored", "buckets": (), "keywords": (), "adjacent": (), "where": ("discover",)},
    {"id": "untouched", "group": "discover", "titles": ("Never touched", "These are judging you from the shelf"), "title": "Never touched", "subtitle": "Unread, unloved, unopened.", "label": "UNREAD", "rule": "unread", "buckets": (), "keywords": (), "adjacent": (), "where": ("discover",)},
)

# Single genre page shelves. Same tone. One title each, edited here.
GENRE_SLICES = (
    {"id": "start_here", "title": "Start here. Regret later.", "subtitle": "Book one. Your weekend is gone.", "rule": "series_new"},
    {"id": "keep_going", "title": "Keep going. You are in too deep.", "subtitle": "You already opened this.", "rule": "series_next"},
    {"id": "standalones", "title": "No sequel, no stress.", "subtitle": "One book. Then you leave.", "rule": "standalone"},
    {"id": "quick", "title": "Short, sharp, done.", "subtitle": "Over before midnight.", "rule": "short"},
    {"id": "big_commitment", "title": "Big series, big problem.", "subtitle": "Five books or more.", "rule": "big_series"},
    {"id": "top_rated", "title": "The ones people will not shut up about.", "subtitle": "Highest rated in this pile.", "rule": "rated"},
    {"id": "adjacent", "title": "If you like this, you are doomed to like these.", "subtitle": "Neighboring shelves. Sorry.", "rule": "adjacent"},
)

# One decade shelf per load. Only decades with ROW_MIN units are eligible.
DECADES = (
    {"title": "From the 2010s, with feeling", "subtitle": "That decade, still loud.", "start": 2010, "end": 2019},
    {"title": "The 2000s, unfiltered", "subtitle": "Unfiltered, and it shows.", "start": 2000, "end": 2009},
    {"title": "Before the internet ruined everything", "subtitle": "Older than your browser.", "start": None, "end": 1994},
)

# Shared vocabulary. Hardcover "dark" and a Calibre "Dark Fantasy" tag are one signal.
# Synonyms are folded. Missing data never creates a signal.
VOCAB = {
    "dark": {"moods": ("dark",), "tags": ("dark fantasy", "grimdark", "dark")},
    "sad": {"moods": ("sad",), "tags": ("tragedy",)},
    "tense": {"moods": ("tense",), "tags": ()},
    "emotional": {"moods": ("emotional",), "tags": ()},
    "funny": {"moods": ("funny", "humorous"), "tags": ("humor", "humour", "comedy", "romantic comedy", "cozy")},
    "lighthearted": {"moods": ("lighthearted", "light hearted"), "tags": ("cozy", "romantic comedy")},
    "hopeful": {"moods": ("hopeful",), "tags": ()},
    "adventurous": {"moods": ("adventurous",), "tags": ("adventure",)},
    "mysterious": {"moods": ("mysterious",), "tags": ("mystery",)},
    "challenging": {"moods": ("challenging",), "tags": ()},
    "reflective": {"moods": ("reflective",), "tags": ()},
    "fast": {"moods": ("fast paced", "fast"), "tags": ()},
    "epic": {"moods": ("epic",), "tags": ("epic fantasy", "epic")},
    "inspiring": {"moods": ("inspiring",), "tags": ()},
}

FANTASY_BUCKETS = ("epic_fantasy", "dark_fantasy", "myths", "paranormal", "weird")
SCIENCE_BUCKETS = ("space_opera", "hard_sf", "aliens", "dystopian", "litrpg")

# Gates are mandatory. score_groups add points and never replace a failed gate.
# accept: standalone, series, or both. strict breaks score ties toward the stricter row.
ROW_GATES = {
    "short": {"accept": "standalone", "clauses": [{"length": "short"}], "score_groups": ({"mood": "fast paced"}, {"rating_min": 4}), "min_score": 0, "topup_score": 0, "strict": 5, "sort": "shortest"},
    "snacks": {"accept": "both", "clauses": [{"length": "long"}], "score_groups": ({"mood": "epic"}, {"keyword_any": ("sprawling", "immersive", "epic")}), "min_score": 0, "topup_score": 0, "strict": 5, "sort": "score"},
    "alone": {"accept": "standalone", "clauses": [], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "big": {"accept": "series", "clauses": [{"series_min": 5}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "binge": {"accept": "series", "clauses": [{"series_between": (2, 5)}, {"not_ongoing": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "start": {"accept": "series", "clauses": [{"series_min": 3}, {"not_started": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "next": {"accept": "series", "clauses": [{"finished_one": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "dark": {
        "accept": "both",
        "exclude_moods": ("lighthearted", "funny", "hopeful"),
        "exclude_tags": ("humor", "humour", "comedy", "romantic comedy", "cozy"),
        "clauses": [
            {"at_least": 2, "groups": (
                {"mood": "dark"}, {"mood": "sad"}, {"mood": "tense"}, {"mood": "emotional"},
                {"tag_any": ("dark fantasy", "grimdark", "tragedy", "dystopian"), "bucket_any": ("dark_fantasy", "dystopian")},
                {"keyword_any": ("tragedy", "betrayal", "doomed", "massacre", "grim", "brutal", "loss", "bleak", "war")},
                {"warning_any": ("death", "violence", "grief")},
            )},
            {"any": (
                {"bucket_any": ("dark_fantasy",), "tag_any": ("dark fantasy", "grimdark")},
                {"all": ({"fantasy": True}, {"mood": "dark"}, {"warning_any": ("death", "violence", "grief"), "keyword_any": ("blood", "brutal", "massacre", "violent")})},
            )},
        ],
        "score_groups": (), "min_score": 2, "topup_score": 2, "strict": 6, "sort": "score",
    },
    "swords": {"accept": "both", "exclude_moods": ("lighthearted",), "clauses": [{"bucket_any": ("epic_fantasy",), "tag_any": ("epic fantasy", "high fantasy", "epic")}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 3, "sort": "score"},
    "dragons": {"accept": "both", "clauses": [{"any": ({"bucket_any": ("myths",)}, {"all": ({"fantasy": True}, {"keyword_any": ("dragon", "dragons", "gods", "prophecy", "prophecies")})})}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 3, "sort": "score"},
    "magic": {"accept": "both", "clauses": [{"fantasy": True}, {"keyword_any": ("magic system", "allomancy", "runes", "spells", "binding", "cost")}, {"any": ({"mood": "epic"}, {"bucket_any": ("epic_fantasy",)})}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 5, "sort": "score"},
    "bite": {"accept": "both", "clauses": [{"any": ({"bucket_any": ("paranormal",), "tag_any": ("paranormal", "vampires", "vampire")}, {"all": ({"keyword_any": ("vampire", "vampires", "curse", "werewolf")}, {"any": ({"fantasy": True}, {"bucket_any": ("horror",)}, {"mood": "dark"}, {"mood": "tense"})})})}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 3, "sort": "score"},
    "hate": {"accept": "both", "clauses": [{"fantasy": True}, {"tag_any": ("steampunk", "gaslamp", "western", "westerns", "magical realism", "alternative history", "alternate history"), "bucket_any": ("weird",)}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "space": {"accept": "both", "clauses": [{"any": ({"bucket_any": ("space_opera",), "tag_any": ("space opera",)}, {"all": ({"science": True}, {"keyword_any": ("fleet", "empire", "starship", "galaxy")})})}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 3, "sort": "score"},
    "hard": {"accept": "both", "clauses": [{"tag_any": ("hard science fiction", "technological", "artificial intelligence", "androids and ai"), "bucket_any": ("hard_sf",)}, {"any": ({"mood": "challenging"}, {"mood": "reflective"}, {"keyword_any": ("physics", "quantum", "orbital", "equation", "scientist")})}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "aliens": {"accept": "both", "clauses": [{"any": ({"bucket_any": ("aliens",), "tag_any": ("alien contact", "aliens", "first contact")}, {"all": ({"keyword_any": ("alien", "aliens", "invasion", "contact")}, {"any": ({"science": True}, {"mood": "mysterious"})})})}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 3, "sort": "score"},
    "apocalypse": {"accept": "both", "clauses": [{"any": ({"bucket_any": ("dystopian",), "tag_any": ("dystopian", "apocalyptic", "post apocalyptic")}, {"keyword_any": ("apocalypse", "collapse", "survival", "wasteland")})}], "score_groups": ({"mood": "funny"}, {"mood": "adventurous"}), "min_score": 0, "topup_score": 0, "strict": 3, "sort": "score"},
    "litrpg": {"accept": "both", "clauses": [{"any": ({"bucket_any": ("litrpg",), "tag_any": ("litrpg", "lit rpg")}, {"all": ({"keyword_any": ("dungeon", "leveling", "loot", "system")}, {"keyword_any": ("game", "rpg", "stats", "litrpg", "player")})})}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "robots": {"accept": "both", "clauses": [{"bucket_any": ("hard_sf",), "tag_any": ("artificial intelligence", "androids and ai", "robot", "robots")}, {"any": ({"mood": "funny"}, {"mood": "reflective"}, {"keyword_any": ("construct", "android", "secunit", "murderbot")})}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "sleep": {"accept": "standalone", "exclude_moods": ("lighthearted", "funny"), "exclude_tags": ("humor", "comedy", "cozy"), "clauses": [{"any": ({"bucket_any": ("horror",), "tag_any": ("horror",)}, {"all": ({"tag_any": ("psychological",)}, {"mood": "tense"})}, {"all": ({"bucket_any": ("mystery",)}, {"mood": "dark"})})}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "whodunit": {"accept": "both", "clauses": [{"tag_any": ("mystery", "crime", "thriller", "suspense"), "bucket_any": ("mystery",)}, {"keyword_any": ("detective", "murder", "investigation", "twist")}, {"not_pure_epic": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "candy": {"accept": "both", "exclude_moods": ("dark", "sad"), "clauses": [{"any": ({"mood": "funny"}, {"mood": "lighthearted"}, {"bucket_any": ("humor",), "tag_any": ("humor", "humour", "comedy")})}], "score_groups": ({"mood": "fast paced"},), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "rebels": {"accept": "both", "clauses": [{"keyword_any": ("rebellion", "uprising", "slave", "orphan", "caste", "empire", "resistance")}, {"mood_any": ("tense", "adventurous", "hopeful")}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "family": {"accept": "both", "clauses": [{"keyword_any": ("crew", "companions", "companion", "band", "friends", "found family", "squad")}, {"mood_any": ("emotional", "adventurous")}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "villains": {"accept": "both", "clauses": [{"keyword_any": ("villain", "antihero", "assassin", "revenge", "tyrant")}, {"mood_any": ("dark", "challenging")}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "twists": {"accept": "standalone", "clauses": [{"keyword_any": ("twist", "secret", "truth", "betrayal", "memory", "identity", "reveal")}, {"mood_any": ("mysterious", "tense")}, {"genre_signal": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 5, "sort": "score"},
    "love": {"accept": "both", "clauses": [{"bucket_any": ("romance",), "tag_any": ("romance", "romantic comedy")}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 3, "sort": "score"},
    "war": {"accept": "both", "clauses": [{"bucket_any": ("military",), "tag_any": ("military", "war")}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 3, "sort": "score"},
    "rulebreakers": {
        "accept": "both",
        "exclude_mood_pair": ("dark", "sad"),
        "exclude_warnings": ("graphic violence", "abuse"),
        "clauses": [{"at_least": 2, "groups": (
            {"hidden_tag": True},
            {"keyword_any": ("chosen one", "apprentice", "academy", "school", "orphan", "prophecy", "first time", "trial", "initiation", "secret heritage", "rebellion")},
            {"mood_any": ("adventurous", "hopeful", "emotional")},
            {"protagonist_age": True},
        )}],
        "score_groups": (), "min_score": 2, "topup_score": 2, "strict": 4, "sort": "score",
    },
    "timeless": {"accept": "both", "clauses": [{"classics_or_old": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 3, "sort": "score"},
    "gems": {"accept": "both", "clauses": [{"rating_min": 4}, {"rating_count": "bottom_third"}, {"positive": 2}], "score_groups": (), "min_score": 2, "topup_score": 2, "strict": 5, "sort": "score"},
    "award": {"accept": "both", "clauses": [{"accolade": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 4, "sort": "score"},
    "because": {"accept": "both", "clauses": [{"share": 2, "source": "last_finished"}], "score_groups": (), "min_score": 2, "topup_score": 2, "strict": 5, "sort": "score"},
    "favorite": {"accept": "both", "clauses": [{"share": 2, "source": "favorite"}], "score_groups": (), "min_score": 2, "topup_score": 2, "strict": 5, "sort": "score"},
    "author": {"accept": "both", "clauses": [{"same_author": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 3, "sort": "score"},
    "spotlight": {"accept": "both", "clauses": [{"spotlight": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 2, "sort": "score"},
    "covers": {"accept": "both", "clauses": [{"random": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 0, "sort": "score"},
    "dice": {"accept": "both", "clauses": [{"random": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 0, "sort": "score"},
    "fresh": {"accept": "both", "clauses": [{"fresh": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 0, "sort": "newest"},
    "decade": {"accept": "both", "clauses": [{"decade": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 2, "sort": "score"},
    "wildcard": {"accept": "both", "clauses": [{"context_bucket": "wildcard"}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 2, "sort": "score"},
    "ignored": {"accept": "both", "clauses": [{"context_bucket": "ignored"}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 2, "sort": "score"},
    "untouched": {"accept": "both", "clauses": [{"unread": True}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 1, "sort": "score"},
}

BY_ID = {row["id"]: row for row in ROWS}
BUCKET_BY_ID = {bucket["id"]: bucket for bucket in BUCKETS}
SPOTLIGHT_NAMES = ("sanderson", "dinniman", "wells", "ruocchio", "gwynne", "brown", "crouch", "brett", "kuang", "taylor")


def tag_hidden(name):
    """True when a tag is an age label that must not be shown."""
    folded = " ".join((name or "").replace("-", " ").replace("'", "").replace("’", "").split()).casefold()
    if not folded:
        return False
    if folded in HIDDEN_TAGS:
        return True
    return "coming of age" in folded


def bucket_for_tag(name):
    folded = (name or "").strip().casefold()
    if not folded or folded in NOISE_TAGS or folded in NATIONALITY_TAGS:
        return ""
    if folded.endswith(" century"):
        return ""
    return TAG_BUCKETS.get(folded, "")


def bucket_name_for_tag(name):
    bucket_id = bucket_for_tag(name)
    bucket = BUCKET_BY_ID.get(bucket_id)
    return bucket["name"] if bucket else ""
