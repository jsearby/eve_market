"""
==============================================================================
EVE Online Manufacturing Optimizer
==============================================================================
Analyzes the most cost-efficient way to build items based on your skills
- Compares mining vs buying materials
- Calculates profitability with your skills
- Shows full recursive material breakdown
- Tracks blueprint ownership

Usage:
  python A_manufacturing_optimizer.py --target "<item name>"
  
Example:
  python A_manufacturing_optimizer.py --target "Orca"
  python A_manufacturing_optimizer.py --target "Retriever"

Requires: 2_refresh_sde.py and 3_refresh_user_profile.py to be run first
==============================================================================
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import argparse
from tools.character_model import CharacterProfile, format_isk
from tools.config import SDE_DIR, MKT_DIR
from tools.sde_loader import find_sde_file, load_cached_yaml

def classify_material(type_id: int, item_name: str, types_data: Dict, groups_data: Dict) -> str:
    """Classify material type based on SDE data"""
    if type_id not in types_data:
        return 'UNKNOWN'
    
    type_info = types_data[type_id]
    group_id = type_info.get('groupID')
    
    if not group_id or group_id not in groups_data:
        return 'UNKNOWN'
    
    group_info = groups_data[group_id]
    group_name = group_info.get('name', {}).get('en', '').lower()
    category_id = group_info.get('categoryID')
    
    # Special case: Capital construction components (these specific items)
    advanced_component_names = [
        'self-harmonizing power core', 'recursive computing module',
        'integrity response drones', 'broadcast node', 'wetware mainframe',
        'sterile conduits', 'nano-factory', 'organic mortar applicators'
    ]
    if item_name.lower() in advanced_component_names:
        return 'ADVANCED'
    
    # Classify based on group ID and name
    # Minerals
    if group_id == 18 or 'mineral' in group_name:
        return 'MINERAL'
    # Moon Mining Materials
    elif group_id == 427:  # Moon Materials (raw)
        return 'MOON'
    # Reaction Products (Intermediate and Composite)
    elif group_id == 428:  # Intermediate Materials (from reactions)
        return 'REACTION_INT'
    elif group_id == 429:  # Composite (final reaction products)
        return 'REACTION'
    # Fuel Blocks
    elif group_id == 1136:  # Fuel Block
        return 'FUEL'
    # Planetary Interaction Products (all tiers)
    elif group_id in [1035, 1034, 1040, 1041, 1033, 1032] or 'planet' in group_name or ('commodities' in group_name and group_id != 1042):
        # 1035 = Planet Organic/Metallic/Mineral - Raw Resource (P0)
        # 1034 = Refined Commodities - Tier 2 (P2)
        # Others = various PI tiers
        return 'PI'
    # Group 1042 is tricky - contains both PI basics AND advanced capitals
    elif group_id == 1042:
        # Most basic commodities are PI
        if item_name.lower() not in advanced_component_names:
            return 'PI'
        else:
            return 'ADVANCED'
    # Advanced Capital Construction Components
    elif group_id == 334 or 'construction components' in group_name:
        return 'ADVANCED'
    # Ice products
    elif 'ice' in group_name:
        return 'ICE'
    # General materials category
    elif category_id == 4:
        return 'MATERIAL'
    else:
        return 'OTHER'

class ManufacturingOptimizer:
    """Analyzes manufacturing costs and options"""
    
    def __init__(self, profile: CharacterProfile):
        self.profile = profile
        self.blueprints = None
        self.types = None
        self.groups = None
        self.planet_schematics = None
        
        # Load SDE data
        print("📚 Loading EVE SDE data (static game database)...")
        if not self._load_sde():
            raise Exception("Failed to load SDE data. Run 'python 2_refresh_sde.py' first!")
        print("✓ SDE data loaded\n")
        
        # Extract blueprints from assets
        print("👤 Processing your character assets...")
        self._extract_blueprints_from_assets()
    
    def _load_sde(self) -> bool:
        """Load blueprint and type data from SDE with caching"""
        try:
            blueprints_file = find_sde_file("blueprints.yaml")
            if not blueprints_file:
                print(f"✗ blueprints.yaml not found. Run 'python 2_refresh_sde.py' first!")
                return False
            self.blueprints = load_cached_yaml(blueprints_file, "blueprints_cache.pkl", "blueprints")

            types_file = find_sde_file("types.yaml")
            if not types_file:
                print(f"✗ types.yaml not found. Run 'python 2_refresh_sde.py' first!")
                return False
            self.types = load_cached_yaml(types_file, "types_cache.pkl", "types")

            groups_file = find_sde_file("groups.yaml")
            if not groups_file:
                print(f"   ⚠️  groups.yaml not found - material classification will be limited")
                self.groups = {}
            else:
                self.groups = load_cached_yaml(groups_file, "groups_cache.pkl", "groups")

            schematics_file = find_sde_file("planetSchematics.yaml")
            if not schematics_file:
                print(f"   ⚠️  planetSchematics.yaml not found - PI breakdown will be limited")
                self.planet_schematics = {}
            else:
                self.planet_schematics = load_cached_yaml(schematics_file, "planet_schematics_cache.pkl", "planet schematics")

            return True

        except Exception as e:
            print(f"✗ Error loading SDE: {e}")
            return False
    
    def _extract_blueprints_from_assets(self):
        """Extract blueprint information from character assets using SDE data"""
        if not self.profile.assets:
            print("   ℹ️  No assets in character profile")
            print("   Run 'python 3_refresh_user_profile.py' to fetch your assets")
            self.profile.blueprints = []
            return
        
        print(f"   Analyzing {len(self.profile.assets)} assets from cache/user/character_profile.json...")
        blueprints = []
        blueprint_count = 0
        
        for asset in self.profile.assets:
            type_id = asset.get('type_id')
            
            # Method 1: ESI marks blueprints with is_blueprint_copy field (present for both BPC and BPO)
            # BPCs have is_blueprint_copy: true, BPOs have is_blueprint_copy: false
            has_blueprint_flag = 'is_blueprint_copy' in asset
            
            # Method 2: Check SDE data for group ID 2 (Blueprints & Reactions)
            is_blueprint_by_group = False
            type_name = None
            if type_id in self.types:
                type_info = self.types[type_id]
                group_id = type_info.get('groupID')
                type_name = type_info.get('name', {}).get('en', '')
                is_blueprint_by_group = (group_id == 2) or ('Blueprint' in type_name)
            
            # Accept if either method identifies it as a blueprint
            if has_blueprint_flag or is_blueprint_by_group:
                blueprint_count += 1
                # Get type name from SDE if available, otherwise use type_id
                if not type_name and type_id in self.types:
                    type_name = self.types[type_id].get('name', {}).get('en', f'Type {type_id}')
                elif not type_name:
                    type_name = f'Type {type_id}'
                
                blueprint_info = {
                    'item_id': asset.get('item_id'),
                    'type_id': type_id,
                    'type_name': type_name,
                    'location_id': asset.get('location_id'),
                    'location_type': asset.get('location_type'),
                    'location_flag': asset.get('location_flag'),
                    'quantity': asset.get('quantity', 1),
                    'is_singleton': asset.get('is_singleton', False),
                    'is_blueprint_copy': asset.get('is_blueprint_copy', False),
                }
                blueprints.append(blueprint_info)
        
        self.profile.blueprints = blueprints
        if blueprints:
            print(f"   ✓ Extracted {len(blueprints)} blueprints from assets")
            # Show a sample of what we found for debugging
            print(f"   📋 Sample blueprints:")
            for bp in blueprints[:3]:  # Show first 3
                bp_type = "BPC" if bp.get('is_blueprint_copy') else "BPO"
                print(f"      • {bp['type_name']} ({bp_type}, Type ID: {bp['type_id']})")
            if len(blueprints) > 3:
                print(f"      ... and {len(blueprints) - 3} more")
        else:
            print(f"   ℹ️  No blueprints found in assets")
    
    def find_item_by_name(self, name: str) -> Optional[int]:
        """Find item type ID by name (case-insensitive partial match)"""
        name_lower = name.lower()
        matches = []
        
        for type_id, data in self.types.items():
            if 'name' in data and 'en' in data['name']:
                item_name = data['name']['en']
                if name_lower in item_name.lower():
                    matches.append((type_id, item_name))
        
        if not matches:
            return None
        
        # If exact match, return it
        for type_id, item_name in matches:
            if item_name.lower() == name_lower:
                return type_id
        
        # If multiple matches, show options
        if len(matches) > 1:
            print(f"\n🔍 Multiple items found matching '{name}':")
            for i, (type_id, item_name) in enumerate(matches[:10], 1):
                print(f"   {i}. {item_name} (ID: {type_id})")
            if len(matches) > 10:
                print(f"   ... and {len(matches) - 10} more")
            
            try:
                choice = int(input("\nSelect item number (or 0 to cancel): "))
                if 1 <= choice <= min(10, len(matches)):
                    return matches[choice - 1][0]
            except:
                pass
            return None
        
        return matches[0][0]
    
    def get_item_name(self, type_id: int) -> str:
        """Get item name from type ID"""
        if type_id in self.types and 'name' in self.types[type_id]:
            return self.types[type_id]['name'].get('en', f'Item {type_id}')
        return f'Item {type_id}'
    
    def get_blueprint_for_item(self, type_id: int) -> Optional[Dict]:
        """Find blueprint that manufactures given item"""
        for bp_id, bp_data in self.blueprints.items():
            if 'activities' in bp_data and 'manufacturing' in bp_data['activities']:
                manufacturing = bp_data['activities']['manufacturing']
                if 'products' in manufacturing:
                    for product in manufacturing['products']:
                        if product['typeID'] == type_id:
                            return {
                                'blueprint_id': bp_id,
                                'blueprint_name': self.get_item_name(bp_id),
                                'data': bp_data
                            }
        return None
    
    def is_raw_material(self, type_id: int) -> bool:
        """Check if item is a raw material (cannot be manufactured)"""
        return self.get_blueprint_for_item(type_id) is None
    
    def display_reaction_breakdown(self, type_id: int, quantity: int, indent_level: int = 2):
        """
        Recursively display reaction product breakdown to raw moon materials.
        indent_level controls indentation (spaces/tabs).
        """
        reaction_inputs = self.get_reaction_inputs(type_id)
        if not reaction_inputs:
            # This is a raw material
            return
        
        indent = "   " * indent_level
        print(f"{indent}⚗️  Reaction - made from:")
        
        for input_id, input_qty in reaction_inputs.items():
            input_name = self.get_item_name(input_id)
            input_total = input_qty * quantity
            
            # Check if this input has further reaction inputs or is raw
            sub_inputs = self.get_reaction_inputs(input_id)
            
            if sub_inputs:
                # This is an intermediate reaction product, show and recurse
                print(f"{indent}   🔧 {input_name}: {input_qty} × {quantity:,} = {input_total:,} units")
                self.display_reaction_breakdown(input_id, input_total, indent_level + 2)
            else:
                # This is a raw material (moon mat or fuel block)
                print(f"{indent}   ⛏️  {input_name} (moon/fuel): {input_qty} × {quantity:,} = {input_total:,} units")
    
    def display_pi_breakdown(self, type_id: int, quantity: int, indent_level: int = 2):
        """
        Recursively display PI material breakdown to P0.
        indent_level controls indentation (spaces/tabs).
        """
        pi_inputs = self.get_pi_inputs(type_id)
        if not pi_inputs:
            # This is P0 - raw material
            return
        
        indent = "   " * indent_level
        print(f"{indent}🌍 PI Material - made from:")
        
        for pi_input_id, pi_input_qty in pi_inputs.items():
            pi_input_name = self.get_item_name(pi_input_id)
            pi_input_total = pi_input_qty * quantity
            
            # Check if this input has further inputs (P1+) or is P0
            pi_sub_inputs = self.get_pi_inputs(pi_input_id)
            
            if pi_sub_inputs:
                # This is P1+ material, show and recurse
                print(f"{indent}   🔧 {pi_input_name}: {pi_input_qty} × {quantity:,} = {pi_input_total:,} units")
                self.display_pi_breakdown(pi_input_id, pi_input_total, indent_level + 2)
            else:
                # This is P0 - raw planetary resource
                print(f"{indent}   ⛏️  {pi_input_name} (P0): {pi_input_qty} × {quantity:,} = {pi_input_total:,} units")
    
    def get_recursive_materials(self, type_id: int, quantity: int = 1, depth: int = 0, visited: set = None) -> Dict[int, int]:
        """
        Recursively expand all materials needed to build an item.
        Returns a dictionary of {material_type_id: total_quantity} for all raw materials.
        Handles manufacturing, reactions, and PI.
        """
        if visited is None:
            visited = set()
        
        # Prevent infinite loops
        if type_id in visited:
            return {}
        visited.add(type_id)
        
        # Check if this is a reaction product first
        reaction_inputs = self.get_reaction_inputs(type_id)
        if reaction_inputs:
            raw_materials = defaultdict(int)
            for mat_type_id, mat_quantity in reaction_inputs.items():
                total_mat_quantity = mat_quantity * quantity
                # Recursively expand this material
                sub_materials = self.get_recursive_materials(mat_type_id, total_mat_quantity, depth + 1, visited.copy())
                for sub_mat_id, sub_mat_quantity in sub_materials.items():
                    raw_materials[sub_mat_id] += sub_mat_quantity
            return dict(raw_materials)
        
        # Check if this is a PI material
        pi_inputs = self.get_pi_inputs(type_id)
        if pi_inputs:
            raw_materials = defaultdict(int)
            for mat_type_id, mat_quantity in pi_inputs.items():
                total_mat_quantity = mat_quantity * quantity
                # Recursively expand this material
                sub_materials = self.get_recursive_materials(mat_type_id, total_mat_quantity, depth + 1, visited.copy())
                for sub_mat_id, sub_mat_quantity in sub_materials.items():
                    raw_materials[sub_mat_id] += sub_mat_quantity
            return dict(raw_materials)
        
        # Get blueprint for this item (manufacturing)
        blueprint = self.get_blueprint_for_item(type_id)
        if not blueprint:
            # This is a raw material
            return {type_id: quantity}
        
        # Get materials from blueprint
        bp_data = blueprint['data']
        manufacturing = bp_data['activities']['manufacturing']
        materials = manufacturing.get('materials', [])
        
        # Get output quantity (how many items one manufacturing run produces)
        products = manufacturing.get('products', [])
        output_per_run = 1
        if products:
            output_per_run = products[0].get('quantity', 1)
        
        # Calculate how many runs needed
        runs_needed = (quantity + output_per_run - 1) // output_per_run  # Ceiling division
        
        # Accumulate raw materials
        raw_materials = defaultdict(int)
        
        for mat in materials:
            mat_type_id = mat['typeID']
            mat_quantity_per_run = mat['quantity']
            total_mat_quantity = mat_quantity_per_run * runs_needed
            
            # Recursively expand this material
            sub_materials = self.get_recursive_materials(mat_type_id, total_mat_quantity, depth + 1, visited.copy())
            
            # Add to accumulator
            for sub_mat_id, sub_mat_quantity in sub_materials.items():
                raw_materials[sub_mat_id] += sub_mat_quantity
        
        return dict(raw_materials)
    
    def get_pi_schematic(self, type_id: int) -> Optional[Dict]:
        """Find PI schematic for producing this item"""
        for schematic_id, schematic_data in self.planet_schematics.items():
            if 'types' in schematic_data:
                # Check output products
                for output_type_id, output_data in schematic_data['types'].items():
                    if output_type_id == type_id and not output_data.get('isInput', True):
                        return {
                            'schematic_id': schematic_id,
                            'data': schematic_data
                        }
        return None
    
    def get_reaction_inputs(self, type_id: int) -> Optional[Dict[int, int]]:
        """Get input materials needed for this reaction"""
        # Find reaction blueprint for this product
        for bp_id, bp_data in self.blueprints.items():
            activities = bp_data.get('activities', {})
            if 'reaction' in activities:
                products = activities['reaction'].get('products', [])
                if products and products[0].get('typeID') == type_id:
                    # Found the reaction blueprint
                    materials = activities['reaction'].get('materials', [])
                    inputs = {}
                    for mat in materials:
                        inputs[mat['typeID']] = mat['quantity']
                    return inputs if inputs else None
        return None
    
    def get_pi_inputs(self, type_id: int) -> Optional[Dict[int, int]]:
        """Get input materials needed to produce this PI item"""
        schematic = self.get_pi_schematic(type_id)
        if not schematic:
            return None
        
        inputs = {}
        schematic_data = schematic['data']
        if 'types' in schematic_data:
            for input_type_id, input_data in schematic_data['types'].items():
                if input_data.get('isInput', False):
                    quantity = input_data.get('quantity', 1)
                    inputs[input_type_id] = quantity
        
        return inputs if inputs else None
    
    def get_recursive_reaction_materials(self, type_id: int, quantity: int = 1) -> Dict[int, int]:
        """
        Recursively break down reaction products to raw moon materials.
        Composite -> Intermediate -> Moon Materials
        """
        # Check if this is a reaction product
        reaction_inputs = self.get_reaction_inputs(type_id)
        
        if not reaction_inputs:
            # This is a raw material or not a reaction product
            return {type_id: quantity}
        
        # This is a reaction product, break it down
        raw_materials = defaultdict(int)
        
        for input_type_id, input_quantity_per_run in reaction_inputs.items():
            total_input_quantity = input_quantity_per_run * quantity
            
            # Recursively break down inputs
            sub_materials = self.get_recursive_reaction_materials(input_type_id, total_input_quantity)
            
            for sub_mat_id, sub_mat_quantity in sub_materials.items():
                raw_materials[sub_mat_id] += sub_mat_quantity
        
        return dict(raw_materials)
    
    def get_recursive_pi_materials(self, type_id: int, quantity: int = 1) -> Dict[int, int]:
        """
        Recursively break down PI materials to P0 (raw planetary resources).
        P2 -> P1 -> P0
        """
        # Check if this is a PI material
        pi_inputs = self.get_pi_inputs(type_id)
        
        if not pi_inputs:
            # This is P0 (raw material) or not a PI item
            return {type_id: quantity}
        
        # This is P1+ material, break it down
        raw_materials = defaultdict(int)
        
        for input_type_id, input_quantity_per_run in pi_inputs.items():
            total_input_quantity = input_quantity_per_run * quantity
            
            # Recursively break down inputs
            sub_materials = self.get_recursive_pi_materials(input_type_id, total_input_quantity)
            
            for sub_mat_id, sub_mat_quantity in sub_materials.items():
                raw_materials[sub_mat_id] += sub_mat_quantity
        
        return dict(raw_materials)
    
    def collect_required_blueprints(self, type_id: int, visited: set = None) -> Dict[int, Dict]:
        """
        Recursively collect all blueprints needed to manufacture an item.
        Returns dict of {type_id: {'name': str, 'blueprint_id': int, 'runs_needed': int}}
        """
        if visited is None:
            visited = set()
        
        if type_id in visited:
            return {}
        visited.add(type_id)
        
        blueprints_needed = {}
        
        # Check if this item has a manufacturing blueprint
        blueprint = self.get_blueprint_for_item(type_id)
        if blueprint:
            bp_data = blueprint['data']
            item_name = self.get_item_name(type_id)
            
            # Add this blueprint
            blueprints_needed[type_id] = {
                'name': item_name,
                'blueprint_id': blueprint['blueprint_id'],
                'type_id': type_id,
                'has_manufacturing': True
            }
            
            # Recursively check materials
            manufacturing = bp_data['activities']['manufacturing']
            materials = manufacturing.get('materials', [])
            
            for mat in materials:
                mat_type_id = mat['typeID']
                sub_blueprints = self.collect_required_blueprints(mat_type_id, visited.copy())
                blueprints_needed.update(sub_blueprints)
        
        # Check if this is a reaction product
        reaction_inputs = self.get_reaction_inputs(type_id)
        if reaction_inputs:
            item_name = self.get_item_name(type_id)
            
            # Find the reaction blueprint ID
            reaction_bp_id = None
            for bp_id, bp_data in self.blueprints.items():
                activities = bp_data.get('activities', {})
                if 'reaction' in activities:
                    products = activities['reaction'].get('products', [])
                    if products and products[0].get('typeID') == type_id:
                        reaction_bp_id = bp_id
                        break
            
            if reaction_bp_id:
                blueprints_needed[type_id] = {
                    'name': item_name,
                    'blueprint_id': reaction_bp_id,
                    'type_id': type_id,
                    'has_reaction': True
                }
            
            # Recursively check reaction inputs
            for input_id in reaction_inputs.keys():
                sub_blueprints = self.collect_required_blueprints(input_id, visited.copy())
                blueprints_needed.update(sub_blueprints)
        
        return blueprints_needed
    
    def analyze_manufacturing(self, target_item: str) -> Dict:
        """Analyze manufacturing options for target item"""
        print(f"\n{'='*80}")
        print(f"🏗️  MANUFACTURING ANALYSIS: {target_item}")
        print(f"{'='*80}")
        
        # Find item
        print(f"\n🔍 Searching for item...")
        type_id = self.find_item_by_name(target_item)
        if not type_id:
            print(f"✗ Item not found: {target_item}")
            return None
        
        item_name = self.get_item_name(type_id)
        print(f"✓ Found: {item_name} (ID: {type_id})")
        
        # Find blueprint
        print(f"\n📋 Looking for blueprint...")
        blueprint = self.get_blueprint_for_item(type_id)
        if not blueprint:
            print(f"✗ No blueprint found for {item_name}")
            print(f"   This item cannot be manufactured (maybe it's a raw material or NPC item)")
            return None
        
        print(f"✓ Blueprint: {blueprint['blueprint_name']}")
        
        # Collect all required blueprints
        print(f"\n📘 BLUEPRINT REQUIREMENTS")
        print(f"{'='*80}")
        print(f"Analyzing blueprint requirements (including all components)...")
        
        all_blueprints = self.collect_required_blueprints(type_id)
        
        if all_blueprints:
            print(f"\n✓ Total blueprints needed: {len(all_blueprints)}")
            
            # Count by type
            manufacturing_count = sum(1 for bp in all_blueprints.values() if bp.get('has_manufacturing'))
            reaction_count = sum(1 for bp in all_blueprints.values() if bp.get('has_reaction'))
            
            print(f"   • Manufacturing blueprints: {manufacturing_count}")
            print(f"   • Reaction blueprints: {reaction_count}")
            
            # Check owned blueprints
            owned_blueprints = {}
            blueprint_data_available = False
            
            if hasattr(self.profile, 'blueprints') and self.profile.blueprints is not None:
                if len(self.profile.blueprints) > 0:
                    blueprint_data_available = True
                    for owned_bp in self.profile.blueprints:
                        bp_type_id = owned_bp['type_id']
                        if bp_type_id not in owned_blueprints:
                            owned_blueprints[bp_type_id] = []
                        owned_blueprints[bp_type_id].append(owned_bp)
                else:
                    # Blueprints were fetched but none found
                    blueprint_data_available = True
                    print(f"\n📊 Ownership Status:")
                    print(f"   ℹ️  No blueprints found in your assets")
                    print(f"   💡 If you have blueprints, they may be in containers or corp hangars")
            
            if blueprint_data_available and owned_blueprints:
                # Match owned blueprints by blueprint_id (not product type_id)
                owned_count = len([bp_id for bp_id, bp_info in all_blueprints.items() 
                                  if bp_info.get('blueprint_id') in owned_blueprints])
                missing_count = len(all_blueprints) - owned_count
                
                print(f"\n📊 Ownership Status:")
                print(f"   ✓ You own: {owned_count} of {len(all_blueprints)} required blueprints")
                print(f"   ✗ Missing: {missing_count} blueprints")
                print(f"   ℹ️  Total blueprints in assets: {len(self.profile.blueprints)}")
            elif not blueprint_data_available:
                print(f"\n⚠️  Blueprint ownership data not available")
                print(f"   Reasons:")
                print(f"   1. Run 'python 3_refresh_user_profile.py' to fetch your asset data")
                print(f"   2. Make sure to grant 'esi-assets.read_assets.v1' scope")
                print(f"   3. Re-authenticate if you recently updated ESI scopes")
            
            print(f"\n💡 How to check your blueprints in-game:")
            print(f"   1. Open Personal Assets (Alt+T)")
            print(f"   2. Search for 'Blueprint' in the search bar")
            print(f"   3. Filter by name to find specific blueprints")
            print(f"   4. Check if they are BPO (Blueprint Original) or BPC (Blueprint Copy)")
            
            print(f"\n📋 Blueprint List:")
            
            # Sort by name for better readability
            sorted_bps = sorted(all_blueprints.items(), key=lambda x: x[1]['name'])
            
            for bp_type_id, bp_info in sorted_bps:
                bp_name = bp_info['name']
                bp_type = "Manufacturing" if bp_info.get('has_manufacturing') else "Reaction"
                blueprint_id = bp_info.get('blueprint_id')
                
                # Check if owned (match by blueprint_id, not product type_id)
                if blueprint_id and blueprint_id in owned_blueprints:
                    owned_copies = owned_blueprints[blueprint_id]
                    for owned in owned_copies:
                        bp_type_str = "BPC" if owned.get('is_blueprint_copy') else "BPO"
                        location = owned.get('location_name', f"Location {owned.get('location_id')}")
                        print(f"   ✓ {bp_name} ({bp_type})")
                        print(f"     └─ {bp_type_str} at {location}")
                else:
                    print(f"   ✗ {bp_name} ({bp_type})")
                    print(f"     └─ NOT OWNED - Purchase from contracts or market")
        else:
            print(f"   Only main blueprint needed")
        
        print(f"\n{'='*80}")
        
        # Get manufacturing data
        bp_data = blueprint['data']
        manufacturing = bp_data['activities']['manufacturing']
        
        # Get required materials
        materials = manufacturing.get('materials', [])
        if not materials:
            print(f"✗ No materials listed (unusual)")
            return None
        
        print(f"\n📦 Material Requirements:")
        print(f"   Required materials: {len(materials)} types")
        
        total_materials = {}
        manufactured_components = []
        
        for mat in materials:
            mat_type_id = mat['typeID']
            mat_quantity = mat['quantity']
            mat_name = self.get_item_name(mat_type_id)
            total_materials[mat_type_id] = {
                'name': mat_name,
                'quantity': mat_quantity
            }
            
            # Check if this is a manufactured component
            is_manufactured = not self.is_raw_material(mat_type_id)
            marker = "🏭" if is_manufactured else "⛏️"
            
            print(f"   {marker} {mat_name}: {mat_quantity:,} units" + 
                  (" (manufactured)" if is_manufactured else ""))
            
            if is_manufactured:
                manufactured_components.append((mat_type_id, mat_name, mat_quantity))
        
        # Show recursive breakdown for each manufactured component
        if manufactured_components:
            print(f"\n{'='*80}")
            print(f"📊 COMPONENT BREAKDOWN (Recursive)")
            print(f"{'='*80}")
            
            for comp_id, comp_name, comp_qty in manufactured_components:
                print(f"\n🔧 {comp_name} (need {comp_qty:,} units):")
                
                # Get the direct materials for this component
                comp_blueprint = self.get_blueprint_for_item(comp_id)
                if comp_blueprint:
                    comp_bp_data = comp_blueprint['data']
                    comp_manufacturing = comp_bp_data['activities']['manufacturing']
                    comp_materials = comp_manufacturing.get('materials', [])
                    
                    # Calculate runs needed
                    comp_products = comp_manufacturing.get('products', [])
                    comp_output_per_run = 1
                    if comp_products:
                        comp_output_per_run = comp_products[0].get('quantity', 1)
                    runs_needed = (comp_qty + comp_output_per_run - 1) // comp_output_per_run
                    
                    print(f"   Manufacturing: {runs_needed:,} run(s) × {comp_output_per_run} per run = {comp_qty:,} units")
                    print(f"   Direct materials per run:")
                    
                    for comp_mat in comp_materials:
                        comp_mat_id = comp_mat['typeID']
                        comp_mat_qty_per_run = comp_mat['quantity']
                        comp_mat_total = comp_mat_qty_per_run * runs_needed
                        comp_mat_name = self.get_item_name(comp_mat_id)
                        is_raw = self.is_raw_material(comp_mat_id)
                        
                        # Check if it's a PI material or reaction product that can be expanded
                        pi_inputs = self.get_pi_inputs(comp_mat_id)
                        reaction_inputs = self.get_reaction_inputs(comp_mat_id)
                        marker = "⛏️" if is_raw else "🔧"
                        
                        print(f"      {marker} {comp_mat_name}: {comp_mat_qty_per_run:,} × {runs_needed:,} = {comp_mat_total:,} units")
                        
                        # If it's a PI material, show full recursive breakdown
                        if pi_inputs:
                            self.display_pi_breakdown(comp_mat_id, comp_mat_total, indent_level=2)
                        # If it's a reaction product, show full recursive breakdown
                        elif reaction_inputs:
                            self.display_reaction_breakdown(comp_mat_id, comp_mat_total, indent_level=2)
        
        # Calculate total raw materials needed
        print(f"\n{'='*80}")
        print(f"⛏️  TOTAL RAW MATERIALS NEEDED")
        print(f"{'='*80}")
        print(f"\nRecursively calculating all raw materials (this may take a moment)...")
        
        raw_materials = self.get_recursive_materials(type_id, 1)
        
        # Further expand PI and reaction materials to raw resources
        print(f"   Breaking down PI materials to P0 (raw planetary resources)...")
        print(f"   Breaking down reaction products to moon materials...")
        final_materials = defaultdict(int)
        
        for mat_id, mat_qty in raw_materials.items():
            # Materials are already expanded by get_recursive_materials
            # which now handles manufacturing, reactions, and PI
            final_materials[mat_id] += mat_qty
        
        raw_materials = dict(final_materials)
        
        if raw_materials:
            print(f"\n✓ Complete bill of materials:")
            print(f"   {len(raw_materials)} different raw material types needed\n")
            
            # Classify and group materials
            classified_materials = {
                'MINERAL': [],
                'PI': [],
                'MOON': [],
                'FUEL': [],
                'ADVANCED': [],
                'ICE': [],
                'MATERIAL': [],
                'REACTION': [],
                'REACTION_INT': [],
                'OTHER': []
            }
            
            for mat_id, mat_qty in raw_materials.items():
                mat_name = self.get_item_name(mat_id)
                material_type = classify_material(mat_id, mat_name, self.types, self.groups)
                classified_materials[material_type].append((mat_name, mat_qty))
            
            # Display by category
            category_info = {
                'MINERAL': ('⛏️  Minerals (from mining ore)', '⛏️ '),
                'PI': ('🌍 Planetary Interaction - P0 (extract from planets)', '🌍'),
                'MOON': ('🌙 Moon Materials (from moon mining)', '🌙'),
                'FUEL': ('⚡ Fuel Blocks (buy from market or manufacture)', '⚡'),
                'ADVANCED': ('🎁 Advanced Components (NPC/Contracts)', '🎁'),
                'ICE': ('❄️  Ice Products', '❄️ '),
                'MATERIAL': ('📦 Materials (buy from market)', '📦'),
                'REACTION': ('⚗️  Reaction Products - Composite (make via reactions)', '⚗️ '),
                'REACTION_INT': ('🧪 Reaction Products - Intermediate (make via reactions)', '🧪'),
                'OTHER': ('❓ Other', '❓')
            }
            
            for category in ['MINERAL', 'PI', 'MOON', 'FUEL', 'ADVANCED', 'REACTION', 'REACTION_INT', 'ICE', 'MATERIAL', 'OTHER']:
                items = classified_materials[category]
                if items:
                    title, icon = category_info[category]
                    print(f"\n{title}:")
                    # Sort by quantity descending
                    items.sort(key=lambda x: x[1], reverse=True)
                    for mat_name, mat_qty in items:
                        print(f"   {icon} {mat_name}: {mat_qty:,} units")
        else:
            print(f"\n⛏️  No recursive materials (item is raw or error occurred)")
        
        # Add acquisition guide
        if raw_materials:
            print(f"\n{'='*80}")
            print(f"📚 ACQUISITION GUIDE - Where to Get Raw Materials")
            print(f"{'='*80}")
            
            # Minerals acquisition guide
            if classified_materials['MINERAL']:
                print(f"\n⛏️  MINERALS - Mining & Refining Ore:")
                print(f"   Mine ore, then refine at station (requires Reprocessing skills)")
                print(f"")
                
                mineral_ore_guide = {
                    'Tritanium': ('Veldspar', 'High Sec', 'Most common, anywhere'),
                    'Pyerite': ('Scordite', 'High Sec', 'Common in 0.7-1.0 systems'),
                    'Mexallon': ('Pyroxeres', 'High Sec', 'Common in 0.5-0.9 systems'),
                    'Isogen': ('Omber', 'Low Sec (0.4-0.1)', 'Some in 0.4-0.7 high sec'),
                    'Nocxium': ('Hemorphite', 'Low/Null Sec', 'Rare in high sec'),
                    'Zydrine': ('Bistot', 'Null Sec (0.0)', 'Requires expedition to null'),
                    'Megacyte': ('Arkonor', 'Null Sec (0.0)', 'Best yields in null/wormholes'),
                }
                
                for mat_name, mat_qty in classified_materials['MINERAL']:
                    if mat_name in mineral_ore_guide:
                        ore, location, notes = mineral_ore_guide[mat_name]
                        print(f"   • {mat_name}: Mine {ore} ({location})")
                        print(f"     └─ {notes}")
            
            # PI acquisition guide
            if classified_materials['PI']:
                print(f"\n🌍 PLANETARY INTERACTION (P0 Materials):")
                print(f"   Extract from planets using Command Centers + Extractors")
                print(f"   Better yields in Low Sec (×1.5) and Null Sec (×2.0)")
                print(f"")
                
                pi_planet_guide = {
                    'Aqueous Liquids': 'Temperate, Oceanic planets',
                    'Autotrophs': 'Temperate, Gas planets',
                    'Base Metals': 'Barren, Lava, Ice planets',
                    'Carbon Compounds': 'Oceanic, Storm planets',
                    'Complex Organisms': 'Temperate, Oceanic planets',
                    'Felsic Magma': 'Lava, Plasma planets',
                    'Heavy Metals': 'Barren, Lava planets',
                    'Ionic Solutions': 'Storm, Gas planets',
                    'Microorganisms': 'Oceanic, Water planets',
                    'Noble Gas': 'Gas, Storm planets',
                    'Noble Metals': 'Barren, Ice planets',
                    'Non-CS Crystals': 'Ice, Barren planets',
                    'Planktic Colonies': 'Oceanic, Temperate planets',
                    'Reactive Gas': 'Gas, Storm planets',
                    'Suspended Plasma': 'Plasma, Lava planets',
                }
                
                for mat_name, mat_qty in classified_materials['PI']:
                    if mat_name in pi_planet_guide:
                        planet_types = pi_planet_guide[mat_name]
                        print(f"   • {mat_name}: {planet_types}")
                
                print(f"\n   💡 Tip: Set up extractors in Low/Null sec for better yields")
                print(f"   💡 Use planetary production chains for passive income")
            
            # Moon materials guide
            if classified_materials['MOON']:
                print(f"\n🌙 MOON MATERIALS - Moon Mining:")
                print(f"   Requires Athanor or Tatara refinery (Low Sec 0.4 or Null Sec only)")
                print(f"   Corporation/Alliance must own the structure")
                print(f"")
                print(f"   • Atmospheric Gases: Common in most moons (R4 rarity)")
                print(f"   • Evaporite Deposits: Common in most moons (R4 rarity)")
                print(f"   • Hydrocarbons: Common in most moons (R4 rarity)")
                print(f"   • Silicates: Common in most moons (R4 rarity)")
                print(f"")
                print(f"   💡 Tip: Join a null-sec alliance with moon mining infrastructure")
                print(f"   💡 Alternative: Buy from Jita market (often cheaper than mining)")
            
            # Ice products guide
            if classified_materials['ICE']:
                print(f"\n❄️  ICE PRODUCTS - Ice Mining & Refining:")
                print(f"   Mine ice from ice belts, then refine at station")
                print(f"   Ice belts spawn in specific systems (check Dotlan)")
                print(f"")
                
                ice_guide = {
                    'Heavy Water': ('Blue Ice', 'High Sec', 'Gallente space'),
                    'Liquid Ozone': ('Clear Icicle, Glacial Mass', 'High/Low Sec', 'Common in all regions'),
                    'Helium Isotopes': ('Helium Isotopes', 'High/Low/Null', 'Amarr fuel, from Glare Crust'),
                    'Hydrogen Isotopes': ('Hydrogen Isotopes', 'High/Low/Null', 'Caldari fuel, from White Glaze'),
                    'Nitrogen Isotopes': ('Nitrogen Isotopes', 'High/Low/Null', 'Gallente fuel, from Thick Blue Ice'),
                    'Oxygen Isotopes': ('Oxygen Isotopes', 'High/Low/Null', 'Minmatar fuel, from Clear Icicle'),
                    'Strontium Clathrates': ('Blue Ice, White Glaze', 'High/Low Sec', 'Structure reinforcement timer fuel'),
                }
                
                for mat_name, mat_qty in classified_materials['ICE']:
                    if mat_name in ice_guide:
                        ice_type, location, notes = ice_guide[mat_name]
                        print(f"   • {mat_name}:")
                        print(f"     └─ Mine {ice_type} ({location})")
                        print(f"     └─ {notes}")
            
            # Fuel blocks guide
            if classified_materials['FUEL']:
                print(f"\n⚡ FUEL BLOCKS:")
                print(f"   Used in reactions and structure fuel")
                print(f"")
                print(f"   • Hydrogen Fuel Block: Manufactured from Caldari fuel (Liquid Ozone + Hydrogen Isotopes)")
                print(f"   • Oxygen Fuel Block: Manufactured from Minmatar fuel (Liquid Ozone + Oxygen Isotopes)")
                print(f"")
                print(f"   💡 Tip: Easier to buy from market than manufacture")
                print(f"   💡 Requires ice products + oxygen/coolant + heavy water + enriched uranium")
        
        # Get output quantity
        products = manufacturing.get('products', [])
        output_quantity = 1
        if products:
            output_quantity = products[0].get('quantity', 1)
        
        print(f"\n{'='*80}")
        print(f"🏭 MANUFACTURING OUTPUT")
        print(f"{'='*80}")
        print(f"   Produces: {output_quantity:,} × {item_name}")
        
        # Manufacturing time
        if 'time' in manufacturing:
            time_seconds = manufacturing['time']
            hours = time_seconds / 3600
            print(f"   Base time: {hours:.1f} hours")
        
        return {
            'item_name': item_name,
            'item_id': type_id,
            'blueprint': blueprint,
            'materials': total_materials,
            'output_quantity': output_quantity,
            'manufacturing_time': manufacturing.get('time', 0)
        }

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='EVE Online Manufacturing Optimizer')
    parser.add_argument('--target', type=str, required=True, help='Item to manufacture (e.g., "Orca")')
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("EVE ONLINE MANUFACTURING OPTIMIZER")
    print("=" * 80)
    
    # Load character profile
    profile = CharacterProfile()
    if not profile.load_profile():
        print("\n✗ No character profile found!")
        print("Run 'python 3_refresh_user_profile.py' first to generate your profile.")
        return
    
    print(f"\n✓ Loaded profile: {profile.name}")
    print(f"✓ Capital: {format_isk(profile.capital)} ISK")
    
    # Create optimizer
    try:
        optimizer = ManufacturingOptimizer(profile)
    except Exception as e:
        print(f"\n✗ {e}")
        return
    
    # Analyze target item
    analysis = optimizer.analyze_manufacturing(args.target)
    
    if analysis:
        print(f"\n{'='*80}")
        print("✨ Analysis complete!")
        print("\n💡 Next steps:")
        print("   1. Market price scanning (coming soon)")
        print("   2. Mining time calculation (coming soon)")
        print("   3. Cost comparison (coming soon)")
    
if __name__ == "__main__":
    main()
