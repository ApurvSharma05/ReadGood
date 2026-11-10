"""Flask extensions, created once and bound to the app in create_app()."""
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
csrf = CSRFProtect()
cache = Cache()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
