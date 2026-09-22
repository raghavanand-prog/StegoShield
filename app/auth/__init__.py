"""Authentication: Supabase Auth (email/password) + Postgres, accessed
over Supabase's REST APIs directly via `requests` rather than the
`supabase-py` SDK, to avoid pulling its heavier dependency tree
(gotrue/postgrest/realtime/storage3/websockets) into an already
size-constrained Vercel Python bundle. See supabase_client.py.

The public StegoShield workflows (encode/decode/steganalysis/image
analysis/docs) require none of this and work identically with no
Supabase project configured at all - see Config.AUTH_ENABLED.
"""
