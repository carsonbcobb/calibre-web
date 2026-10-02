# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2018-2019 OzzieIsaacs, cervinko, jkrehm, bodybybuddha, ok11,
#                            andy29485, idalin, Kyosfonica, wuqi, Kennyl, lemmsh,
#                            falgh1, grunjol, csitko, ytils, xybydy, trasba, vrabe,
#                            ruben-herold, marblepebble, JackED42, SiphonSquirrel,
#                            apetresc, nanu-c, mutschler
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program. If not, see <http://www.gnu.org/licenses/>.
__package__ = "cps"

import sys
import os
import mimetypes
from datetime import timedelta

from flask import Flask
from flask.sessions import SecureCookieSessionInterface
from flask_themes2 import Themes
from .MyLoginManager import MyLoginManager
from flask_principal import Principal

from . import logger
from .cli import CliParameter
from .reverseproxy import ReverseProxied
from .server import WebServer
from .dep_check import dependency_check
from .updater import Updater
from . import config_sql
from . import cache_buster
from . import ub, db

try:
    from flask_limiter import Limiter
    limiter_present = True
except ImportError:
    limiter_present = False
try:
    from flask_wtf.csrf import CSRFProtect
    wtf_present = True
except ImportError:
    wtf_present = False


mimetypes.init()
mimetypes.add_type('application/xhtml+xml', '.xhtml')
mimetypes.add_type('application/epub+zip', '.epub')
mimetypes.add_type('application/epub+zip', '.kepub')
mimetypes.add_type('application/fb2+zip', '.fb2')
mimetypes.add_type('application/x-mobipocket-ebook', '.mobi')
mimetypes.add_type('application/octet-stream', '.prc')
mimetypes.add_type('application/x-mobipocket-ebook', '.azw')
mimetypes.add_type('application/x-mobipocket-ebook', '.azw3')
mimetypes.add_type('application/x-cbr', '.cbr')
mimetypes.add_type('application/x-cbz', '.cbz')
mimetypes.add_type('application/x-tar', '.cbt')
mimetypes.add_type('application/x-7z-compressed', '.cb7')
mimetypes.add_type('image/vnd.djvu', '.djv')
mimetypes.add_type('image/vnd.djvu', '.djvu')
mimetypes.add_type('application/mpeg', '.mpeg')
mimetypes.add_type('audio/mpeg', '.mp3')
mimetypes.add_type('audio/x-m4a', '.m4a')
mimetypes.add_type('audio/x-m4a', '.m4b')
mimetypes.add_type('audio/x-hx-aac-adts', '.aac')
mimetypes.add_type('audio/vnd.dolby.dd-raw', '.ac3')
mimetypes.add_type('video/x-ms-asf', '.asf')
mimetypes.add_type('audio/ogg', '.ogg')
mimetypes.add_type('application/ogg', '.oga')
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('application/x-ms-reader', '.lit')
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('text/rtf', '.rtf')

log = logger.create()


def _env_flag(name, default=False):
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


# Cookie flags live here. Defaults work on plain http (a phone on the LAN).
# Set COOKIE_SECURE=1 when the site is served only over https.
# Set COOKIE_DOMAIN only if every hostname should share one cookie.
# Set COOKIE_SAMESITE to Lax, Strict, or None.
_COOKIE_SECURE = _env_flag("COOKIE_SECURE", False)
_COOKIE_DOMAIN = (os.environ.get("COOKIE_DOMAIN") or "").strip() or None
_COOKIE_SAMESITE = (os.environ.get("COOKIE_SAMESITE") or "Lax").strip() or "Lax"

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=_COOKIE_SECURE,
    SESSION_COOKIE_SAMESITE=_COOKIE_SAMESITE,
    SESSION_COOKIE_DOMAIN=_COOKIE_DOMAIN,
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SECURE=_COOKIE_SECURE,
    REMEMBER_COOKIE_SAMESITE=_COOKIE_SAMESITE,
    REMEMBER_COOKIE_DOMAIN=_COOKIE_DOMAIN,
    REMEMBER_COOKIE_DURATION=timedelta(days=30),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_PROTECTION="basic",
    WTF_CSRF_SSL_STRICT=False,
    SESSION_COOKIE_NAME=os.environ.get('COOKIE_PREFIX', "") + "session",
    REMEMBER_COOKIE_NAME=os.environ.get('COOKIE_PREFIX', "") + "remember_token"
)

lm = MyLoginManager()

cli_param = CliParameter()

config = config_sql.ConfigSQL()

if wtf_present:
    csrf = CSRFProtect()
else:
    csrf = None

calibre_db = db.CalibreDB(app)

web_server = WebServer()

updater_thread = Updater()
themes_extension = Themes()

if limiter_present:
    limiter = Limiter(key_func=True, headers_enabled=True, in_memory_fallback_enabled=True, default_limits=[],
                      swallow_errors=True)
else:
    limiter = None

def _script_name(wrapper):
    while wrapper is not None and not hasattr(wrapper, "script_name"):
        wrapper = getattr(wrapper, "app", None) or getattr(wrapper, "application", None)
    name = getattr(wrapper, "script_name", "/") if wrapper is not None else "/"
    return (name or "/").rstrip("/") or "/"


class ScriptNameSessionInterface(SecureCookieSessionInterface):
    def get_cookie_path(self, app):
        # Called once per response, after request context exists
        return _script_name(app.wsgi_app)


def create_app():
    app.session_interface = ScriptNameSessionInterface()
    if csrf:
        csrf.init_app(app)

    cli_param.init()

    ub.init_db(cli_param.settings_path)
    # pylint: disable=no-member
    encrypt_key, error = config_sql.get_encryption_key(os.path.dirname(cli_param.settings_path))

    config_sql.load_configuration(ub.session, encrypt_key)
    config.init_config(ub.session, encrypt_key, cli_param)

    if error:
        log.error(error)

    ub.password_change(cli_param.user_credentials)

    if sys.version_info < (3, 0):
        log.info(
            '*** Python2 is EOL since end of 2019, this version of Calibre-Web is no longer supporting Python2, '
            'please update your installation to Python3 ***')
        print(
            '*** Python2 is EOL since end of 2019, this version of Calibre-Web is no longer supporting Python2, '
            'please update your installation to Python3 ***')
        web_server.stop(True)
        sys.exit(5)

    lm.login_view = 'web.login'
    lm.anonymous_user = ub.Anonymous
    # Strong protection hashes the client address into the session. A phone
    # switches between IPv4 and IPv6, or a tunnel adds X-Forwarded-For, and
    # the next page is treated as a different browser. Basic keeps the login.
    lm.session_protection = "basic"
    app.config["SESSION_PROTECTION"] = "basic"

    @app.before_request
    def _keep_session_cookie():
        from flask import session
        session.permanent = True

    db.CalibreDB.update_config(config, config.config_calibre_dir, cli_param.settings_path)

    updater_thread.init_updater(config, web_server)
    # Perform dry run of updater and exit afterward
    if cli_param.dry_run:
        updater_thread.dry_run()
        sys.exit(0)
    updater_thread.start()
    requirements = dependency_check()
    for res in requirements:
        if res['found'] == "not installed":
            message = ('Cannot import {name} module, it is needed to run calibre-web, '
                       'please install it using "pip install {name}"').format(name=res["name"])
            log.info(message)
            print("*** " + message + " ***")
            web_server.stop(True)
            sys.exit(8)
    for res in requirements + dependency_check(True):
        log.info('*** "{}" version does not meet the requirements. '
                 'Should: {}, Found: {}, please consider installing required version ***'
                 .format(res['name'],
                         res['target'],
                         res['found']))
    app.wsgi_app = ReverseProxied(app.wsgi_app)
    trusted_proxies = (getattr(config, "config_reverse_proxy_trusted_ips", "") or "").strip()
    if trusted_proxies:
        from .reverse_proxy_auth import is_trusted_proxy_source

        class _TrustedProxy:
            def __init__(self, application, trusted):
                self.application = application
                self.trusted = trusted

            @property
            def script_name(self):
                return _script_name(self.application)

            def __call__(self, environ, start_response):
                remote = environ.get("REMOTE_ADDR") or ""
                if is_trusted_proxy_source(remote, self.trusted):
                    forwarded = (environ.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
                    if forwarded:
                        environ["REMOTE_ADDR"] = forwarded
                    proto = (environ.get("HTTP_X_FORWARDED_PROTO") or environ.get("HTTP_X_SCHEME") or "").split(",")[0].strip()
                    if proto:
                        environ["wsgi.url_scheme"] = proto
                    host = (environ.get("HTTP_X_FORWARDED_HOST") or "").split(",")[0].strip()
                    if host:
                        environ["HTTP_HOST"] = host
                return self.application(environ, start_response)

        app.wsgi_app = _TrustedProxy(app.wsgi_app, trusted_proxies)
    if not hasattr(app, "theme_manager"):
        themes_extension.init_themes(app)

    if os.environ.get('FLASK_DEBUG'):
        cache_buster.init_cache_busting(app)
    log.info('Starting Calibre Web...')
    Principal(app)
    lm.init_app(app)
    app.secret_key = os.getenv('SECRET_KEY', config_sql.get_flask_session_key(ub.session))

    web_server.init_app(app, config)
    from .cw_babel import babel, get_locale
    if hasattr(babel, "localeselector"):
        babel.init_app(app)
        babel.localeselector(get_locale)
    else:
        babel.init_app(app, locale_selector=get_locale)

    from . import services

    if services.ldap:
        services.ldap.init_app(app, config)
    if services.goodreads_support:
        services.goodreads_support.connect(config.config_goodreads_api_key,
                                           config.config_use_goodreads)
    config.store_calibre_uuid(calibre_db, db.Library_Id)
    # Configure rate limiter
    # https://limits.readthedocs.io/en/stable/storage.html
    app.config.update(RATELIMIT_ENABLED=config.config_ratelimiter)
    if config.config_limiter_uri != "" and not cli_param.memory_backend:
        app.config.update(RATELIMIT_STORAGE_URI=config.config_limiter_uri)
        if config.config_limiter_options != "":
            app.config.update(RATELIMIT_STORAGE_OPTIONS=config.config_limiter_options)
    try:
        limiter.init_app(app)
    except Exception as e:
        log.error('Wrong Flask Limiter configuration, falling back to default: {}'.format(e))
        app.config.update(RATELIMIT_STORAGE_URI=None)
        limiter.init_app(app)

    # Register scheduled tasks
    from .schedule import register_scheduled_tasks, register_startup_tasks
    register_scheduled_tasks(config.schedule_reconnect)
    register_startup_tasks()

    return app
