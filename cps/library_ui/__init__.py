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
    from .ratings.service import rating_info

    app.jinja_env.globals["library_read_bits"] = read_bits
    app.jinja_env.globals["library_rating_bits"] = rating_bits
    app.jinja_env.globals["library_rating_info"] = rating_info
    from .accolades import about_html, quote_sections, quotes_for, tags_for, top_accolade
    from .ratings.hardcover import profile_for
    from .flags import library_is_favorite, library_is_wanted
    app.jinja_env.globals["library_top_accolade"] = top_accolade
    app.jinja_env.globals["library_accolade_tags"] = tags_for
    app.jinja_env.globals["library_quotes"] = quotes_for
    app.jinja_env.globals["library_quote_sections"] = quote_sections
    from .reviews import reviews_for
    app.jinja_env.globals["library_reviews"] = reviews_for
    app.jinja_env.globals["library_about"] = about_html
    app.jinja_env.globals["library_hardcover"] = profile_for
    app.jinja_env.globals["library_is_favorite"] = library_is_favorite
    app.jinja_env.globals["library_is_wanted"] = library_is_wanted
    from .comments import comments_for_book, user_name
    from .send import send_choice
    app.jinja_env.globals["library_comments"] = comments_for_book
    app.jinja_env.globals["library_comment_author"] = user_name
    app.jinja_env.globals["library_send_choice"] = send_choice
