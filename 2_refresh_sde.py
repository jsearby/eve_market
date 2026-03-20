"""
==============================================================================
STEP 2: EVE Static Data Export (SDE) Setup
==============================================================================
Downloads CCP's official EVE Online game data and builds universe graph
- Downloads ~500MB from CCP (blueprints, items, systems, etc.)
- Extracts and organizes the data
- Builds optimized jump route graph for trading route finder
Run this ONCE when first setting up (or after major EVE expansions)
Estimated time: 5-10 minutes
==============================================================================
"""

import requests
import zipfile
import os
import shutil
import time
import yaml
import json
from pathlib import Path
from typing import Dict, List
from collections import defaultdict, Counter
from tools.config import SDE_DIR, MKT_DIR, GRAPH_FILE
from tools.sde_loader import find_sde_file

SDE_URL = "https://eve-static-data-export.s3-eu-west-1.amazonaws.com/tranquility/sde.zip"
UNIVERSE_DIR = SDE_DIR / "universe"
GRAPH_OUTPUT = GRAPH_FILE

# ==============================================================================
# PART 1: SDE Download
# ==============================================================================

def download_sde():
    """Download and extract latest SDE from CCP's official source"""
    print("🌐 EVE Online SDE Downloader")
    print("=" * 70)
    
    # Check if SDE already exists
    if SDE_DIR.exists():
        print(f"\n⚠️  SDE directory already exists: {SDE_DIR}")
        response = input("Re-download? This will take ~5-10 minutes. (y/N): ")
        if response.lower() != 'y':
            print("✓ Using existing SDE data.")
            return True
        print("\n🔄 Re-downloading SDE...")
        shutil.rmtree(SDE_DIR)
    
    # Create directories
    SDE_DIR.mkdir(exist_ok=True)
    MKT_DIR.mkdir(exist_ok=True)
    
    zip_file = "sde.zip"
    
    try:
        # Download SDE
        print(f"\n📥 Downloading SDE from CCP...")
        print(f"   Source: {SDE_URL}")
        print(f"   Size: ~500 MB (this may take a few minutes)")
        
        response = requests.get(SDE_URL, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(zip_file, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        print(f"   Progress: {progress:.1f}% ({downloaded // (1024*1024)} MB)", end='\r')
        
        print(f"\n✓ Download complete: {os.path.getsize(zip_file) // (1024*1024)} MB")
        
        # Extract SDE
        print(f"\n📦 Extracting SDE data...")
        print(f"   This may take 2-3 minutes...")
        
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            all_files = zip_ref.namelist()
            print(f"   Extracting {len(all_files):,} files...")
            zip_ref.extractall(SDE_DIR)
        
        print(f"   ✓ Extracted all files")
        
        # Clean up zip file
        os.remove(zip_file)
        print(f"✓ Cleaned up temporary files")
        
        # Verify extracted files
        print(f"\n✔️  Verifying SDE data...")
        
        blueprints_file = find_sde_file("blueprints.yaml")
        types_file = find_sde_file("types.yaml")
        
        if blueprints_file and types_file:
            bp_size = blueprints_file.stat().st_size // (1024*1024)
            types_size = types_file.stat().st_size // (1024*1024)
            print(f"   ✓ blueprints.yaml: {bp_size} MB")
            print(f"   ✓ types.yaml: {types_size} MB")
        else:
            if not blueprints_file:
                print(f"   ✗ blueprints.yaml not found!")
            if not types_file:
                print(f"   ✗ types.yaml not found!")
            return False
        
        print(f"\n✓ SDE download complete!")
        print(f"📁 Data location: {SDE_DIR.absolute()}")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error downloading SDE: {e}")
        if os.path.exists(zip_file):
            os.remove(zip_file)
        return False

# ==============================================================================
# PART 2: Universe Graph Builder
# ==============================================================================

class UniverseGraphBuilder:
    def __init__(self):
        self.system_to_stargates = {}  # system_id -> list of stargate_ids in that system
        self.stargate_to_system = {}   # stargate_id -> system_id it's located in
        self.stargate_destinations = {} # stargate_id -> destination_stargate_id
        self.graph = defaultdict(list)  # system_id -> list of connected system_ids
        
    def build_graph_from_sde(self) -> Dict[int, List[int]]:
        """Build universe graph from SDE data"""
        print("\n" + "=" * 70)
        print("🌌 Building EVE Universe Graph from SDE Data...")
        print("=" * 70)
        
        # Step 1: Find all solarsystem.yaml files
        print("\n📡 Step 1: Scanning SDE universe directory...")
        solar_system_files = list(UNIVERSE_DIR.rglob("solarsystem.yaml"))
        print(f"✅ Found {len(solar_system_files):,} solar system files")
        
        # Show breakdown by directory
        dir_counts = Counter()
        for file in solar_system_files:
            parts = file.relative_to(UNIVERSE_DIR).parts
            if parts:
                dir_counts[parts[0]] += 1
        
        if dir_counts:
            print("   📂 Breakdown:")
            for dir_name, count in sorted(dir_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"      • {dir_name}: {count:,} systems")
        
        # Step 2: Parse all solar systems and extract stargate data
        print("\n🔗 Step 2: Extracting stargate connections...")
        self._parse_all_systems(solar_system_files)
        print(f"✅ Parsed {len(self.system_to_stargates):,} systems")
        print(f"✅ Found {len(self.stargate_destinations):,} stargate connections")
        
        # Step 3: Build adjacency graph
        print("\n🗺️  Step 3: Building system adjacency graph...")
        self._build_adjacency_graph()
        print(f"✅ Mapped {len(self.graph):,} systems with connections")
        
        # Step 4: Validate graph
        print("\n✔️  Step 4: Validating graph integrity...")
        self._validate_graph()
        
        # Step 5: Save to file
        print(f"\n💾 Step 5: Saving to {GRAPH_OUTPUT}...")
        self._save_graph()
        
        print("\n" + "=" * 70)
        print(f"🎉 Universe graph complete!")
        self._print_statistics()
        
        return dict(self.graph)
    
    def _parse_all_systems(self, solar_system_files: List[Path]):
        """Parse all solarsystem.yaml files and extract stargate data"""
        yaml_loader = yaml.CSafeLoader if hasattr(yaml, 'CSafeLoader') else yaml.SafeLoader
        
        systems_processed = 0
        for idx, system_file in enumerate(solar_system_files, 1):
            if idx % 500 == 0 or idx == len(solar_system_files):
                progress_pct = (idx / len(solar_system_files)) * 100
                print(f"  Progress: {idx:,}/{len(solar_system_files):,} files ({progress_pct:.1f}%)")
            
            try:
                with open(system_file, 'r', encoding='utf-8') as f:
                    system_data = yaml.load(f, Loader=yaml_loader)
                
                system_id = system_data.get('solarSystemID')
                if not system_id:
                    continue
                
                stargates = system_data.get('stargates', {})
                stargate_ids = []
                
                for stargate_id, stargate_data in stargates.items():
                    stargate_ids.append(stargate_id)
                    self.stargate_to_system[stargate_id] = system_id
                    
                    destination = stargate_data.get('destination')
                    if destination:
                        self.stargate_destinations[stargate_id] = destination
                
                self.system_to_stargates[system_id] = stargate_ids
                systems_processed += 1
                
            except Exception as e:
                continue
        
        print(f"  ✅ Successfully processed {systems_processed:,} systems")
    
    def _build_adjacency_graph(self):
        """Build adjacency list from stargate connections"""
        for system_id, stargate_ids in self.system_to_stargates.items():
            connected_systems = set()
            
            for stargate_id in stargate_ids:
                dest_stargate_id = self.stargate_destinations.get(stargate_id)
                if not dest_stargate_id:
                    continue
                
                dest_system_id = self.stargate_to_system.get(dest_stargate_id)
                if dest_system_id:
                    connected_systems.add(dest_system_id)
            
            self.graph[system_id] = sorted(list(connected_systems))
    
    def _validate_graph(self):
        """Validate graph consistency"""
        isolated_systems = []
        
        for system_id, neighbors in self.graph.items():
            if len(neighbors) == 0:
                isolated_systems.append(system_id)
        
        if isolated_systems:
            print(f"  ℹ️  Found {len(isolated_systems)} isolated systems (special systems)")
        
        print(f"  ✅ Graph validation complete")
    
    def _save_graph(self):
        """Save graph to JSON file"""
        SDE_DIR.mkdir(parents=True, exist_ok=True)
        
        graph_for_json = {str(k): v for k, v in self.graph.items()}
        
        with open(GRAPH_OUTPUT, 'w') as f:
            json.dump(graph_for_json, f, indent=2)
        
        file_size = GRAPH_OUTPUT.stat().st_size
        size_mb = file_size / (1024 * 1024)
        print(f"  ✅ File size: {size_mb:.2f} MB")
    
    def _print_statistics(self):
        """Print graph statistics"""
        total_connections = sum(len(neighbors) for neighbors in self.graph.values())
        avg_connections = total_connections / len(self.graph) if self.graph else 0
        
        most_connected = sorted(
            [(sys_id, len(neighbors)) for sys_id, neighbors in self.graph.items()],
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        print(f"📊 Graph Statistics:")
        print(f"   • Total systems: {len(self.graph):,}")
        print(f"   • Total connections: {total_connections:,}")
        print(f"   • Average connections per system: {avg_connections:.2f}")
        print(f"   • Most connected systems:")
        for sys_id, conn_count in most_connected:
            print(f"     - System {sys_id}: {conn_count} connections")

# ==============================================================================
# MAIN
# ==============================================================================

def main():
    """Main entry point"""
    print("=" * 70)
    print("STEP 2: EVE Static Data Setup")
    print("=" * 70)
    print()
    
    start_time = time.time()
    
    # Part 1: Download SDE
    if not download_sde():
        print("\n✗ SDE download failed. Please check your internet connection.")
        return 1
    
    # Part 2: Build Universe Graph
    builder = UniverseGraphBuilder()
    graph = builder.build_graph_from_sde()
    
    elapsed_time = time.time() - start_time
    
    print("\n" + "=" * 70)
    print("✅ STEP 2 COMPLETE!")
    print("=" * 70)
    print(f"⏱️  Total time: {elapsed_time:.1f} seconds")
    print()
    print("📁 Created files:")
    print(f"   • {SDE_DIR}/  (EVE game data)")
    print(f"   • {GRAPH_OUTPUT}  (Jump route graph)")
    print()
    print("Next step:")
    print("  Run: python 3_refresh_user_profile.py")
    print("  (Authenticate & fetch your character data)")
    print()
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
