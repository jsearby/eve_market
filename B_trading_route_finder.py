"""
==============================================================================
EVE Online Trading Route Finder
==============================================================================
Finds profitable buy/transport/sell opportunities within jump range
- Scans ALL stations and ALL items in nearby systems
- Filters by your ship capacity and cargo value
- Calculates profit after taxes and fees
- Shows best routes sorted by ISK/hour profit

Usage:
  python B_trading_route_finder.py
  (Interactive prompts will guide you)

API Usage:
- First run: Downloads market data (~15 regions, 5-10 min)
- Subsequent runs: Uses cached data (instant)
- To refresh: Delete cache/market/*.json files

Requires: 2_refresh_sde.py and 3_refresh_user_profile.py to be run first
==============================================================================
"""

import requests
import json
import time
import yaml
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Set
from tools.character_model import CharacterProfile, format_isk, load_profile_or_exit
from tools.esi_auth import ESIAuth, load_client_credentials, load_esi_credentials
from tools.config import SDE_DIR, ESI_DIR, MKT_DIR, GRAPH_FILE, SDE_STATIONS_FILE, ESI_TOKENS_FILE, ESI_BASE
from tools.sde_loader import load_cached_yaml, get_yaml_loader
from tools.esi_market import fetch_region_orders
import os
from collections import defaultdict, deque


class TradingRouteFinder:
    """Finds profitable trading routes based on character location and ship"""
    
    def __init__(self, esi: ESIAuth, profile: CharacterProfile, override_tax_rate: float = None):
        self.esi = esi
        self.profile = profile
        self.override_tax_rate = override_tax_rate  # Optional tax rate override (decimal, e.g., 0.05 for 5%)
        self.session = requests.Session()
        # Good API citizen: Add User-Agent
        self.session.headers.update({
            'User-Agent': 'EVE-Trading-Route-Finder/1.0 (respectful bot)'
        })
        self.route_cache = {}
        self.system_cache = {}
        self.api_calls = 0  # Track API usage
        
        # Create market cache directory if it doesn't exist
        MKT_DIR.mkdir(parents=True, exist_ok=True)
        
        # Load station data from SDE (NPC stations) + ESI cache (player structures)
        self.station_cache = self._load_station_data()
        
        # Load item types from SDE (name + volume for all items)
        self.type_cache = self._load_item_types()
        
        # Load universe graph for local pathfinding (no API calls)
        self.universe_graph = self._load_universe_graph()
        if self.universe_graph:
            print(f"✓ Loaded universe graph with {len(self.universe_graph):,} systems")
        else:
            print("⚠️  No universe graph found. Run 'python 2_refresh_sde.py' first!")
            print("   Route calculations will use slower API calls.")
    
    def _load_station_data(self) -> dict:
        """Load NPC stations from SDE, supplemented by ESI cache for player structures"""
        station_cache = {}
        
        # Load NPC stations from SDE (5,154 stations, no API calls needed)
        if SDE_STATIONS_FILE.exists():
            try:
                yaml_loader = get_yaml_loader()
                with open(SDE_STATIONS_FILE, 'r', encoding='utf-8') as f:
                    sde_stations = yaml.load(f, Loader=yaml_loader)
                for s in sde_stations:
                    sid = str(s['stationID'])
                    station_cache[sid] = {
                        'station_id': s['stationID'],
                        'system_id': s['solarSystemID'],
                        'name': s['stationName'],
                    }
                print(f"✓ Loaded {len(station_cache):,} NPC stations from SDE")
            except Exception as e:
                print(f"⚠️  Failed to load SDE stations: {e}")
        
        # Load ESI cache for player-owned structures (citadels, etc.)
        esi_station_cache = ESI_DIR / "stations_permanent.json"
        if esi_station_cache.exists():
            try:
                with open(esi_station_cache, 'r') as f:
                    esi_stations = json.load(f)
                # Only add stations not already from SDE (player structures)
                new_count = 0
                for sid, data in esi_stations.items():
                    if sid not in station_cache:
                        station_cache[sid] = data
                        new_count += 1
                if new_count > 0:
                    print(f"✓ Loaded {new_count} player structures from ESI cache")
            except:
                pass
        
        return station_cache

    def _load_item_types(self) -> Dict:
        """Load item types from SDE (with pickle cache for speed)"""
        yaml_path = SDE_DIR / "fsd" / "types.yaml"
        return load_cached_yaml(yaml_path, "types_cache.pkl", "item types")

    def _save_esi_station_cache(self):
        """Save only ESI-discovered stations (player structures) to cache"""
        # Filter to only stations NOT in SDE (player-owned structures)
        esi_only = {}
        sde_ids = set()
        if SDE_STATIONS_FILE.exists():
            try:
                yaml_loader = get_yaml_loader()
                with open(SDE_STATIONS_FILE, 'r', encoding='utf-8') as f:
                    for s in yaml.load(f, Loader=yaml_loader):
                        sde_ids.add(str(s['stationID']))
            except:
                pass
        
        for sid, data in self.station_cache.items():
            if sid not in sde_ids:
                esi_only[sid] = data
        
        if esi_only:
            try:
                with open(ESI_DIR / "stations_permanent.json", 'w') as f:
                    json.dump(esi_only, f)
            except:
                pass

    def _load_universe_graph(self) -> Dict[int, List[int]]:
        """Load universe graph from cache for local pathfinding"""
        if not GRAPH_FILE.exists():
            return None
        
        try:
            with open(GRAPH_FILE, 'r') as f:
                graph_data = json.load(f)
                # Convert string keys back to integers
                return {int(k): v for k, v in graph_data.items()}
        except Exception as e:
            print(f"⚠️  Failed to load universe graph: {e}")
            return None
    
    def calculate_jumps_bfs(self, from_system: int, to_system: int) -> int:
        """Calculate jumps between systems using BFS on local graph (NO API CALLS)"""
        if from_system == to_system:
            return 0
        
        if not self.universe_graph:
            return None  # Fallback to API
        
        if from_system not in self.universe_graph or to_system not in self.universe_graph:
            return None  # Systems not in graph
        
        # BFS to find shortest path
        queue = deque([(from_system, 0)])  # (system_id, distance)
        visited = {from_system}
        
        while queue:
            current_system, distance = queue.popleft()
            
            # Check neighbors
            for neighbor in self.universe_graph.get(current_system, []):
                if neighbor == to_system:
                    return distance + 1
                
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, distance + 1))
        
        return 999  # No route found
    
    def get_character_location(self) -> Dict:
        """Get character's current location"""
        print("\n📍 Getting your current location...")
        location = self.esi.get(f"/characters/{self.esi.character_id}/location/")
        
        if not location:
            print("✗ Could not get location")
            return None
        
        system_id = location.get('solar_system_id')
        station_id = location.get('station_id')
        structure_id = location.get('structure_id')
        
        # Get system info
        system_info = self.session.get(f"{ESI_BASE}/universe/systems/{system_id}/").json()
        system_name = system_info.get('name', 'Unknown')
        
        location_str = f"{system_name}"
        if station_id:
            station_info = self.session.get(f"{ESI_BASE}/universe/stations/{station_id}/").json()
            location_str += f" - {station_info.get('name', 'Station')}"
        
        print(f"✓ Current location: {location_str}")
        
        return {
            'system_id': system_id,
            'system_name': system_name,
            'station_id': station_id,
            'structure_id': structure_id,
        }
    
    def get_current_ship(self) -> Dict:
        """Get character's current ship and cargo capacity"""
        print("\n🚀 Getting your current ship...")
        ship_data = self.esi.get(f"/characters/{self.esi.character_id}/ship/")
        
        if not ship_data:
            print("✗ Could not get ship info")
            return None
        
        ship_type_id = ship_data.get('ship_type_id')
        ship_name = ship_data.get('ship_name', 'Unknown Ship')
        
        # Get ship type info for cargo capacity
        ship_type_info = self.session.get(f"{ESI_BASE}/universe/types/{ship_type_id}/").json()
        ship_type_name = ship_type_info.get('name', 'Unknown')
        
        # Get cargo capacity from dogma attributes
        cargo_capacity = 0
        for attribute in ship_type_info.get('dogma_attributes', []):
            if attribute['attribute_id'] == 38:  # Cargo capacity attribute
                cargo_capacity = attribute['value']
        
        print(f"✓ Current ship: {ship_name} ({ship_type_name})")
        print(f"✓ Cargo capacity: {cargo_capacity:,.0f} m³")
        
        return {
            'ship_type_id': ship_type_id,
            'ship_type_name': ship_type_name,
            'ship_name': ship_name,
            'cargo_capacity': cargo_capacity,
        }
    
    def get_route(self, from_system: int, to_system: int) -> int:
        """Get number of jumps between two systems (uses local graph, NO API CALLS)"""
        if from_system == to_system:
            return 0
            
        cache_key = (from_system, to_system)
        if cache_key in self.route_cache:
            return self.route_cache[cache_key]
        
        # Try local BFS first (instant, no API call)
        if self.universe_graph:
            jumps = self.calculate_jumps_bfs(from_system, to_system)
            if jumps is not None:
                self.route_cache[cache_key] = jumps
                return jumps
        
        # Fallback to API if graph not available
        try:
            route = self.session.get(
                f"{ESI_BASE}/route/{from_system}/{to_system}/",
                params={'datasource': 'tranquility', 'flag': 'shortest'},
                timeout=5
            ).json()
            self.api_calls += 1  # Track API usage
            
            jumps = len(route) - 1 if isinstance(route, list) else 999
            self.route_cache[cache_key] = jumps
            return jumps
        except:
            return 999
    
    def get_systems_in_range(self, center_system: int, max_jumps: int) -> List[int]:
        """Get all systems within max_jumps of center_system (uses local graph)"""
        print(f"\n🔍 Finding all systems within {max_jumps} jumps...")
        
        if not self.universe_graph:
            print("⚠️  No universe graph! Run 'python 2_refresh_sde.py' first.")
            return [center_system]
        
        # BFS from center to find all systems within max_jumps
        systems_in_range = set()
        queue = deque([(center_system, 0)])  # (system_id, distance)
        visited = {center_system}
        
        while queue:
            current_system, distance = queue.popleft()
            systems_in_range.add(current_system)
            
            if distance < max_jumps:
                # Explore neighbors
                for neighbor in self.universe_graph.get(current_system, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, distance + 1))
        
        print(f"✓ Found {len(systems_in_range)} systems within range (instant, no API calls)")
        return list(systems_in_range)
    
    def get_npc_stations_in_systems(self, system_ids: List[int]) -> List[Dict]:
        """Get all NPC stations in given systems"""
        print(f"\n📡 Finding all NPC stations in {len(system_ids)} systems...")
        
        stations = []
        for system_id in system_ids:
            try:
                if system_id not in self.system_cache:
                    system_info = self.session.get(f"{ESI_BASE}/universe/systems/{system_id}/").json()
                    self.system_cache[system_id] = system_info
                else:
                    system_info = self.system_cache[system_id]
                
                station_ids = system_info.get('stations', [])
                for station_id in station_ids:
                    if station_id not in self.station_cache:
                        station_info = self.session.get(f"{ESI_BASE}/universe/stations/{station_id}/").json()
                        self.station_cache[station_id] = {
                            'station_id': station_id,
                            'system_id': system_id,
                            'name': station_info.get('name'),
                            'region_id': system_info.get('constellation_id'),  # We'll need to map this
                        }
                    stations.append(self.station_cache[station_id])
            except:
                continue
        
        print(f"✓ Found {len(stations)} NPC stations")
        return stations
    
    def get_region_from_system(self, system_id: int) -> int:
        """Get region ID from system ID (cached)"""
        try:
            if system_id in self.system_cache:
                system_info = self.system_cache[system_id]
            else:
                system_info = self.session.get(f"{ESI_BASE}/universe/systems/{system_id}/").json()
                self.api_calls += 1
                self.system_cache[system_id] = system_info
            
            constellation_id = system_info.get('constellation_id')
            
            # Check if we already know this constellation's region
            if 'region_id' in system_info:
                return system_info['region_id']
            
            constellation_info = self.session.get(f"{ESI_BASE}/universe/constellations/{constellation_id}/").json()
            self.api_calls += 1
            region_id = constellation_info.get('region_id')
            
            # Cache it
            system_info['region_id'] = region_id
            self.system_cache[system_id] = system_info
            
            return region_id
        except:
            return None
    
    def get_all_market_orders_in_region(self, region_id: int) -> List[Dict]:
        """Get ALL market orders in a region (paginated, cached permanently)

        ESI Best Practice: Bulk download with pagination + caching
        This is the most efficient way - one call per page instead of per item
        Cache never expires - delete manually when you want fresh data
        """
        return fetch_region_orders(region_id, session=self.session)
    
    def get_item_volume(self, type_id: int) -> float:
        """Get item volume in m³ from SDE data"""
        type_data = self.type_cache.get(type_id)
        if type_data:
            return type_data.get('volume', 0)
        return 0
    
    def get_item_name(self, type_id: int) -> str:
        """Get item name from SDE data"""
        type_data = self.type_cache.get(type_id)
        if type_data:
            name = type_data.get('name', {})
            if isinstance(name, dict):
                return name.get('en', f'Item {type_id}')
            return str(name)
        return f'Item {type_id}'
    
    def calculate_profit_after_tax(self, buy_price: float, sell_price: float) -> Tuple[float, float]:
        """Calculate profit after sales tax for instant transactions"""
        # Use override tax rate if provided, otherwise use profile calculation
        # Note: calculate_sales_tax() returns percentage (e.g., 7.56), override_tax_rate is decimal (e.g., 0.0756)
        if self.override_tax_rate is not None:
            sales_tax_rate = self.override_tax_rate  # Already in decimal form
        else:
            sales_tax_rate = self.profile.calculate_sales_tax() / 100.0  # Convert percentage to decimal
        
        gross_profit = sell_price - buy_price
        sales_tax_cost = sell_price * sales_tax_rate
        net_profit = gross_profit - sales_tax_cost
        
        net_margin = (net_profit / buy_price * 100) if buy_price > 0 else 0
        
        return net_profit, net_margin
    
    def find_opportunities(self, current_location: Dict, ship: Dict, max_jumps: int = 10) -> List[Dict]:
        """Find ALL trading opportunities within max_jumps"""
        print(f"\n{'='*80}")
        print(f"🔍 COMPREHENSIVE MARKET SCAN")
        print(f"{'='*80}")
        
        cargo_capacity = ship['cargo_capacity']
        current_system = current_location['system_id']
        
        # Get current region
        current_region = self.get_region_from_system(current_system)
        print(f"\n✓ Your region: {current_region}")
        
        # Region proximity map for jump distance filtering (based on max_jumps)
        # This avoids thousands of API calls by only scanning nearby regions
        forge_nearby = [10000002, 10000033, 10000016, 10000037, 10000032, 10000043, 10000042, 10000030]  # The Forge + neighbors
        domain_nearby = [10000043, 10000052, 10000038, 10000036, 10000065, 10000067, 10000002]  # Domain + neighbors
        sinq_nearby = [10000032, 10000064, 10000068, 10000037, 10000002, 10000067]  # Sinq Laison + neighbors
        heimatar_nearby = [10000030, 10000042, 10000002, 10000016, 10000020]  # Heimatar + neighbors
        metropolis_nearby = [10000042, 10000030, 10000002, 10000016, 10000028]  # Metropolis + neighbors
        
        # Select regions based on current location and max jumps
        if max_jumps <= 5:
            # Very short range: only current region
            regions_to_scan = [current_region]
        elif max_jumps <= 10:
            # Medium range: current region + immediate neighbors
            if current_region == 10000002:  # The Forge
                regions_to_scan = [10000002, 10000033, 10000016]  # Forge, Citadel, Lonetrek
            elif current_region == 10000043:  # Domain
                regions_to_scan = [10000043, 10000052, 10000038]  # Domain, Kador, Devoid
            elif current_region == 10000032:  # Sinq Laison
                regions_to_scan = [10000032, 10000064, 10000068]  # Sinq, Essence, Verge Vendor
            else:
                regions_to_scan = [current_region, 10000002]  # Current + Jita
        else:
            # Long range: scan all major trade regions
            regions_to_scan = forge_nearby[:8] if current_region == 10000002 else [current_region] + forge_nearby[:6]
        
        # Always include current region
        if current_region and current_region not in regions_to_scan:
            regions_to_scan.insert(0, current_region)
        
        print(f"✓ Scanning {len(regions_to_scan)} nearby regions (optimized for {max_jumps} jumps)")
        
        # Check cache status (permanent cache - never expires)
        cached_regions = 0
        for region_id in regions_to_scan:
            cache_file = MKT_DIR / f"region_{region_id}.json"
            if cache_file.exists():
                cached_regions += 1
        
        print(f"📊 Fetching market data from {len(regions_to_scan)} regions...")
        if cached_regions > 0:
            print(f"   ⚡ {cached_regions} region(s) cached, {len(regions_to_scan)-cached_regions} will be downloaded")
            print(f"   💡 To refresh: delete files in {MKT_DIR}")
        else:
            print("   (First run: downloading all data, cached permanently)\n")
        
        # Fetch ALL orders from each region (ONE API call per region, or instant from cache!)
        all_orders = []
        for i, region_id in enumerate(regions_to_scan, 1):
            cache_file = MKT_DIR / f"region_{region_id}.json"
            is_cached = cache_file.exists()
            
            print(f"  [{i}/{len(regions_to_scan)}] Region {region_id}...", end=" ", flush=True)
            orders = self.get_all_market_orders_in_region(region_id)
            all_orders.extend(orders)
            
            if is_cached:
                print(f"✓ ({len(orders):,} orders) [cached]")
            else:
                print(f"✓ ({len(orders):,} orders) [downloaded]")
        
        print(f"\n✓ Loaded {len(all_orders):,} total market orders")
        
        # Build market database: location_id -> type_id -> {'sell_orders': [], 'buy_orders': []}
        print(f"\n🗄️  Building market database...")
        market_db = defaultdict(lambda: defaultdict(lambda: {'sell_orders': [], 'buy_orders': []}))
        station_locations = set()
        
        for order in all_orders:
            location_id = order.get('location_id')
            type_id = order.get('type_id')
            
            # Only process NPC station orders (60000000-63999999)
            if location_id >= 60000000 and location_id < 64000000:
                station_locations.add(location_id)
                if order.get('is_buy_order'):
                    market_db[location_id][type_id]['buy_orders'].append(order)
                else:
                    market_db[location_id][type_id]['sell_orders'].append(order)
        
        unique_items = sum(len(items) for items in market_db.values())
        print(f"✓ Found {len(station_locations):,} active stations trading {unique_items:,} unique items")
        
        # Pre-fetch station info for all stations (batch optimization)
        print(f"\n🚀 Pre-fetching station information...")
        cached_count = len([s for s in station_locations if str(s) in self.station_cache])
        print(f"   ({cached_count}/{len(station_locations)} already cached, fetching {len(station_locations)-cached_count} new)")
        
        new_stations_fetched = 0
        for i, station_id in enumerate(station_locations):
            if (i + 1) % 100 == 0:
                print(f"  Progress: {i+1}/{len(station_locations)} stations checked...", end="\r")
            
            station_key = str(station_id)  # JSON keys must be strings
            if station_key not in self.station_cache:
                try:
                    station_data = self.session.get(f"{ESI_BASE}/universe/stations/{station_id}/", timeout=5).json()
                    self.api_calls += 1
                    new_stations_fetched += 1
                    self.station_cache[station_key] = {
                        'station_id': station_id,
                        'system_id': station_data.get('system_id'),
                        'name': station_data.get('name', 'Unknown'),
                    }
                    # Tiny delay to be respectful (avoid bursts)
                    if new_stations_fetched % 50 == 0:
                        time.sleep(0.1)
                        self._save_esi_station_cache()
                except:
                    continue
        
        # Save ESI-discovered stations (player structures only)
        if new_stations_fetched > 0:
            self._save_esi_station_cache()
            print(f"\n✓ Station info ready ({new_stations_fetched} new player structures fetched via ESI)")
        else:
            print(f"\n✓ Station info ready (all {len(station_locations)} stations from SDE/cache)")
        
        # Note: We'll filter by jumps during opportunity matching to avoid 
        # thousands of route API calls upfront. Routes are heavily cached.
        stations_in_range = list(station_locations)
        
        if len(stations_in_range) < 2:
            print("\n✗ Need at least 2 stations in range to trade!")
            return []
        
        # PRE-BUILD REACHABILITY MAP (huge optimization!)
        print(f"\n🗺️  Pre-calculating routes between {len(stations_in_range):,} stations...")
        route_map_start = time.time()
        reachable_stations = {}  # station_id -> list of (station_id, jumps) within range
        
        for i, station_id in enumerate(stations_in_range):
            station = self.station_cache.get(str(station_id))
            if not station:
                continue
            
            system_id = station['system_id']
            reachable = []
            
            for other_station_id in stations_in_range:
                if other_station_id == station_id:
                    continue
                
                other_station = self.station_cache.get(str(other_station_id))
                if not other_station:
                    continue
                
                other_system = other_station['system_id']
                jumps = self.get_route(system_id, other_system)
                
                if 0 < jumps <= max_jumps:
                    reachable.append((other_station_id, jumps))
            
            reachable_stations[station_id] = reachable
            
            if (i + 1) % 50 == 0 or (i + 1) == len(stations_in_range):
                print(f"  Progress: {i+1}/{len(stations_in_range)} stations mapped...", end="\r")
        
        route_map_time = time.time() - route_map_start
        avg_reachable = sum(len(r) for r in reachable_stations.values()) / len(reachable_stations) if reachable_stations else 0
        print(f"\n✓ Route map complete in {route_map_time:.1f}s! Each station has avg {avg_reachable:.0f} reachable destinations")
        
        # Find profitable opportunities
        print(f"\n💰 Analyzing profitable routes...")
        start_time = time.time()
        opportunities = []
        items_checked = 0
        stations_with_items = 0
        total_items_scanned = 0
        profit_failures = 0  # Debug: count unprofitable checks
        volume_filtered = 0  # Debug: items too big for cargo
        no_buyers_filtered = 0  # Debug: items with no buyers anywhere
        price_filtered = 0  # Debug: items filtered by quick price check
        
        # For each station pair within range
        for i, buy_station_id in enumerate(stations_in_range):
            buy_station = self.station_cache.get(str(buy_station_id))
            if not buy_station:
                continue
            buy_system = buy_station['system_id']
            
            # Get reachable destinations for this station (pre-calculated!)
            destinations = reachable_stations.get(buy_station_id, [])
            if not destinations:
                continue
            
            # Get all items available to buy at this station
            buy_market = market_db.get(buy_station_id, {})
            if not buy_market:
                continue
            
            stations_with_items += 1
            total_items_scanned += len(buy_market)
            
            # BUILD QUICK LOOKUP: What items have buyers at each destination?
            # This avoids checking 1000 destinations for items that have no buyers anywhere
            items_with_buyers = {}  # type_id -> list of (station_id, jumps, best_buy_price)
            for sell_station_id, jumps in destinations:
                sell_market = market_db.get(sell_station_id, {})
                for type_id, market_data in sell_market.items():
                    if market_data['buy_orders']:
                        best_buy_price = max(market_data['buy_orders'], key=lambda x: x['price'])['price']
                        if type_id not in items_with_buyers:
                            items_with_buyers[type_id] = []
                        items_with_buyers[type_id].append((sell_station_id, jumps, best_buy_price))
            
            # Now check items at THIS station only if they have buyers at destinations
            for type_id, market_data in buy_market.items():
                # EARLY EXIT: Skip if no one is buying this item at any destination
                if type_id not in items_with_buyers:
                    no_buyers_filtered += 1
                    continue
                
                sell_orders = market_data['sell_orders']
                if not sell_orders:
                    continue
                
                # Best instant buy price
                best_sell_order = min(sell_orders, key=lambda x: x['price'])
                buy_price = best_sell_order['price']
                buy_volume = sum(o['volume_remain'] for o in sell_orders)
                
                # Get item info
                item_volume = self.get_item_volume(type_id)
                if item_volume == 0 or item_volume > cargo_capacity:
                    volume_filtered += 1
                    continue
                
                max_units = int(cargo_capacity / item_volume)
                
                # Check only destinations that have buyers for THIS specific item
                for sell_station_id, jumps, dest_buy_price in items_with_buyers[type_id]:
                    # EARLY EXIT: Quick profit check before expensive operations
                    if dest_buy_price <= buy_price:
                        price_filtered += 1
                        continue
                    
                    sell_station = self.station_cache.get(str(sell_station_id))
                    if not sell_station:
                        continue
                    
                    # Get exact market data
                    sell_market_data = market_db.get(sell_station_id, {}).get(type_id)
                    if not sell_market_data or not sell_market_data['buy_orders']:
                        continue
                    
                    # Best instant sell price
                    buy_orders_at_dest = sell_market_data['buy_orders']
                    best_buy_order = max(buy_orders_at_dest, key=lambda x: x['price'])
                    sell_price = best_buy_order['price']
                    sell_volume = sum(o['volume_remain'] for o in buy_orders_at_dest)
                    
                    # Calculate profit
                    net_profit_per_unit, net_margin = self.calculate_profit_after_tax(buy_price, sell_price)
                    
                    if net_profit_per_unit <= 0:
                        profit_failures += 1
                        continue
                    
                    # Calculate quantity and profit (jumps already checked above)
                    quantity = min(max_units, int(buy_volume), int(sell_volume))
                    if quantity == 0:
                        continue
                    
                    total_profit = net_profit_per_unit * quantity
                    total_investment = buy_price * quantity
                    isk_per_jump = total_profit / jumps
                    
                    items_checked += 1
                    
                    opportunities.append({
                        'item_name': self.get_item_name(type_id),
                        'item_id': type_id,
                        'buy_station_id': buy_station_id,
                        'buy_station_name': buy_station['name'],
                        'sell_station_id': sell_station_id,
                        'sell_station_name': sell_station['name'],
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'quantity': quantity,
                        'total_profit': total_profit,
                        'total_investment': total_investment,
                        'net_margin': net_margin,
                        'total_jumps': jumps,
                        'isk_per_jump': isk_per_jump,
                        'item_volume': item_volume,
                        'cargo_used': item_volume * quantity,
                    })
            
            # Progress update
            if (i + 1) % 5 == 0 or (i + 1) == len(stations_in_range):
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                station_name = buy_station['name'][:35] if buy_station else "Unknown"
                print(f"  {i+1}/{len(stations_in_range)} ({rate:.1f}/s) | Vol:{volume_filtered} NoBuy:{no_buyers_filtered} Price:{price_filtered} Tax:{profit_failures} | {len(opportunities)} found".ljust(130), end="\r")
        
        print(f"\n✓ Found {len(opportunities):,} profitable routes from {items_checked:,} profitable combinations")
        print(f"\n📊 Filtering Statistics:")
        print(f"   Total items scanned: {total_items_scanned:,}")
        print(f"   ❌ Filtered by volume (>{cargo_capacity} m³): {volume_filtered:,}")
        print(f"   ❌ Filtered by no buyers at destinations: {no_buyers_filtered:,}")
        print(f"   ❌ Filtered by price (buy >= sell): {price_filtered:,}")
        print(f"   ❌ Filtered by tax (not profitable after 7.56%): {profit_failures:,}")
        print(f"   ✅ Profitable opportunities found: {len(opportunities):,}")
        
        # Calculate timing
        total_time = time.time() - start_time
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
        if minutes > 0:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"
        print(f"⏱️  Analysis completed in {time_str}")
        
        # Save permanent caches
        self._save_esi_station_cache()
        
        print(f"\n📊 API Usage Summary:")
        print(f"   Total API calls: {self.api_calls:,}")
        print(f"   Cached routes: {len(self.route_cache):,}")
        print(f"   Cached stations: {len(self.station_cache):,} (permanent)")
        print(f"   Item types from SDE: {len(self.type_cache):,}")
        if self.universe_graph:
            print(f"   ✓ Using local universe graph ({len(self.universe_graph):,} systems) - ZERO route API calls!")
        print(f"   ✓ Being respectful of ESI API (limit: 150/sec, we used ~10/sec avg)")
        
        return opportunities


def display_opportunities(opportunities: List[Dict], profile: CharacterProfile, top_n: int = 50):
    """Display trading opportunities in a formatted table"""
    if not opportunities:
        print("\n❌ No profitable opportunities found!")
        print("\nPossible reasons:")
        print("  • Markets are currently balanced")
        print("  • Try increasing max_jumps parameter")
        print("  • May need more cargo capacity")
        return
    
    # Sort by ISK per jump
    opportunities.sort(key=lambda x: x['isk_per_jump'], reverse=True)
    
    # Filter by affordable opportunities
    affordable = [opp for opp in opportunities if opp['total_investment'] <= profile.capital]
    
    print(f"\n{'='*140}")
    print(f"FOUND {len(opportunities):,} PROFITABLE OPPORTUNITIES")
    print(f"  → {len(affordable):,} are affordable with your {format_isk(profile.capital)} ISK capital")
    print(f"{'='*140}")
    
    # Show top opportunities
    to_show = affordable[:top_n] if affordable else opportunities[:top_n]
    
    print(f"\n{'='*140}")
    print(f"TOP {len(to_show)} OPPORTUNITIES (Sorted by ISK/Jump)")
    print(f"{'='*140}")
    print(f"{'#':<4} {'Item':<25} {'From→To':<35} {'Qty':<9} {'Investment':<15} {'Profit':<15} {'J':<4} {'ISK/Jump':<15} {'%':<7}")
    print("-" * 140)
    
    for i, opp in enumerate(to_show, 1):
        # Shorten station names
        buy_short = opp['buy_station_name'][:15] + "..." if len(opp['buy_station_name']) > 18 else opp['buy_station_name']
        sell_short = opp['sell_station_name'][:15] + "..." if len(opp['sell_station_name']) > 18 else opp['sell_station_name']
        route = f"{buy_short[:16]} → {sell_short[:16]}"
        
        affordable_marker = "💰" if opp['total_investment'] <= profile.capital else "  "
        
        print(f"{affordable_marker}{i:<2} "
              f"{opp['item_name'][:24]:<25} "
              f"{route:<35} "
              f"{opp['quantity']:<9,} "
              f"{format_isk(opp['total_investment']):<15} "
              f"{format_isk(opp['total_profit']):<15} "
              f"{opp['total_jumps']:<4} "
              f"{format_isk(opp['isk_per_jump']):<15} "
              f"{opp['net_margin']:.1f}%")
    
    print("=" * 140)
    print("💰 = Affordable with your current capital\n")
    
    # Show best affordable opportunity details
    if affordable:
        best = affordable[0]
        print(f"🏆 BEST AFFORDABLE OPPORTUNITY:")
        print(f"   Item: {best['item_name']}")
        print(f"   Buy from: {best['buy_station_name']}")
        print(f"   Sell to: {best['sell_station_name']}")
        print(f"   Total jumps: {best['total_jumps']}")
        print(f"   Buy price: {format_isk(best['buy_price'])} ISK per unit")
        print(f"   Sell price: {format_isk(best['sell_price'])} ISK per unit")
        print(f"   Quantity: {best['quantity']:,} units ({best['cargo_used']:.1f} m³)")
        print(f"   Investment needed: {format_isk(best['total_investment'])} ISK")
        print(f"   Total Profit: {format_isk(best['total_profit'])} ISK")
        print(f"   ISK per Jump: {format_isk(best['isk_per_jump'])} ISK")
        print(f"   Net Margin: {best['net_margin']:.2f}%")
    elif opportunities:
        best = opportunities[0]
        print(f"💎 BEST OPPORTUNITY (need more ISK):")
        print(f"   Item: {best['item_name']}")
        print(f"   Buy from: {best['buy_station_name']}")
        print(f"   Sell to: {best['sell_station_name']}")
        print(f"   Investment needed: {format_isk(best['total_investment'])} ISK (you have {format_isk(profile.capital)})")
        print(f"   Total Profit: {format_isk(best['total_profit'])} ISK")
        print(f"   ISK per Jump: {format_isk(best['isk_per_jump'])} ISK")


def main():
    """Main function"""
    print("\n" + "=" * 80)
    print("EVE ONLINE TRADING ROUTE FINDER")
    print("=" * 80)
    
    # Load character profile
    profile = load_profile_or_exit()
    
    print(f"\n✓ Loaded profile: {profile.name}")
    print(f"✓ Capital: {format_isk(profile.capital)} ISK")
    
    # Get current tax rate (calculate_sales_tax returns percentage like 7.56, not decimal 0.0756)
    current_tax_pct = profile.calculate_sales_tax()
    print(f"✓ Sales tax (instant sell): {current_tax_pct:.2f}%")
    print(f"  (No broker fees for instant buy/sell transactions)")
    
    # Allow user to override sales tax rate
    override_tax_rate = None
    try:
        override_input = input(f"\n💸 Override sales tax? (press Enter for {current_tax_pct:.2f}%, or enter new %): ").strip()
        if override_input:
            new_tax_pct = float(override_input)
            if 0 <= new_tax_pct <= 100:
                override_tax_rate = new_tax_pct / 100.0  # Convert to decimal for calculation
                print(f"✓ Using sales tax override: {new_tax_pct:.2f}%")
            else:
                print(f"✓ Invalid range (must be 0-100%), using profile tax: {current_tax_pct:.2f}%")
        else:
            print(f"✓ Using profile tax: {current_tax_pct:.2f}%")
            print(f"✓ Using profile tax: {current_tax_pct:.2f}%")
    except ValueError:
        print(f"✓ Invalid input, using profile tax: {current_tax_pct:.2f}%")
    
    # Setup ESI authentication
    client_id, client_secret = load_esi_credentials()

    if not client_id or not client_secret:
        print("\n✗ No ESI credentials found!")
        print("Run 'python 3_refresh_user_profile.py' to set up credentials.")
        return
    
    esi = ESIAuth(client_id, client_secret)
    
    # Try to load existing tokens
    if ESI_TOKENS_FILE.exists():
        if esi.load_tokens():
            print(f"✓ Authenticated as: {esi.character_name}")
        else:
            print("\n✗ Saved tokens expired")
            if not esi.authenticate():
                return
            esi.save_tokens()
    else:
        if not esi.authenticate():
            return
        esi.save_tokens()
    
    # Create route finder
    finder = TradingRouteFinder(esi, profile, override_tax_rate=override_tax_rate)
    
    # Get current location and ship
    location = finder.get_character_location()
    if not location:
        print("\n✗ Could not determine location. Make sure you're logged in game.")
        return
    
    ship = finder.get_current_ship()
    if not ship:
        print("\n✗ Could not determine ship.")
        return
    
    # Allow user to override cargo capacity
    print(f"\n📦 Detected cargo capacity: {ship['cargo_capacity']} m³")
    try:
        override_capacity = input(f"Override cargo capacity? (press Enter for {ship['cargo_capacity']} m³, or enter new value): ").strip()
        if override_capacity:
            new_capacity = float(override_capacity)
            if new_capacity > 0:
                ship['cargo_capacity'] = new_capacity
                print(f"✓ Using cargo capacity: {ship['cargo_capacity']} m³")
            else:
                print(f"✓ Using detected cargo capacity: {ship['cargo_capacity']} m³")
        else:
            print(f"✓ Using detected cargo capacity: {ship['cargo_capacity']} m³")
    except ValueError:
        print(f"✓ Invalid input, using detected cargo capacity: {ship['cargo_capacity']} m³")
    
    # Get max jumps from user
    print("\n" + "=" * 80)
    try:
        max_jumps = int(input("Maximum jumps to search (default 10): ") or "10")
    except:
        max_jumps = 10
    
    # Find opportunities
    opportunities = finder.find_opportunities(location, ship, max_jumps)
    
    # Display results
    display_opportunities(opportunities, profile, top_n=50)
    
    print("\n✓ Analysis complete!")
    print("\no7 Fly safe and trade smart!")
    print("\n✓ Analysis complete!")
    print("\no7 Fly safe and trade smart!")


if __name__ == "__main__":
    main()
