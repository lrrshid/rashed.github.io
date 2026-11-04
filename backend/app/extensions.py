"""Process-wide singletons shared by the app factory, services and CLI."""
from .core.database import Database

db = Database()
