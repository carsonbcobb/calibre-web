# -*- coding: utf-8 -*-

"""Row gates. Every gate must pass. A failed gate is never waived."""

from .shelf_config import FANTASY_BUCKETS, ROW_GATES, SCIENCE_BUCKETS

_RULE_ROW = {
    "series_new": "start",
    "series_next": "next",
    "standalone": "alone",
    "short": "short",
    "big_series": "big",
    "binge": "binge",
    "snacks": "snacks",
}


def evaluate(spec, profile, ctx=None):
    """Return ok, score, the gates checked, and the signals that fired."""
    ctx = ctx or {}
    gate = _gate_for(spec)
    checked = []
    signals = []
    failed = ""

    def mark(name, ok, detail):
        nonlocal failed
        checked.append({"name": name, "ok": bool(ok), "detail": detail or ""})
        if not ok and not failed:
            failed = name

    accept = gate.get("accept") or "both"
    mark("accept", _accept(accept, profile), _accept_detail(accept, profile))
    for mood in gate.get("exclude_moods") or ():
        if _has_mood(profile, mood):
            mark("exclude", False, "excluded %s" % mood)
            break
    else:
        if gate.get("exclude_moods"):
            mark("exclude", True, "not excluded by mood")
    for tag in gate.get("exclude_tags") or ():
        if tag in (profile.get("tags") or {}):
            mark("exclude tag", False, "excluded %s" % tag)
            break
    pair = tuple(gate.get("exclude_mood_pair") or ())
    if pair and all(_has_mood(profile, mood) for mood in pair):
        mark("exclude", False, "excluded paired mood")
    for phrase in gate.get("exclude_warnings") or ():
        if _warning_phrase(profile, phrase):
            mark("exclude warning", False, "excluded warning")
            break
    for clause in gate.get("clauses") or ():
        ok, detail, fired = _clause(clause, profile, ctx)
        mark(detail or "gate", ok, detail if ok else "")
        if ok:
            for item in fired:
                if item and item not in signals:
                    signals.append(item)
    for group in gate.get("score_groups") or ():
        ok, detail = _group(group, profile, ctx)
        if ok and detail and detail not in signals:
            signals.append(detail)
    score = len(signals)
    minimum = int(gate.get("min_score") or 0)
    if not failed and score < minimum:
        mark("score", False, "")
    score_only = failed == "score"
    return {
        "ok": not failed and score >= minimum,
        "gates_ok": (not failed) or score_only,
        "score": score,
        "min_score": minimum,
        "topup_score": int(gate.get("topup_score") if gate.get("topup_score") is not None else minimum),
        "strict": int(gate.get("strict") or 0),
        "sort": gate.get("sort") or "score",
        "gates": checked,
        "signals": signals,
        "failed": failed,
        "reason": _reason(checked, signals, score),
    }


def _gate_for(spec):
    row_id = (spec or {}).get("id")
    if row_id in ROW_GATES:
        return ROW_GATES[row_id]
    rule = (spec or {}).get("rule") or ""
    mapped = _RULE_ROW.get(rule)
    if mapped in ROW_GATES:
        return ROW_GATES[mapped]
    if rule == "bucket":
        return {
            "accept": "both",
            "clauses": [{"bucket_any": tuple((spec or {}).get("buckets") or ())}],
            "score_groups": (),
            "min_score": 0,
            "topup_score": 0,
            "strict": 2,
            "sort": "score",
        }
    if rule == "rated":
        return {
            "accept": "both",
            "clauses": [{"rating_min": 0.01}],
            "score_groups": (),
            "min_score": 0,
            "topup_score": 0,
            "strict": 2,
            "sort": "rating",
        }
    return {"accept": "both", "clauses": [{"random": False}], "score_groups": (), "min_score": 0, "topup_score": 0, "strict": 1, "sort": "score"}


def _accept(kind, profile):
    series = profile.get("kind") == "series" or profile.get("series_id") or profile.get("series_index")
    if kind == "standalone":
        return not series
    if kind == "series":
        return profile.get("kind") == "series"
    return True


def _accept_detail(kind, profile):
    if kind == "standalone":
        return "standalone"
    if kind == "series":
        return "series of %s" % (profile.get("count") or 0)
    return "book or series"


def _clause(clause, profile, ctx):
    if "at_least" in clause:
        fired = []
        for group in clause.get("groups") or ():
            ok, detail = _group(group, profile, ctx)
            if ok and detail:
                fired.append(detail)
        need = int(clause["at_least"])
        return len(fired) >= need, "%s supporting signals" % len(fired), fired
    if "length" in clause:
        return _length(clause["length"], profile)
    if "series_min" in clause:
        ok = profile.get("kind") == "series" and int(profile.get("count") or 0) >= int(clause["series_min"])
        return ok, "%s books in the series" % (profile.get("count") or 0), []
    if "series_between" in clause:
        low, high = clause["series_between"]
        count = int(profile.get("count") or 0)
        ok = profile.get("kind") == "series" and low <= count <= high
        return ok, "%s books in the series" % count, []
    if clause.get("not_started"):
        ok = not profile.get("started")
        return ok, "not started", []
    if clause.get("finished_one"):
        ok = int(profile.get("finished_count") or 0) >= 1 and profile.get("unread_left")
        return ok, "one book finished, more left", []
    if clause.get("not_ongoing"):
        series_id = profile.get("series_id")
        ongoing = series_id in (ctx.get("incomplete") or ())
        return not ongoing, "not marked ongoing", []
    if clause.get("unread"):
        ok = not profile.get("started") and int(profile.get("finished_count") or 0) == 0
        return ok, "unread", []
    if clause.get("fresh"):
        return profile.get("stamp") is not None, "on the shelf", []
    if clause.get("decade"):
        test = ctx.get("decade_test")
        year = profile.get("year")
        ok = bool(test and year and test(int(year)))
        return ok, "published %s" % year if ok else "year", []
    if "rating_min" in clause:
        rating = profile.get("rating")
        ok = rating is not None and float(rating) >= float(clause["rating_min"])
        return ok, "rating %s" % rating if ok else "rating", []
    if clause.get("rating_count") == "bottom_third":
        count = profile.get("rating_count")
        cutoff = ctx.get("rating_cutoff")
        ok = count is not None and cutoff is not None and int(count) <= int(cutoff)
        return ok, "ratings count in the bottom third" if ok else "ratings count", []
    if "positive" in clause:
        fired = _positive(profile)
        need = int(clause["positive"])
        ok = len(fired) >= need
        return ok, "%s positive signals" % len(fired), (fired[:need] if ok else [])
    if clause.get("accolade"):
        return bool(profile.get("accolade")), "recorded accolade", []
    if clause.get("classics_or_old"):
        return _classics(profile)
    if "share" in clause:
        return _share(clause, profile, ctx)
    if clause.get("same_author"):
        author = ctx.get("finished_author") or ""
        ok = bool(author) and author == (profile.get("author_key") or "") and profile.get("id") not in (ctx.get("finished_ids") or ())
        return ok, "same author", []
    if clause.get("spotlight"):
        key = ((ctx.get("spotlight") or {}).get("key") or "")
        ok = bool(key) and key in (profile.get("author_key") or "")
        return ok, "spotlight author", []
    if "context_bucket" in clause:
        pick = (ctx.get(clause["context_bucket"]) or {}).get("id")
        ok = bool(pick) and pick in (profile.get("buckets") or {})
        return ok, "bucket %s" % (pick or ""), []
    if clause.get("not_pure_epic"):
        buckets = profile.get("buckets") or {}
        tags = profile.get("tags") or {}
        epic = "epic_fantasy" in buckets
        mystery = "mystery" in buckets or any(tag in tags for tag in ("mystery", "crime", "thriller"))
        ok = (not epic) or mystery
        return ok, "mystery tag present" if epic else "not an epic with no mystery tag", []
    if clause.get("genre_signal"):
        ok = bool(profile.get("buckets"))
        return ok, "a genre signal", ["a genre signal"] if ok else []
    if "random" in clause:
        return bool(clause["random"]), "random", []
    ok, detail = _group(clause, profile, ctx)
    return ok, detail or _label(clause), [detail] if ok and detail else []


def _length(kind, profile):
    if kind == "short":
        pages = profile.get("pages")
        minutes = profile.get("minutes")
        if pages is not None and int(pages) <= 350:
            return True, "%s pages" % int(pages), []
        if minutes is not None and int(minutes) <= 360:
            return True, "%s minutes" % int(minutes), []
        return False, "length", []
    pages = profile.get("pages")
    minutes = profile.get("minutes")
    if profile.get("kind") != "series" and not profile.get("series_id"):
        if pages is not None and int(pages) >= 900:
            return True, "%s pages" % int(pages), []
        return False, "length", []
    if profile.get("minutes_known") and minutes is not None and int(minutes) >= 3600:
        return True, "over 60 hours", []
    return False, "length", []


def _classics(profile):
    buckets = profile.get("buckets") or {}
    tags = profile.get("tags") or {}
    if "classics" in buckets or "classics" in tags or "classic" in tags:
        return True, "classics", []
    year = profile.get("year")
    rating = profile.get("rating")
    if year and int(year) < 1990 and rating is not None and float(rating) >= 4:
        return True, "published %s, rating %s" % (year, rating), []
    return False, "classics", []


def _share(clause, profile, ctx):
    source_unit = ctx.get("last_finished") if clause.get("source") == "last_finished" else ctx.get("favorite_unit")
    source = (ctx.get("source_profiles") or {}).get(clause.get("source") or "")
    if source_unit is None or not source:
        return False, "no source book", []
    if source.get("series_id") and source.get("series_id") == profile.get("series_id"):
        return False, "same series", []
    if source.get("id") == profile.get("id"):
        return False, "same book", []
    shared = []
    for bucket in profile.get("buckets") or {}:
        if bucket in (source.get("buckets") or {}):
            shared.append(bucket)
    for mood in profile.get("moods") or {}:
        if mood in (source.get("moods") or {}):
            shared.append("%s mood" % mood)
    left = "series" if profile.get("series_id") or profile.get("kind") == "series" else "standalone"
    right = "series" if source.get("series_id") or source.get("kind") == "series" else "standalone"
    if left == right:
        shared.append(left)
    unique = []
    for item in shared:
        if item not in unique:
            unique.append(item)
    need = int(clause.get("share") or 2)
    return len(unique) >= need, "%s shared signals" % len(unique), unique[:need]


def _positive(profile):
    fired = []
    for mood, source in (profile.get("moods") or {}).items():
        fired.append("%s mood (%s)" % (mood, source))
    for bucket, source in (profile.get("buckets") or {}).items():
        fired.append("%s (%s)" % (bucket, source))
    if profile.get("accolade"):
        fired.append("accolade")
    return fired


def _label(clause):
    if clause.get("fantasy"):
        return "fantasy"
    if clause.get("science"):
        return "science fiction"
    if "mood" in clause or "mood_any" in clause:
        return "mood"
    if "keyword_any" in clause:
        return "keyword"
    if "tag_any" in clause:
        return "tag"
    if "bucket_any" in clause:
        return "bucket"
    if "warning_any" in clause:
        return "warning"
    if "any" in clause or "all" in clause:
        return "match"
    return "gate"


def _group(group, profile, ctx):
    if not isinstance(group, dict):
        return False, ""
    if group.get("hidden_tag"):
        from .shelf_config import HIDDEN_TAGS
        tags = profile.get("tags") or {}
        if any(tag in tags for tag in HIDDEN_TAGS):
            return True, "story signal"
        return False, ""
    if group.get("protagonist_age"):
        from .shelf_config import PROTAGONIST_CUES
        words = profile.get("keywords") or {}
        if any(word in words for word in PROTAGONIST_CUES):
            return True, "early years in the description"
        return False, ""
    if "all" in group:
        details = []
        for part in group["all"]:
            ok, detail = _group(part, profile, ctx)
            if not ok:
                return False, ""
            if detail:
                details.append(detail)
        return True, ", ".join(details)
    if "any" in group:
        for part in group["any"]:
            ok, detail = _group(part, profile, ctx)
            if ok:
                return True, detail
        return False, ""
    if group.get("fantasy"):
        if _fantasy(profile):
            return True, "fantasy"
        return False, ""
    if group.get("science"):
        if _science(profile):
            return True, "science fiction"
        return False, ""
    if "mood" in group:
        if _has_mood(profile, group["mood"]):
            return True, "%s mood (%s)" % (group["mood"], _mood_source(profile, group["mood"]))
        return False, ""
    if "mood_any" in group:
        for mood in group["mood_any"]:
            if _has_mood(profile, mood):
                return True, "%s mood (%s)" % (mood, _mood_source(profile, mood))
        return False, ""
    if "rating_min" in group:
        rating = profile.get("rating")
        if rating is not None and float(rating) >= float(group["rating_min"]):
            return True, "rating %s" % rating
        return False, ""
    hits = []
    for tag in group.get("tag_any") or ():
        if tag in (profile.get("tags") or {}):
            hits.append("%s tag (%s)" % (tag, profile["tags"][tag]))
            break
    for bucket in group.get("bucket_any") or ():
        if bucket in (profile.get("buckets") or {}):
            hits.append("%s (%s)" % (bucket, profile["buckets"][bucket]))
            break
    for word in group.get("keyword_any") or ():
        if word in (profile.get("keywords") or {}):
            hits.append("%s in the description" % word)
            break
    for word in group.get("warning_any") or ():
        if _warning(profile, word):
            hits.append("%s warning (hardcover)" % word)
            break
    if hits:
        return True, hits[0]
    if any(key in group for key in ("tag_any", "bucket_any", "keyword_any", "warning_any")):
        return False, ""
    return False, ""


def _fantasy(profile):
    buckets = profile.get("buckets") or {}
    if any(bucket in buckets for bucket in FANTASY_BUCKETS):
        return True
    return "fantasy" in (profile.get("tags") or {})


def _science(profile):
    buckets = profile.get("buckets") or {}
    if any(bucket in buckets for bucket in SCIENCE_BUCKETS):
        return True
    tags = profile.get("tags") or {}
    return "science fiction" in tags or "scifi" in tags or "sci fi" in tags


def _has_mood(profile, mood):
    moods = profile.get("moods") or {}
    if mood in moods:
        return True
    folded = " ".join(mood.replace("-", " ").split()).casefold()
    return folded in moods


def _mood_source(profile, mood):
    moods = profile.get("moods") or {}
    return moods.get(mood) or moods.get(" ".join(mood.replace("-", " ").split()).casefold()) or "catalog"


def _warning_phrase(profile, phrase):
    warnings = profile.get("warnings") or {}
    folded = " ".join((phrase or "").split()).casefold()
    if not folded:
        return False
    if folded in warnings:
        return True
    return any(folded in name for name in warnings)


def _warning(profile, word):
    warnings = profile.get("warnings") or {}
    if word in warnings:
        return True
    for name in warnings:
        if word in name.split():
            return True
    return False


def _reason(checked, signals, score):
    passed = [item["detail"] for item in checked if item["ok"] and item["detail"]]
    parts = []
    if passed:
        parts.append("Gates: %s." % ". ".join(passed))
    if signals:
        parts.append("Signals: %s." % ". ".join(signals))
    else:
        parts.append("Signals: none.")
    parts.append("Score %s." % score)
    return " ".join(parts)
