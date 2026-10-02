# -*- coding: utf-8 -*-

"""Phone layout: one login, then the main pages, at iPhone 12 and Pixel 5."""

import os
import sqlite3
import time
import unittest
import urllib.request
from hashlib import sha512

BASE = os.environ.get("CW_BASE_URL", "http://127.0.0.1:8084")
PATHS = (
    "/",
    "/genres",
    "/genres/Fantasy",
    "/series",
    "/series/1",
    "/discover/stored",
    "/book/36",
    "/friends",
)

MEASURE = """
() => {
  const doc = document.documentElement;
  const nav = document.querySelector(".cw-nav");
  const top = document.querySelector(".library-topnav");
  const shell = document.querySelector(".cw-shell");
  const toasts = document.querySelector(".cw-toasts");
  const broken = [];
  document.querySelectorAll("img").forEach((img) => {
    const style = getComputedStyle(img);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
      return;
    }
    const rect = img.getBoundingClientRect();
    if (rect.width < 2 || rect.bottom < 0 || rect.top > window.innerHeight) {
      return;
    }
    if (img.complete && img.naturalWidth === 0) {
      broken.push(img.currentSrc || img.src);
    }
  });
  const navBox = nav ? nav.getBoundingClientRect() : { height: 999 };
  const topBox = top ? top.getBoundingClientRect() : { bottom: 0 };
  const shellBox = shell ? shell.getBoundingClientRect() : { top: 0 };
  return {
    url: location.pathname + location.search,
    scrollWidth: doc.scrollWidth,
    clientWidth: doc.clientWidth,
    navHeight: navBox.height,
    toastFixed: toasts ? getComputedStyle(toasts).position === "fixed" : false,
    shellGap: shellBox.top - topBox.bottom,
    loggedIn: !!document.querySelector("#logout, .cw-account, #cw-sidebar"),
    broken: broken.slice(0, 8)
  };
}
"""


def _server_up():
    try:
        urllib.request.urlopen(BASE + "/login", timeout=3).read(32)
        return True
    except Exception:
        return False


def _db():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "app.db")


def _mint(user_agent):
    from flask import Flask, session

    base = "%s|%s" % (b"::ffff:127.0.0.1", user_agent.encode())
    ident = sha512(base.encode("utf8")).hexdigest()
    token = "mobile-ui-" + sha512(user_agent.encode()).hexdigest()[:16]
    con = sqlite3.connect(_db(), timeout=5)
    key = con.execute("select flask_session_key from flask_settings").fetchone()[0]
    expiry = int(time.time()) + 900
    con.execute("delete from user_session where random = ?", (token,))
    con.execute(
        "insert into user_session (user_id, session_key, random, expiry) values (?,?,?,?)",
        (1, ident, token, expiry),
    )
    con.commit()
    con.close()
    app = Flask("mobile-ui-check")
    app.secret_key = key
    with app.test_request_context("/"):
        session.permanent = True
        session["_user_id"] = "1"
        session["_fresh"] = True
        session["_id"] = ident
        session["_random"] = token
        response = app.response_class()
        app.session_interface.save_session(app, session, response)
        cookie = response.headers.get("Set-Cookie").split(";", 1)[0].split("=", 1)[1]
    return cookie, token


def _drop(token):
    con = sqlite3.connect(_db(), timeout=5)
    con.execute("delete from user_session where random = ?", (token,))
    con.commit()
    con.close()


class MobileLayoutTest(unittest.TestCase):
    def test_phone_profiles(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            self.skipTest("Playwright is not installed")
        if not _server_up():
            self.skipTest("The library server is not available")

        tokens = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                profiles = (
                    ("iPhone 12", playwright.devices["iPhone 12"], None),
                    ("Pixel 5", playwright.devices["Pixel 5"], None),
                    ("360", playwright.devices["iPhone 12"], 360),
                    ("430", playwright.devices["iPhone 12"], 430),
                )
                for name, device, width in profiles:
                    options = dict(device)
                    if width:
                        options["viewport"] = {"width": width, "height": 844}
                    context = browser.new_context(**options)
                    page = context.new_page()
                    page.goto(BASE + "/login", wait_until="domcontentloaded")
                    user_agent = page.evaluate("() => navigator.userAgent")
                    cookie, token = _mint(user_agent)
                    tokens.append(token)
                    context.add_cookies([{
                        "name": "session",
                        "value": cookie,
                        "url": BASE + "/",
                    }])
                    for path in PATHS:
                        response = page.goto(BASE + path, wait_until="domcontentloaded")
                        self.assertIsNotNone(response, name + " " + path)
                        self.assertLess(response.status, 400, name + " " + path)
                        self.assertNotIn("/login", page.url, name + " " + path)
                        page.wait_for_timeout(250)
                        data = page.evaluate(MEASURE)
                        self.assertTrue(data["loggedIn"], name + " " + path)
                        self.assertLessEqual(
                            data["scrollWidth"], data["clientWidth"] + 1, name + " " + path)
                        self.assertLess(data["navHeight"], 64, name + " " + path)
                        self.assertTrue(data["toastFixed"], name + " " + path)
                        self.assertLess(data["shellGap"], 32, name + " " + path)
                        self.assertEqual(data["broken"], [], name + " " + path + " " + str(data["broken"]))
                    context.close()
                browser.close()
        finally:
            for token in tokens:
                _drop(token)


if __name__ == "__main__":
    unittest.main()
