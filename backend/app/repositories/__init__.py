"""Data access: every SQLAlchemy query lives here, keyed by aggregate.

Repositories take a ``Session`` and return entities or plain values. They hold
no business rules and never talk HTTP — that is the service and router layers.
"""
