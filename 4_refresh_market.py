"""
==============================================================================
STEP 4: Market Data Refresh
==============================================================================
Downloads and caches market orders for the regions around your character:
  • Your current region
  • All regions that share a border with your region

Region adjacency is derived fully from the SDE (no heuristics, no hardcoding).
Cache files live in cache/market/region_<id>.json.

Run this:
  - Daily, before using B_trading_route_finder.py or C_eve_market_analyzer.py
  - Any time you want fresh prices

Requires:
  - 2_refresh_sde.py must have been run (builds universe_region_graph.json
    and system_region.json)
  - 3_refresh_user_profile.py must have been run (saves ESI tokens so we can
    read your current location without prompting a browser login)

Estimated time: 1-5 minutes depending on number of regions and cache state.
==============================================================================
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

from tools.config import (
    ESI_BASE,
    ESI_TOKENS_FILE,
    REGION_GRAPH_FILE,
    SYSTEM_REGION_FILE,
    MKT_DIR,
)
from tools.esi_auth import ESIAuth, load_esi_credentials
from tools.esi_market import fetch_region_orders

# ---------------------------------------------------------------------------
# How old a cache file must be before we re-download it.
# Set to 0 to always re-download everything.
# ---------------------------------------------------------------------------
CACHE_MAX_AGE_HOURS = 1


# ==============================================================================
# Region / location helpers
# ==============================================================================

def load_system_region_map() -> dict:
    """Load system_id -> region_id mapping built by 2_refresh_sde.py."""
    if not SYSTEM_REGION_FILE.exists():
        print(
            "\n✗ system_region.json not found.\n"
            "  Run 'python 2_refresh_sde.py' first to build the SDE data."
        )
        sys.exit(1)
    with open(SYSTEM_REGION_FILE, "r") as f:
        return json.load(f)   # keys are strings


def load_region_graph() -> dict:
    """Load region_id -> [adjacent region_ids] mapping from SDE."""
    if not REGION_GRAPH_FILE.exists():
        print(
            "\n✗ universe_region_graph.json not found.\n"
            "  Run 'python 2_refresh_sde.py' first to build the SDE data."
        )
        sys.exit(1)
    with open(REGION_GRAPH_FILE, "r") as f:
        return json.load(f)   # keys are strings, values are lists of ints


def get_character_region(esi: ESIAuth, system_region_map: dict) -> int:
    """Return the region_id the authenticated character is currently in."""
    print("\n📍 Fetching your current location...")
    location = esi.get(f"/characters/{esi.character_id}/location/")
    if not location:
        print("✗ Could not fetch character location from ESI.")
        sys.exit(1)

    system_id = location.get("solar_system_id")
    if not system_id:
        print("✗ Location response did not contain a solar_system_id.")
        sys.exit(1)

    region_id = system_region_map.get(str(system_id))
    if not region_id:
        print(f"✗ System {system_id} not found in system_region.json.")
        sys.exit(1)

    print(f"   Solar system ID : {system_id}")
    print(f"   Region ID       : {region_id}")
    return region_id


def get_regions_to_refresh(current_region: int, region_graph: dict) -> list[int]:
    """Return [current_region] + all directly adjacent regions, sorted."""
    adjacent = region_graph.get(str(current_region), [])
    regions = sorted(set([current_region] + list(adjacent)))
    return regions


# ==============================================================================
# Cache helpers
# ==============================================================================

def cache_age_hours(region_id: int) -> float | None:
    """Return the age of the cached file in hours, or None if it doesn't exist."""
    cache_file = MKT_DIR / f"region_{region_id}.json"
    if not cache_file.exists():
        return None
    age_seconds = time.time() - cache_file.stat().st_mtime
    return age_seconds / 3600


def needs_refresh(region_id: int, max_age_hours: float) -> bool:
    """True if the file is missing or older than max_age_hours."""
    age = cache_age_hours(region_id)
    if age is None:
        return True
    return age > max_age_hours


# ==============================================================================
# Region name lookup (best-effort, for display only)
# ==============================================================================

_KNOWN_REGION_NAMES = {
    10000002: "The Forge",
    10000016: "Lonetrek",
    10000033: "The Citadel",
    10000042: "Metropolis",
    10000030: "Heimatar",
    10000043: "Domain",
    10000032: "Sinq Laison",
    10000064: "Essence",
    10000037: "Everyshore",
    10000068: "Verge Vendor",
    10000052: "Kador",
    10000038: "Devoid",
    10000036: "Placid",
    10000067: "Genesis",
    10000029: "Caldari Prime / Forge border",
    10000028: "Molden Heath",
    10000027: "Aridia",
    10000003: "Vale of the Silent",
    10000017: "Great Wildlands",
    10000020: "Tash-Murkon",
}


def region_name(region_id: int) -> str:
    return _KNOWN_REGION_NAMES.get(region_id, f"Region {region_id}")


# ==============================================================================
# ESI authentication (reuse saved tokens; no browser prompt)
# ==============================================================================

def authenticate_silent() -> ESIAuth:
    """
    Authenticate using saved tokens only — no browser/interactive prompt.
    Fails with a clear message if tokens are missing or expired.
    """
    client_id, client_secret = load_esi_credentials()
    if not client_id or not client_secret:
        print(
            "\n✗ No ESI credentials found.\n"
            "  Run 'python 3_refresh_user_profile.py' to set them up."
        )
        sys.exit(1)

    esi = ESIAuth(client_id, client_secret)

    if not ESI_TOKENS_FILE.exists():
        print(
            "\n✗ No saved ESI tokens found.\n"
            "  Run 'python 3_refresh_user_profile.py' to authenticate first."
        )
        sys.exit(1)

    if not esi.load_tokens():
        print(
            "\n✗ Saved ESI tokens have expired.\n"
            "  Run 'python 3_refresh_user_profile.py' to re-authenticate."
        )
        sys.exit(1)

    print(f"✓ Authenticated as: {esi.character_name}")
    return esi


# ==============================================================================
# Main
# ==============================================================================

def main():
    print("\n" + "=" * 80)
    print("STEP 4: Market Data Refresh")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Authenticate (silent — reuse saved tokens)
    esi = authenticate_silent()

    # 2. Load SDE maps
    print("\n📂 Loading SDE region maps...")
    system_region_map = load_system_region_map()
    region_graph = load_region_graph()
    print(f"   ✓ {len(system_region_map):,} systems mapped to regions")
    print(f"   ✓ {len(region_graph):,} regions in region graph")

    # 3. Determine which regions to refresh
    current_region = get_character_region(esi, system_region_map)
    regions = get_regions_to_refresh(current_region, region_graph)

    print(f"\n🗺️  Regions to refresh ({len(regions)} total):")
    for rid in regions:
        marker = " ← you are here" if rid == current_region else ""
        age = cache_age_hours(rid)
        age_str = f"{age:.1f}h old" if age is not None else "not cached"
        print(f"   • {region_name(rid):30s} (id {rid})  [{age_str}]{marker}")

    # 4. Decide what actually needs downloading
    to_download = [rid for rid in regions if needs_refresh(rid, CACHE_MAX_AGE_HOURS)]
    already_fresh = [rid for rid in regions if rid not in to_download]

    if already_fresh:
        print(f"\n⚡ {len(already_fresh)} region(s) already fresh (< {CACHE_MAX_AGE_HOURS}h old) — skipping.")

    if not to_download:
        print("\n✓ All regions are up to date. Nothing to download.")
        print("\nTip: delete files in cache/market/ to force a full refresh.")
    else:
        print(f"\n📥 Downloading {len(to_download)} region(s)...\n")
        MKT_DIR.mkdir(parents=True, exist_ok=True)

        session = requests.Session()
        session.headers.update({"User-Agent": "EVE-Market-Refresh/1.0 (respectful bot)"})

        total_orders = 0
        start = time.time()

        for i, region_id in enumerate(to_download, 1):
            name = region_name(region_id)
            print(f"  [{i}/{len(to_download)}] {name} ({region_id})...", end=" ", flush=True)

            # Remove stale cache so fetch_region_orders re-downloads
            cache_file = MKT_DIR / f"region_{region_id}.json"
            if cache_file.exists():
                cache_file.unlink()

            t0 = time.time()
            orders = fetch_region_orders(region_id, session=session)
            elapsed = time.time() - t0

            total_orders += len(orders)
            print(f"✓  {len(orders):,} orders  ({elapsed:.1f}s)")

        elapsed_total = time.time() - start
        print(f"\n✓ Downloaded {total_orders:,} orders across {len(to_download)} region(s) in {elapsed_total:.1f}s")

    # 5. Summary
    print("\n" + "=" * 80)
    print("✓ STEP 4 COMPLETE!")
    print("=" * 80)
    print(f"\nMarket cache covers {len(regions)} region(s) around your current location:")
    for rid in regions:
        cache_file = MKT_DIR / f"region_{rid}.json"
        if cache_file.exists():
            size_mb = cache_file.stat().st_size / (1024 * 1024)
            age = cache_age_hours(rid)
            print(f"   ✓ {region_name(rid):30s}  {size_mb:.1f} MB  ({age:.1f}h old)")
        else:
            print(f"   ✗ {region_name(rid):30s}  (not cached — download may have failed)")

    print(
        "\nYou can now run:\n"
        "  • python B_trading_route_finder.py\n"
        "  • python C_eve_market_analyzer.py\n"
        "\nRe-run 4_refresh_market.py daily (or delete cache/market/*.json to force a full refresh)."
    )
    print("\no7 Fly safe!")


if __name__ == "__main__":
    main()
