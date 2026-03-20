"""
==============================================================================
EVE Online Blueprint Finder
==============================================================================
Searches the market AND public contracts for Blueprint Originals (BPO) and
Blueprint Copies (BPC) across major trade hubs, sorted by price. Shows jump
distance from your current location.

Usage:
  python D_find_blueprint.py --target "<item name>"
  python D_find_blueprint.py --target "<item name>" --contracts

Flags:
  --contracts   Also scan public contracts (slower, ~30-60s extra)
  --top N       Show top N results per section (default: 10)

Example:
  python D_find_blueprint.py --target "Porpoise"
  python D_find_blueprint.py --target "Porpoise" --contracts
  python D_find_blueprint.py --target "Orca" --contracts --top 20

Requires: 2_refresh_sde.py and 3_refresh_user_profile.py to be run first
=============================================================================="""

import json
import sys
import argparse
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import yaml

_thread_local = threading.local()

def _get_session() -> requests.Session:
    if not hasattr(_thread_local, "session"):
        _thread_local.session = requests.Session()
    return _thread_local.session

from tools.character_model import load_profile_or_exit, format_isk
from tools.config import (
    ESI_BASE, ESI_DIR, SDE_DIR, SDE_STATIONS_FILE, GRAPH_FILE
)
from tools.sde_loader import find_sde_file, load_cached_yaml, get_yaml_loader

# ──────────────────────────────────────────────────────────────────────────────
# Regions to search (major trade hubs + high-sec industrial areas)
# ──────────────────────────────────────────────────────────────────────────────
SEARCH_REGIONS = {
    10000002: "The Forge (Jita)",
    10000043: "Domain (Amarr)",
    10000042: "Metropolis (Hek)",
    10000030: "Heimatar (Rens)",
    10000032: "Sinq Laison (Dodixie)",
    10000033: "The Citadel",
    10000016: "Lonetrek",
    10000067: "Genesis",
    10000052: "Kador",
}

# Well-known hub anchor systems (for jump distance display)
REGION_HUB_SYSTEM = {
    10000002: 30000142,  # Jita
    10000043: 30002187,  # Amarr
    10000042: 30002659,  # Hek
    10000030: 30002510,  # Rens
    10000032: 30002659,  # Dodixie (approx)
    10000033: 30000049,  # Perimeter
    10000016: 30001161,  # Nourvukaiken
    10000067: 30005196,  # Yulai
    10000052: 30004049,  # Amarr-adjacent
}


def _print_header():
    print("=" * 80)
    print("🔍 EVE ONLINE BLUEPRINT FINDER")
    print("=" * 80)
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ──────────────────────────────────────────────────────────────────────────────
# SDE helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_types() -> Dict:
    types_file = find_sde_file("types.yaml")
    if not types_file:
        print("✗ types.yaml not found. Run 'python 2_refresh_sde.py' first.")
        sys.exit(1)
    return load_cached_yaml(types_file, "types_cache.pkl", "types")


def find_blueprint_type_ids(item_name: str, types: Dict) -> Tuple[Optional[int], Optional[int]]:
    """
    Return (bpo_type_id, bpc_type_id) for the given item name.
    BPO name = "<Item> Blueprint"
    BPC name is the same type — in EVE, BPCs are copies of the same typeID,
    distinguishable only via the isSingleton / quantity flag on market orders.
    We return the single blueprint typeID and filter orders by quantity later.
    """
    target_bpo = f"{item_name.strip()} Blueprint"
    bpo_id = None

    for type_id, data in types.items():
        name = data.get("name", {}).get("en", "")
        if name.lower() == target_bpo.lower():
            bpo_id = type_id
            break

    # BPC is the same typeID — a BPO listed with quantity -1 or via contract
    # On the open market, BPCs often show as quantity -1 (negative = copy).
    # We return the same type_id; the caller separates by order quantity sign.
    return bpo_id, bpo_id  # (bpo_id, bpc_id) — same type, filtered by qty


# ──────────────────────────────────────────────────────────────────────────────
# Station name resolution
# ──────────────────────────────────────────────────────────────────────────────

def load_station_cache() -> Dict[str, Dict]:
    """Load NPC stations from SDE + player structures from ESI cache."""
    cache: Dict[str, Dict] = {}

    if SDE_STATIONS_FILE.exists():
        try:
            loader = get_yaml_loader()
            with open(SDE_STATIONS_FILE, "r", encoding="utf-8") as f:
                for s in yaml.load(f, Loader=loader):
                    sid = str(s["stationID"])
                    cache[sid] = {
                        "station_id": s["stationID"],
                        "system_id": s["solarSystemID"],
                        "name": s["stationName"],
                    }
        except Exception as e:
            print(f"   ⚠️  Could not load SDE stations: {e}")

    esi_cache = ESI_DIR / "stations_permanent.json"
    if esi_cache.exists():
        try:
            with open(esi_cache) as f:
                for sid, data in json.load(f).items():
                    if sid not in cache:
                        cache[sid] = data
        except Exception:
            pass

    return cache


def resolve_station_name(location_id: int, station_cache: Dict, session: requests.Session) -> Tuple[str, int]:
    """Return (station_name, system_id). Fetches from ESI if not cached."""
    sid = str(location_id)
    if sid in station_cache:
        s = station_cache[sid]
        return s["name"], s["system_id"]

    # Player-owned structure — query ESI
    try:
        r = session.get(f"{ESI_BASE}/universe/structures/{location_id}/",
                        params={"datasource": "tranquility"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            name = data.get("name", f"Structure {location_id}")
            system_id = data.get("solar_system_id", 0)
            station_cache[sid] = {"station_id": location_id, "system_id": system_id, "name": name}
            return name, system_id
    except Exception:
        pass

    return f"Unknown ({location_id})", 0


# ──────────────────────────────────────────────────────────────────────────────
# Jump calculation
# ──────────────────────────────────────────────────────────────────────────────

def load_universe_graph() -> Optional[Dict[int, List[int]]]:
    if not GRAPH_FILE.exists():
        return None
    try:
        with open(GRAPH_FILE) as f:
            return {int(k): v for k, v in json.load(f).items()}
    except Exception:
        return None


def calc_jumps(graph: Optional[Dict], src: int, dst: int) -> Optional[int]:
    if graph is None or src == dst:
        return 0 if src == dst else None
    if src not in graph or dst not in graph:
        return None
    visited = {src}
    queue = deque([(src, 0)])
    while queue:
        node, dist = queue.popleft()
        for nb in graph.get(node, []):
            if nb == dst:
                return dist + 1
            if nb not in visited:
                visited.add(nb)
                queue.append((nb, dist + 1))
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Market fetch
# ──────────────────────────────────────────────────────────────────────────────

def fetch_orders_for_type(region_id: int, type_id: int, session: requests.Session) -> List[Dict]:
    """Fetch all sell orders for a type in a region (ESI type-filtered endpoint)."""
    orders = []
    page = 1
    while True:
        try:
            r = session.get(
                f"{ESI_BASE}/markets/{region_id}/orders/",
                params={
                    "datasource": "tranquility",
                    "order_type": "sell",
                    "type_id": type_id,
                    "page": page,
                },
                timeout=15,
            )
            if r.status_code == 404:
                break
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            orders.extend(batch)
            total = int(r.headers.get("x-pages", 1))
            if page >= total:
                break
            page += 1
        except Exception:
            break
    return orders


# ──────────────────────────────────────────────────────────────────────────────
# Contract scanning
# ──────────────────────────────────────────────────────────────────────────────

# Regions with active contract markets (fewer but more focused than market scan)
CONTRACT_REGIONS = {
    10000002: "The Forge (Jita)",
    10000043: "Domain (Amarr)",
    10000042: "Metropolis (Hek)",
    10000030: "Heimatar (Rens)",
    10000032: "Sinq Laison (Dodixie)",
}

MAX_CONTRACT_PAGES = 5  # 5,000 contracts per region — newest/most relevant


def _fetch_contract_page(region_id: int, page: int) -> List[Dict]:
    try:
        r = _get_session().get(
            f"{ESI_BASE}/contracts/public/{region_id}/",
            params={"datasource": "tranquility", "page": page},
            timeout=15,
        )
        if r.status_code in (404, 204):
            return []
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def _fetch_contract_items(contract_id: int) -> List[Dict]:
    try:
        r = _get_session().get(
            f"{ESI_BASE}/contracts/public/items/{contract_id}/",
            params={"datasource": "tranquility"},
            timeout=15,
        )
        if r.status_code in (404, 204):
            return []
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def fetch_contracts_for_region(region_id: int, region_label: str) -> List[Dict]:
    """Fetch up to MAX_CONTRACT_PAGES pages of public contracts for a region."""
    # Page 1 to get total page count
    try:
        r = _get_session().get(
            f"{ESI_BASE}/contracts/public/{region_id}/",
            params={"datasource": "tranquility", "page": 1},
            timeout=15,
        )
        r.raise_for_status()
        contracts = r.json()
        total_pages = min(int(r.headers.get("x-pages", 1)), MAX_CONTRACT_PAGES)
    except Exception:
        return []

    if total_pages > 1:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(_fetch_contract_page, region_id, p)
                       for p in range(2, total_pages + 1)]
            for f in as_completed(futures):
                contracts.extend(f.result())

    return contracts


def search_contracts(
    type_id: int,
    bp_volume: float,
    station_cache: Dict,
    graph: Optional[Dict],
    origin_system: Optional[int],
    min_price: float = 0.0,
    max_price: float = float("inf"),
) -> List[Dict]:
    """
    Scan public contracts across CONTRACT_REGIONS for a blueprint typeID.

    Strategy to keep it fast:
      1. Fetch up to MAX_CONTRACT_PAGES pages per region in parallel.
      2. Keep only item_exchange / auction contracts.
      3. Pre-filter by price range (derived from market results) and
         volume ≤ max(bp_volume * 100, 1.0) m³ to eliminate cargo/package deals.
      4. Parallel-fetch items for the remaining contracts (8 workers).
      5. Return contracts that contain our typeID (included items only).
    """
    max_vol = max(bp_volume * 100, 1.0)  # generous upper bound for bundles
    results: List[Dict] = []

    print(f"   Scanning up to {MAX_CONTRACT_PAGES} pages per region ", end="", flush=True)
    print(f"(≤{MAX_CONTRACT_PAGES*1000:,} contracts each)...")

    all_candidates: List[Dict] = []
    for region_id, region_label in CONTRACT_REGIONS.items():
        print(f"   • {region_label}...", end=" ", flush=True)
        contracts = fetch_contracts_for_region(region_id, region_label)

        candidates = [
            c for c in contracts
            if c.get("type") in ("item_exchange", "auction")
            and c.get("volume", 9999) <= max_vol
            and min_price <= c.get("price", 0) <= max_price
        ]
        for c in candidates:
            c["_region_id"] = region_id
            c["_region_label"] = region_label
        all_candidates.extend(candidates)
        print(f"✓ {len(contracts):,} contracts → {len(candidates)} candidates")

    if not all_candidates:
        return []

    # Parallel item fetch
    print(f"   Checking items for {len(all_candidates)} candidate contracts...", flush=True)

    def check_contract(contract: Dict) -> Optional[Dict]:
        items = _fetch_contract_items(contract["contract_id"])
        for item in items:
            if item.get("type_id") == type_id and item.get("is_included", True):
                contract["_item"] = item  # carries ME/TE/runs/is_bpc
                return contract
        return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(check_contract, c): c for c in all_candidates}
        for f in as_completed(futures):
            result = f.result()
            if result is not None:
                results.append(result)

    # Resolve station names + jumps
    sess = requests.Session()
    for c in results:
        loc = c.get("start_location_id", 0)
        name, system_id = resolve_station_name(loc, station_cache, sess)
        c["_station_name"] = name
        c["_system_id"] = system_id
        c["_jumps"] = calc_jumps(graph, origin_system, system_id) if (origin_system and graph and system_id) else None

    return sorted(results, key=lambda c: c["price"])


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Find blueprint BPO/BPC on the market and contracts")
    parser.add_argument("--target", required=True, help="Item name (e.g. 'Porpoise')")
    parser.add_argument("--top", type=int, default=10, help="How many results to show per section (default: 10)")
    parser.add_argument("--contracts", action="store_true", help="Also scan public contracts (slower)")
    args = parser.parse_args()

    _print_header()

    # ── Profile (for current location / jump distance origin) ────────────────
    print("\n📋 Loading character profile...")
    profile = load_profile_or_exit()
    print(f"   ✓ {profile.name}")

    origin_system: Optional[int] = None
    if hasattr(profile, "location") and profile.location:
        origin_system = profile.location.get("system_id")
    if origin_system:
        print(f"   ✓ Current system: {origin_system}")
    else:
        print("   ⚠️  Current location unknown — jump counts unavailable")

    # ── SDE ──────────────────────────────────────────────────────────────────
    print("\n📚 Loading SDE data...")
    types = load_types()
    print(f"   ✓ {len(types):,} types loaded")

    bpo_id, _ = find_blueprint_type_ids(args.target, types)
    if bpo_id is None:
        print(f"\n✗ No blueprint found for '{args.target}'.")
        print("  Check the item name (e.g. 'Porpoise', 'Orca', 'Retriever')")
        sys.exit(1)
    bp_name = types[bpo_id].get("name", {}).get("en", f"Type {bpo_id}")
    bp_volume = types[bpo_id].get("volume", 0.01)
    print(f"   ✓ Blueprint: {bp_name} (typeID {bpo_id}, {bp_volume} m³)")
    print(f"   ✓ Blueprint: {bp_name} (typeID {bpo_id})")

    # ── Station cache + universe graph ────────────────────────────────────────
    station_cache = load_station_cache()
    graph = load_universe_graph()
    if graph:
        print(f"   ✓ Universe graph loaded ({len(graph):,} systems)")
    else:
        print("   ⚠️  Universe graph not found — jump counts unavailable")

    # ── Market scan ──────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"📥 Scanning {len(SEARCH_REGIONS)} regions for '{bp_name}'...")
    print(f"{'='*80}")

    session = requests.Session()
    all_bpo: List[Dict] = []
    all_bpc: List[Dict] = []

    for region_id, region_label in SEARCH_REGIONS.items():
        print(f"   • {region_label}...", end=" ", flush=True)
        orders = fetch_orders_for_type(region_id, bpo_id, session)
        bpo_here = [o for o in orders if o.get("volume_remain", 0) > 0 and o.get("price", 0) > 0]
        # EVE market: BPCs have volume_remain = -1 in contracts, but on open market
        # BPOs and BPCs share the same typeID. Quantity = 1 typically means BPO.
        # We show all sell orders and tag them — user can verify in-game.
        print(f"✓ {len(bpo_here)} sell orders")
        for o in bpo_here:
            o["_region_id"] = region_id
            o["_region_label"] = region_label
        all_bpo.extend(bpo_here)

    if not all_bpo:
        print(f"\n✗ No sell orders found for '{bp_name}' in any scanned region.")
        print("   The blueprint may only be available via contracts or LP stores.")
        sys.exit(0)

    # ── Resolve station names + jump distances ────────────────────────────────
    print(f"\n🗺️  Resolving {len(all_bpo)} order location(s)...")
    for order in all_bpo:
        name, system_id = resolve_station_name(order["location_id"], station_cache, session)
        order["_station_name"] = name
        order["_system_id"] = system_id
        if origin_system and graph and system_id:
            order["_jumps"] = calc_jumps(graph, origin_system, system_id)
        else:
            order["_jumps"] = None

    # Save any newly discovered player structures
    esi_cache_path = ESI_DIR / "stations_permanent.json"
    try:
        ESI_DIR.mkdir(parents=True, exist_ok=True)
        sde_ids = set()
        if SDE_STATIONS_FILE.exists():
            loader = get_yaml_loader()
            with open(SDE_STATIONS_FILE, "r", encoding="utf-8") as f:
                for s in yaml.load(f, Loader=loader):
                    sde_ids.add(str(s["stationID"]))
        esi_only = {k: v for k, v in station_cache.items() if k not in sde_ids}
        if esi_only:
            with open(esi_cache_path, "w") as f:
                json.dump(esi_only, f)
    except Exception:
        pass

    # ── Sort and display ──────────────────────────────────────────────────────
    sorted_orders = sorted(all_bpo, key=lambda o: o["price"])
    print(f"\n{'='*80}")
    print(f"💰 CHEAPEST SELL ORDERS — {bp_name}")
    print(f"   Note: All orders share the same typeID. In EVE, BPOs appear in")
    print(f"   Personal Assets as 'Original', BPCs as 'Copy'. Verify in-game.")
    print(f"{'='*80}")

    header = f"  {'#':>3}  {'Price':>18}  {'Qty':>4}  {'Jumps':>5}  Station"
    print(header)
    print("  " + "-" * 76)

    shown = 0
    for order in sorted_orders:
        if shown >= args.top:
            break
        price     = order["price"]
        qty       = order.get("volume_remain", 1)
        jumps     = order["_jumps"]
        station   = order["_station_name"]
        region    = order["_region_label"]
        jumps_str = f"{jumps:>4}j" if jumps is not None else "   ?j"

        print(f"  {shown+1:>3}. {format_isk(price):>16}    {qty:>4}  {jumps_str}   {station}")
        print(f"                                             └─ {region}")
        shown += 1

    if len(sorted_orders) > args.top:
        print(f"\n  ... and {len(sorted_orders) - args.top} more orders. Use --top N to see more.")

    # ── Contract scan (optional) ──────────────────────────────────────────────
    contract_results: List[Dict] = []
    if args.contracts:
        # Use market price range as pre-filter: 30% below cheapest to 3x cheapest
        min_p = sorted_orders[0]["price"] * 0.3 if sorted_orders else 0.0
        max_p = sorted_orders[0]["price"] * 3.0 if sorted_orders else float("inf")
        print(f"\n{'='*80}")
        print(f"📜 CONTRACT SCAN — {bp_name}")
        if sorted_orders:
            print(f"   Price filter: {format_isk(min_p)} – {format_isk(max_p)} (based on cheapest market price)")
        print(f"   Blueprint volume: {bp_volume} m³ · Pre-filter keeps contracts ≤ {max(bp_volume*100, 1.0):.1f} m³")
        print(f"{'='*80}")
        contract_results = search_contracts(
            bpo_id, bp_volume, station_cache, graph, origin_system,
            min_price=min_p,
            max_price=max_p,
        )

        if not contract_results:
            print("   ✗ No matching contracts found in scanned pages.")
            print("   Try searching in-game: Business → Contracts → search blueprint name")
        else:
            print(f"\n   Found {len(contract_results)} contract(s) containing {bp_name}:\n")
            header = f"  {'#':>3}  {'Price':>16}  {'Type':>4}  {'ME':>3}  {'TE':>3}  {'Runs':>5}  {'Jumps':>5}  Location"
            print(header)
            print("  " + "-" * 82)
            for i, c in enumerate(contract_results[:args.top], 1):
                item      = c.get("_item", {})
                is_bpc    = item.get("is_blueprint_copy", False)
                me        = item.get("material_efficiency", "?")
                te        = item.get("time_efficiency", "?")
                runs      = item.get("runs", -1)
                bp_type   = "BPC" if is_bpc else "BPO"
                runs_str  = f"{runs:>5}" if (is_bpc and runs and runs > 0) else "   ∞" if not is_bpc else "    ?"
                jumps     = c.get("_jumps")
                jumps_str = f"{jumps:>4}j" if jumps is not None else "   ?j"
                title     = c.get("title", "") or ""
                station   = c.get("_station_name", "Unknown")
                region    = c.get("_region_label", "")
                print(f"  {i:>3}. {format_isk(c['price']):>14}  {bp_type:>4}  {me:>3}  {te:>3}  {runs_str}  {jumps_str}   {station}")
                if title:
                    print(f"                                                          └─ '{title}' · {region}")
                else:
                    print(f"                                                          └─ {region}")
            if len(contract_results) > args.top:
                print(f"\n  ... and {len(contract_results) - args.top} more. Use --top N to see more.")

    # ── Summary ───────────────────────────────────────────────────────────────
    all_options = (
        [("market", o["price"], o["_station_name"], o.get("_jumps")) for o in sorted_orders] +
        [("contract", c["price"], c["_station_name"], c.get("_jumps")) for c in contract_results]
    )
    all_options.sort(key=lambda x: x[1])

    cheapest_src, cheapest_price, cheapest_station, cheapest_jumps = all_options[0]

    print(f"\n{'='*80}")
    print(f"✅ RECOMMENDATION")
    print(f"{'='*80}")
    print(f"   Cheapest: {format_isk(cheapest_price)} ISK  [{cheapest_src.upper()}]")
    print(f"   At:       {cheapest_station}")
    if cheapest_jumps is not None:
        print(f"   Distance: {cheapest_jumps} jumps from your current location")
    print(f"\n   💡 BPOs can be researched to ME10/TE20 — reduces material waste")
    print(f"      and build time. BPCs cannot be researched.")
    if not args.contracts:
        print(f"      Run with --contracts to also search the public contract market.")


if __name__ == "__main__":
    main()
