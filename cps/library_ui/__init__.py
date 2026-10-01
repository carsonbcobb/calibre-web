# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Netflix style library UI extensions.

New data lives in app.db. This package stays beside the stock Calibre-Web
code so upstream merges stay small.
"""


def register_library_ui(app):
    from .blueprint import library_ui_bp
    from .context import library_context
    from .reading import read_bits
    from .ratings.service import rating_bits
    from .store import ensure_tables

    ensure_tables()
    app.register_blueprint(library_ui_bp)
    app.context_processor(library_context)
    app.jinja_env.globals["library_read_bits"] = read_bits
    app.jinja_env.globals["library_rating_bits"] = rating_bits
