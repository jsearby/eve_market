"""
Shared configuration and path constants for all EVE tools.
Import from here instead of redefining paths in each script.
"""

from pathlib import Path

# Project root (tools/ is one level below)
ROOT = Path(__file__).parent.parent

# Cache subdirectories
SDE_DIR  = ROOT / "cache" / "sde"
ESI_DIR  = ROOT / "cache" / "esi"
MKT_DIR  = ROOT / "cache" / "market"
USER_DIR = ROOT / "cache" / "user"

# Derived paths used by multiple scripts
GRAPH_FILE          = SDE_DIR / "universe_graph.json"
REGION_GRAPH_FILE   = SDE_DIR / "universe_region_graph.json"  # region_id -> [adjacent region_ids]
SYSTEM_REGION_FILE  = SDE_DIR / "system_region.json"          # system_id -> region_id
SDE_STATIONS_FILE   = SDE_DIR / "bsd" / "staStations.yaml"
ESI_TOKENS_FILE    = USER_DIR / "esi_tokens.json"
ESI_CREDS_FILE     = USER_DIR / "esi_credentials.json"
PROFILE_FILE       = USER_DIR / "character_profile.json"

# ESI API base URL
ESI_BASE = "https://esi.evetech.net/latest"
