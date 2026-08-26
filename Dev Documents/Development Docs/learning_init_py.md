# Learning: `__init__.py` — what it is and why we add it

**It's a Python language feature, NOT part of any framework** (nothing to do with
FastAPI, Supabase, etc.).

## What it does
When Python sees a folder containing a file literally named `__init__.py`, it treats
that folder as a **package** — an importable unit. That is what makes this work:
```python
from modules.market_data.upstox.upstox_auth_client import get_analytics_client
```
Python walks `modules/` → `market_data/` → `upstox/`, and the `__init__.py` in each is
the marker that says "this folder is an importable package, you may descend into it."

## It's usually empty
The file's mere *presence* is the signal — it normally contains nothing. (It *can*
contain code that runs the first time the package is imported, e.g. exposing certain
names at the package level, but we rarely want that and keep ours empty.)

## Why add it if things sometimes work without it?
Python 3.3+ has "namespace packages" that can sometimes import a folder with no
`__init__.py` (this is why the first Upstox smoke test ran before we added them). But
relying on that is fragile — it can break depending on import order, tooling, test
runners, and deployment setup. Adding the empty `__init__.py` is the explicit, robust,
conventional way. Rule of thumb: **any folder you import from should have one.**

## In Fortuna
`modules/`, `modules/market_data/`, and `modules/market_data/upstox/` each have an empty
`__init__.py`. When we add `watchlists/`, it gets one too.
