"""
EVE Tools — shared utilities for EVE Online Python scripts.

Import from here instead of reaching directly into submodules:

    from tools import CharacterProfile, load_profile_or_exit, format_isk
    from tools import ESIAuth, load_esi_credentials, setup_esi_credentials
    from tools import find_sde_file, load_cached_yaml, get_yaml_loader
    from tools import fetch_market_orders, fetch_region_orders
    from tools import PROFILE_FILE, SDE_DIR, MKT_DIR, ESI_BASE
"""

from tools.config import (
    ROOT,
    SDE_DIR,
    ESI_DIR,
    MKT_DIR,
    USER_DIR,
    GRAPH_FILE,
    REGION_GRAPH_FILE,
    SYSTEM_REGION_FILE,
    SDE_STATIONS_FILE,
    ESI_TOKENS_FILE,
    ESI_CREDS_FILE,
    PROFILE_FILE,
    ESI_BASE,
)

from tools.character_model import (
    CharacterProfile,
    format_isk,
    generate_profile_report,
    load_profile_or_exit,
)

from tools.sde_loader import (
    find_sde_file,
    load_cached_yaml,
    get_yaml_loader,
)

from tools.esi_auth import (
    ESIAuth,
    load_client_credentials,
    save_client_credentials,
    load_esi_credentials,
    setup_esi_credentials,
)

from tools.esi_market import (
    fetch_market_orders,
    fetch_region_orders,
)
