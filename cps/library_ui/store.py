# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2026
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from . import logger_helper
from .models import Base, LibrarySetting

log = logger_helper.log


def ensure_tables():
    """Create library UI tables and add any columns introduced later."""
    from .. import ub

    engine = ub.session.bind
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine):
    """SQLite migration: add model columns that are not in the table yet."""
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            col_type = column.type.compile(dialect=engine.dialect)
            statement = text(
                "ALTER TABLE %s ADD COLUMN %s %s" % (table.name, column.name, col_type)
            )
            log.info("Library UI migration: %s", statement)
            with engine.begin() as conn:
                conn.execute(statement)


def get_setting(key, default=""):
    from .. import ub

    try:
        row = ub.session.query(LibrarySetting).filter(LibrarySetting.key == key).one_or_none()
    except OperationalError:
        ub.session.rollback()
        return default
    if row is None or row.value is None:
        return default
    return row.value


def set_setting(key, value):
    from .. import ub

    row = ub.session.query(LibrarySetting).filter(LibrarySetting.key == key).one_or_none()
    if row is None:
        row = LibrarySetting(key=key, value=value)
        ub.session.add(row)
    else:
        row.value = value
    ub.session_commit("Library UI setting updated: %s" % key)
    return row
