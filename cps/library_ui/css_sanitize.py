# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import re

MAX_CSS_LENGTH = 200000

# Angle brackets would let an admin stylesheet close the style tag.
# javascript and expression are not needed for visual tweaks.
_DANGEROUS = re.compile(
    r"javascript\s*:|expression\s*\(|-moz-binding|behavior\s*:",
    re.IGNORECASE,
)


def sanitize_css(raw):
    if not raw:
        return ""
    text = str(raw).replace("\x00", "")
    if len(text) > MAX_CSS_LENGTH:
        text = text[:MAX_CSS_LENGTH]
    text = text.replace("<", "")
    text = _DANGEROUS.sub("", text)
    return text
