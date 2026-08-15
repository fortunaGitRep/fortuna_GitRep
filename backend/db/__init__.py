# db
# Shared database infrastructure for the Fortuna backend: the Supabase
# service-role connection (supabase_client.py) and the versioned SQL schema
# history (migrations/). Feature-specific read/write logic does NOT live here
# — it lives with its module (e.g. modules/market_data/index_store.py) and
# imports the client from here.
