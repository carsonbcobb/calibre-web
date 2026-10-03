# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Genre names now live in shelf_config.py. This module only re-exports them."""

from .shelf_config import (  # noqa: F401
    BUCKETS,
    NATIONALITY_TAGS,
    NOISE_TAGS,
    ROW_MIN,
    TAG_BUCKETS,
    bucket_for_tag,
    bucket_name_for_tag,
)

ROW_SHOW = 8
