from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)

# Per-client-IP limits on the endpoints worth abusing. Storage is Redis in compose, so
# limits hold across every gunicorn worker and API replica.
limiter = Limiter(key_func=get_remote_address, headers_enabled=True)
