# -*- coding: utf-8 -*-

"""Request the library pages and fail if any of them returns a server error."""

import os
import re
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYTHONUNBUFFERED", "1")

from cps import create_app, ub
from cps.services.background_scheduler import BackgroundScheduler


PATHS = (
    "/",
    "/genres",
    "/genres/Fantasy",
    "/series",
    "/series/1",
    "/discover/stored",
    "/book/3",
)

USERS = (
    ("admin", 1),
    ("reader", 3),
)


def _stop_scheduler():
    scheduler = getattr(BackgroundScheduler, "_instance", None)
    if scheduler is None or not getattr(scheduler, "scheduler", None):
        return
    try:
        if scheduler.scheduler.running:
            scheduler.scheduler.shutdown(wait=False)
    except Exception:
        return


def _boot():
    application = create_app()
    from cps.web import web
    from cps.basic import basic
    from cps.opds import opds
    from cps.admin import admi
    from cps.gdrive import gdrive
    from cps.editbooks import editbook
    from cps.about import about
    from cps.search import search
    from cps.search_metadata import meta
    from cps.shelf import shelf
    from cps.tasks_status import tasks
    from cps.error_handler import init_errorhandler
    from cps.remotelogin import remotelogin
    from cps.jinjia import jinjia
    from cps.library_ui import register_library_ui

    init_errorhandler()
    application.register_blueprint(search)
    application.register_blueprint(tasks)
    application.register_blueprint(web)
    application.register_blueprint(basic)
    application.register_blueprint(opds)
    application.register_blueprint(jinjia)
    application.register_blueprint(about)
    application.register_blueprint(shelf)
    application.register_blueprint(admi)
    application.register_blueprint(remotelogin)
    application.register_blueprint(meta)
    application.register_blueprint(gdrive)
    application.register_blueprint(editbook)
    register_library_ui(application)
    application.config["TESTING"] = True
    application.config["WTF_CSRF_ENABLED"] = False
    application.config["SESSION_PROTECTION"] = None
    return application


def setUpModule():
    global app
    app = _boot()


def tearDownModule():
    try:
        ub.session.query(ub.User_Sessions).filter(ub.User_Sessions.session_key.like("smoke-%")).delete(
            synchronize_session=False
        )
        ub.session.commit()
    except Exception:
        ub.session.rollback()
    _stop_scheduler()


class LibraryPageSmokeTest(unittest.TestCase):
    def test_pages_return_200_for_admin_and_reader(self):
        client = app.test_client()
        for label, user_id in USERS:
            self._login(client, user_id)
            for path in PATHS:
                response = client.get(path, follow_redirects=False)
                self.assertEqual(
                    200,
                    response.status_code,
                    "%s %s returned %s" % (label, path, response.status_code),
                )
                self.assertNotIn(b"Internal Server Error", response.data)
                self.assertNotIn(b"Nothing matches", response.data)
                if path == "/discover/stored":
                    row_ids = set(re.findall(br'id="shelf-discover-[^"]+"', response.data))
                    cards = len(re.findall(br'class="library-card(?: |")', response.data))
                    self.assertGreaterEqual(len(row_ids), 5, "%s discover rows %s" % (label, len(row_ids)))
                    self.assertGreaterEqual(cards, 24, "%s discover cards %s" % (label, cards))

    def test_book_request_pages(self):
        client = app.test_client()
        self._login(client, 3)
        response = client.get("/request")
        self.assertEqual(200, response.status_code)
        self.assertNotIn(b"Nothing matches", response.data)
        response = client.get("/admin/requests")
        self.assertEqual(403, response.status_code)
        response = client.post("/admin/requests/update", data={"action": "delete", "ids": "1"})
        self.assertEqual(403, response.status_code)
        self._login(client, 1)
        response = client.get("/request")
        self.assertEqual(200, response.status_code)
        self.assertIn(b"Request a Book", response.data)
        response = client.get("/admin/requests")
        self.assertEqual(200, response.status_code)
        self.assertNotIn(b"Nothing matches", response.data)
        self.assertIn(b"Book Requests", response.data)

    def _login(self, client, user_id):
        key = "smoke-%s" % user_id
        token = "smoke-token-%s" % user_id
        expiry = int((datetime.now() + timedelta(days=1)).timestamp())
        existing = ub.session.query(ub.User_Sessions).filter(ub.User_Sessions.session_key == key).first()
        if existing is None:
            ub.session.add(ub.User_Sessions(user_id, key, token, expiry))
            ub.session.commit()
        if not hasattr(app.wsgi_app, "script_name"):
            app.wsgi_app.script_name = ""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_id)
            sess["_id"] = key
            sess["_random"] = token
            sess["_fresh"] = True


if __name__ == "__main__":
    try:
        result = unittest.main(exit=False, verbosity=2)
        code = 0 if result.result.wasSuccessful() else 1
    finally:
        _stop_scheduler()
    os._exit(code)
