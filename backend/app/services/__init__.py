"""Business logic: orchestration over repositories.

Services own the "what happens when" — candidate intake, seeding a new
account — and the transaction boundary. Routers stay thin; repositories stay
query-only.
"""
