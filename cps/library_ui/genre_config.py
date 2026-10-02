# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Editable genre map.

Raw Calibre tags are folded to lowercase and looked up here.
NOISE_TAGS and NATIONALITY_TAGS are ignored.
TAG_BUCKETS sends every other tag into a display bucket.
A book can land in more than one bucket when it has tags from more than one.
Add a line to TAG_BUCKETS to file a new tag. Add a line to NOISE_TAGS to hide one.
"""

# A landing row is dropped when it still has fewer cards than this after top up.
ROW_MIN = 8
# Cards placed on a landing row. Kept at the minimum so more buckets can appear.
ROW_SHOW = 8

# Tags that are too broad, or subject headings that are not a genre.
NOISE_TAGS = {
    "fiction",
    "general",
    "general fiction",
    "novel",
    "novels",
    "books",
    "ebook",
    "ebooks",
    "kindle",
    "adult",
    "juvenile",
    "juvenile fiction",
    "young adult",
    "young adult fiction",
    "ya",
    "kids",
    "children",
    "children's fiction",
    "children's stories",
    "family life",
    "siblings",
    "friendship",
    "domestic fiction",
    "animals",
    "places",
    "social science",
    "small town & rural",
    "small town and rural",
    "contemporary",
    "21st century",
    "20th century",
    "19th century",
    "18th century",
}

# Nationality, ethnicity, and place tags. Same idea as the noise list.
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
    "china",
    "europe",
    "africa",
    "asia",
    "asian american & pacific islander",
    "asian american and pacific islander",
    "african american & black",
    "african american and black",
    "african american",
    "native american",
    "asian american",
}

# Folded raw tag -> bucket id. This is the merge list.
TAG_BUCKETS = {
    "fantasy": "fantasy",
    "epic": "fantasy",
    "epic fantasy": "fantasy",
    "high fantasy": "fantasy",
    "dark fantasy": "fantasy",
    "dragons & mythical creatures": "fantasy",
    "dragons and mythical creatures": "fantasy",
    "myths and legends": "fantasy",
    "mythology": "fantasy",
    "myth": "fantasy",
    "folklore": "fantasy",
    "folklore & mythology": "fantasy",
    "folklore and mythology": "fantasy",
    "fairy tales; folk tales; legends & mythology": "fantasy",
    "fairy tales": "fantasy",
    "folk tales": "fantasy",
    "legends & mythology": "fantasy",
    "gaslamp": "fantasy",
    "steampunk": "fantasy",
    "urban": "fantasy",
    "urban fantasy": "fantasy",
    "vampires": "fantasy",
    "paranormal": "fantasy",
    "magical realism": "fantasy",
    "science fiction": "science_fiction",
    "sci fi": "science_fiction",
    "scifi": "science_fiction",
    "sf": "science_fiction",
    "space opera": "science_fiction",
    "hard science fiction": "science_fiction",
    "alien contact": "science_fiction",
    "technological": "science_fiction",
    "androids and ai": "science_fiction",
    "androids; robots & artificial intelligences": "science_fiction",
    "androids, robots & artificial intelligences": "science_fiction",
    "alternative history": "science_fiction",
    "space exploration": "science_fiction",
    "time travel": "science_fiction",
    "computers & digital media": "science_fiction",
    "computers and digital media": "science_fiction",
    "military": "science_fiction",
    "thrillers": "thrillers",
    "thriller": "thrillers",
    "suspense": "thrillers",
    "horror": "thrillers",
    "crime": "thrillers",
    "crime & mystery": "thrillers",
    "crime and mystery": "thrillers",
    "mystery": "thrillers",
    "espionage": "thrillers",
    "psychological": "thrillers",
    "classics": "classics",
    "classic": "classics",
    "literary": "classics",
    "literary fiction": "classics",
    "historical": "classics",
    "historical fiction": "classics",
    "world literature": "classics",
    "dystopian": "dystopian",
    "dystopia": "dystopian",
    "apocalyptic": "dystopian",
    "apocalyptic & post-apocalyptic": "dystopian",
    "apocalyptic and post apocalyptic": "dystopian",
    "apocalyptic and post-apocalyptic": "dystopian",
    "post apocalyptic": "dystopian",
    "post-apocalyptic": "dystopian",
    "political": "dystopian",
    "action & adventure": "adventure",
    "action and adventure": "adventure",
    "adventure": "adventure",
    "humorous": "adventure",
    "humor": "adventure",
    "humour": "adventure",
    "dark humor": "adventure",
    "satire": "adventure",
    "comedy": "adventure",
    "litrpg": "litrpg",
    "lit rpg": "litrpg",
    "litrpg (literary role-playing game)": "litrpg",
}

# Neighbors used only when a row has fewer than ROW_MIN cards.
BUCKETS = (
    {
        "id": "fantasy",
        "name": "Fantasy",
        "adjacent": ("science_fiction", "adventure", "litrpg"),
        "titles": (
            ("Dragons, quests, and bad decisions", "Swords out, and the plan is already slipping"),
            ("Another world, no return ticket", "One chapter in, and home is a rumor"),
            ("Magic with the safety off", "Stay for the dragon, leave with a quest"),
        ),
    },
    {
        "id": "science_fiction",
        "name": "Science Fiction",
        "adjacent": ("fantasy", "thrillers", "dystopian", "adventure"),
        "titles": (
            ("Lost in space", "The map ends where the story starts"),
            ("The future is weird", "Ships, strangers, and a plan that will not hold"),
            ("Stars and second thoughts", "Far from home, and closer to trouble"),
        ),
    },
    {
        "id": "thrillers",
        "name": "Thrillers and Horror",
        "adjacent": ("dystopian", "science_fiction", "adventure"),
        "titles": (
            ("Can't sleep after this", "One more chapter is a dare"),
            ("Read with the lights on", "Someone in here is not telling the truth"),
            ("Trust no one, turn the page", "The quiet parts are the worst"),
        ),
    },
    {
        "id": "classics",
        "name": "Classics and Literary",
        "adjacent": ("adventure", "dystopian", "fantasy"),
        "titles": (
            ("Timeless and worth the hype", "Old books with sharp teeth"),
            ("Dusty covers, sharp ideas", "They earned the reputation"),
            ("Still talking, still right", "The language holds up"),
        ),
    },
    {
        "id": "dystopian",
        "name": "Dystopian and Apocalyptic",
        "adjacent": ("science_fiction", "thrillers", "classics"),
        "titles": (
            ("The end of the world, but make it interesting", "Society cracked, and the story got better"),
            ("Everything fell apart", "What people do after the rules go quiet"),
            ("After the lights go out", "The world ended and the plot did not"),
        ),
    },
    {
        "id": "adventure",
        "name": "Adventure and Humor",
        "adjacent": ("fantasy", "science_fiction", "classics"),
        "titles": (
            ("Brain candy", "Fun, fast, and a little unwise"),
            ("Escape for an afternoon", "Leave the day behind for a while"),
            ("Trouble, on purpose", "A good time with dirt on its boots"),
        ),
    },
    {
        "id": "litrpg",
        "name": "LitRPG",
        "adjacent": ("fantasy", "science_fiction", "adventure"),
        "titles": (
            ("Dungeons, levels, and dark humor", "The stats are funny until they are not"),
            ("Press start to continue", "One more floor, then bed"),
            ("The dungeon has jokes", "Level up, and try not to die"),
        ),
    },
)

# Cross genre rows. tags are bucket ids. keywords are matched in the description
# and in the raw tag text. rule picks a tighter filter on top of that.
# see is a bucket id, "series", or "genres".
CROSS_ROWS = (
    {
        "id": "rebels",
        "label": "Underdogs",
        "titles": (
            ("Rebels and underdogs", "The ones who were not supposed to win"),
            ("Outcasts with a plan", "Small odds, loud hearts"),
        ),
        "tags": ("dystopian", "adventure", "fantasy"),
        "keywords": ("rebel", "uprising", "underdog", "revolution", "outcast", "overthrow"),
        "rule": "tags_or_keywords",
        "adjacent": ("dystopian", "adventure", "fantasy"),
        "see": "dystopian",
    },
    {
        "id": "family",
        "label": "Found family",
        "titles": (
            ("Found family energy", "The crew you choose when the plot gets mean"),
            ("Stick together", "Friends, strays, and one shared secret"),
        ),
        "tags": ("fantasy", "adventure", "litrpg"),
        "keywords": ("found family", "companion", "crew", "party of", "loyal friend"),
        "rule": "tags_or_keywords",
        "adjacent": ("fantasy", "adventure", "litrpg"),
        "see": "fantasy",
    },
    {
        "id": "villains",
        "label": "Villains",
        "titles": (
            ("Villains with a point", "The bad side brought receipts"),
            ("Charming and terrible", "You may not want them to lose"),
        ),
        "tags": ("thrillers", "dystopian", "fantasy"),
        "keywords": ("villain", "tyrant", "revenge", "antihero", "empire"),
        "rule": "tags_or_keywords",
        "adjacent": ("thrillers", "dystopian"),
        "see": "thrillers",
    },
    {
        "id": "dangerous",
        "label": "Dangerous",
        "titles": (
            ("Smart and a little dangerous", "Clever people, sharp consequences"),
            ("Brains, then trouble", "Someone in here is three steps ahead"),
        ),
        "tags": ("thrillers", "science_fiction", "classics"),
        "keywords": ("assassin", "spy", "genius", "dangerous", "cunning", "heist"),
        "rule": "tags_or_keywords",
        "adjacent": ("thrillers", "science_fiction"),
        "see": "thrillers",
    },
    {
        "id": "heists",
        "label": "Heists",
        "titles": (
            ("Heists and clever plans", "In and out, if the plan survives contact"),
            ("One last job", "The plan is beautiful until it is not"),
        ),
        "tags": ("adventure", "thrillers"),
        "keywords": ("heist", "robbery", "con artist", "scheme", "caper", "thief"),
        "rule": "tags_or_keywords",
        "adjacent": ("adventure", "thrillers"),
        "see": "adventure",
    },
    {
        "id": "short",
        "label": "Short reads",
        "titles": (
            ("Big worlds, short reads", "A whole world, and still home for dinner"),
            ("Epic, but brief", "Large stakes, small time commitment"),
        ),
        "tags": ("fantasy", "science_fiction", "adventure", "litrpg"),
        "keywords": (),
        "rule": "short",
        "adjacent": ("fantasy", "science_fiction", "adventure"),
        "see": "science_fiction",
    },
    {
        "id": "commitment",
        "label": "Series",
        "titles": (
            ("Series worth the commitment", "Four books or more, and the story keeps the promise"),
            ("Settle in", "This one is going to take a while"),
        ),
        "tags": (),
        "keywords": (),
        "rule": "series",
        "adjacent": ("fantasy", "science_fiction", "litrpg", "adventure"),
        "see": "series",
    },
    {
        "id": "standalones",
        "label": "Standalones",
        "titles": (
            ("Standalones, no commitment", "One book, then you are free"),
            ("One and done", "No sequel required"),
        ),
        "tags": (),
        "keywords": (),
        "rule": "standalone",
        "adjacent": ("adventure", "classics", "thrillers"),
        "see": "genres",
    },
    {
        "id": "gems",
        "label": "Hidden",
        "titles": (
            ("Hidden gems", "No rating yet, and easy to scroll past"),
            ("Quiet on the shelf", "The ones almost nobody has scored"),
        ),
        "tags": (),
        "keywords": (),
        "rule": "hidden",
        "adjacent": ("fantasy", "science_fiction", "adventure", "classics", "thrillers", "dystopian", "litrpg"),
        "see": "genres",
    },
    {
        "id": "fresh",
        "label": "New arrivals",
        "titles": (
            ("Fresh on the shelf", "The latest books to land in the library"),
            ("Just arrived", "New covers, still warm from the add"),
        ),
        "tags": (),
        "keywords": (),
        "rule": "fresh",
        "adjacent": (),
        "see": "genres",
        "repeat": True,
    },
)
