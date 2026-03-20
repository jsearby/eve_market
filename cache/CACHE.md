# Cache Directory

All generated data lives here. These directories are gitignored — regenerate them by running the setup scripts.

| Directory | Contents | Regenerate with |
|-----------|----------|-----------------|
| `sde/` | EVE Static Data Export — blueprints, item types, universe graph, NPC stations (~500 MB) | `python 2_refresh_sde.py` |
| `market/` | Market order snapshots per region (`region_*.json`), refreshed automatically on each run | Delete files to force refresh |
| `esi/` | ESI reference data — player-owned structures discovered during market scans | Rebuilt automatically |
| `user/` | Your character profile, ESI tokens, and API credentials — **keep private** | `python 3_refresh_user_profile.py` |
