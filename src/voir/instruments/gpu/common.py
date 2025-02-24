"""Common utilities and functions for the various GPU reporting backends."""


class NotAvailable(Exception):
    """Raised by GPU backend when the backend is not available"""
