"""
EVE Online Character Profile Analyzer
Generates a detailed report about your trading capabilities and actual costs
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from tools.config import PROFILE_FILE


class CharacterProfile:
    """EVE Online character profile for trading analysis"""
    
    def __init__(self):
        self.name = ""
        self.capital = 0.0
        
        # Raw assets from ESI (for all tools to use)
        self.assets = []  # List of all asset dictionaries from ESI
        
        # Owned blueprints (filtered from assets by consuming scripts)
        self.blueprints = []  # List of owned blueprint dictionaries
        
        # Trade skills (0-5)
        self.broker_relations = 0
        self.accounting = 0
        self.margin_trading = 0
        self.trade = 0
        self.retail = 0
        self.wholesale = 0
        self.tycoon = 0
        self.daytrading = 0
        
        # Hauling skills
        self.transport_ship = 0
        self.freighter = 0
        self.jump_freighter = 0
        
        # Industry skills
        self.industry = 0
        self.mass_production = 0
        self.advanced_industry = 0
        self.production_efficiency = 0
        
        # Science/Research skills
        self.science = 0
        self.metallurgy = 0
        self.research = 0
        self.laboratory_operation = 0
        
        # Refining skills
        self.reprocessing = 0
        self.reprocessing_efficiency = 0
        self.scrapmetal_processing = 0
        
        # Reactions
        self.reactions = 0
        self.mass_reactions = 0
        
        # Planetary Interaction
        self.planetology = 0
        self.advanced_planetology = 0
        self.command_center_upgrades = 0
        self.interplanetary_consolidation = 0
        
        # Mining Skills
        self.mining = 0
        self.ice_harvesting = 0
        self.gas_cloud_harvesting = 0
        self.mining_upgrades = 0
        self.mining_barge = 0
        self.exhumers = 0
        self.deep_core_mining = 0
        self.astrogeology = 0
        
        # Exploration Skills
        self.archaeology = 0
        self.hacking = 0
        self.salvaging = 0
        self.astrometrics = 0
        self.cloaking = 0
        self.covert_ops = 0
        
        # Combat - General
        self.gunnery = 0
        self.missile_launcher_operation = 0
        self.drones = 0
        
        # Ship Skills (highest across all races)
        self.frigate = 0
        self.destroyer = 0
        self.cruiser = 0
        self.battlecruiser = 0
        self.battleship = 0
        self.industrial = 0
        
        # Specialized Ships
        self.assault_frigates = 0
        self.interceptors = 0
        self.covert_ops_ship = 0
        self.heavy_assault_cruisers = 0
        self.logistics_cruisers = 0
        self.recon_ships = 0
        self.command_ships = 0
        self.marauders = 0
        self.black_ops_ship = 0
        self.carriers = 0
        self.dreadnoughts = 0
        
        # Standings (0.0 to 10.0)
        self.faction_standing = 0.0  # e.g., Caldari State for Jita
        self.corp_standing = 0.0     # e.g., Caldari Navy for Jita
        
        # Character info
        self.in_npc_corp = True
        self.can_place_remote_orders = False
    
    def calculate_broker_fee(self) -> float:
        """
        Calculate broker fee percentage
        Base: 3.0%
        -0.1% per level of Broker Relations
        -0.03% per point of faction standing
        -0.02% per point of corp standing
        """
        base_fee = 3.0
        fee = base_fee - (0.1 * self.broker_relations)
        fee -= (0.03 * self.faction_standing)
        fee -= (0.02 * self.corp_standing)
        return max(fee, 0.5)  # Minimum 0.5%
    
    def calculate_sales_tax(self) -> float:
        """
        Calculate sales tax percentage
        Base: 8.0%
        -0.11% per level of Accounting (max 5 levels = 5.5% reduction)
        Minimum: 2.5% (with Accounting V + special conditions)
        """
        base_tax = 8.0
        tax = base_tax - (0.11 * self.accounting)
        return max(tax, 2.5)
    
    def calculate_margin_trading_benefit(self) -> float:
        """
        Calculate escrow reduction from Margin Trading
        Reduces upfront ISK needed for buy orders
        -25% per level (0% to -100%)
        """
        return 25.0 * self.margin_trading
    
    def get_max_active_orders(self) -> int:
        """Calculate maximum number of active market orders"""
        base = 5
        from_trade = self.trade * 4          # Trade: +4 per level
        from_retail = self.retail * 8        # Retail: +8 per level
        from_wholesale = self.wholesale * 16  # Wholesale: +16 per level
        from_tycoon = self.tycoon * 32       # Tycoon: +32 per level
        return base + from_trade + from_retail + from_wholesale + from_tycoon
    
    def calculate_real_profit(self, buy_price: float, sell_price: float) -> Tuple[float, float, float]:
        """
        Calculate real profit after fees
        Returns: (net_profit_per_unit, net_profit_margin_percent, total_fees)
        """
        broker_fee_pct = self.calculate_broker_fee()
        sales_tax_pct = self.calculate_sales_tax()
        
        # Fees on buy order placement
        buy_broker_fee = buy_price * (broker_fee_pct / 100)
        
        # Fees on sell order
        sell_broker_fee = sell_price * (broker_fee_pct / 100)
        sales_tax = sell_price * (sales_tax_pct / 100)
        
        total_fees = buy_broker_fee + sell_broker_fee + sales_tax
        net_profit = sell_price - buy_price - total_fees
        net_margin = (net_profit / sell_price) * 100 if sell_price > 0 else 0
        
        return net_profit, net_margin, total_fees
    
    def get_hauling_capacity(self) -> str:
        """Get hauling capability description"""
        if self.jump_freighter > 0:
            return "Jump Freighter (320,000-365,000 m³, can bypass gates)"
        elif self.freighter > 0:
            return "Freighter (435,000-1,100,000 m³)"
        elif self.transport_ship > 0:
            return "Transport Ship (60,000-70,000 m³, faster than freighter)"
        else:
            return "Basic hauler (limited to ~20,000 m³)"
    
    def can_do_station_trading(self) -> bool:
        """Check if profitable station trading is possible"""
        broker_fee = self.calculate_broker_fee()
        sales_tax = self.calculate_sales_tax()
        total_cost = (broker_fee * 2) + sales_tax  # Buy + sell broker fees + tax
        return total_cost < 5.0  # Need margins > 5% to be worthwhile
    
    def can_do_arbitrage_trading(self) -> bool:
        """Check if arbitrage trading is viable"""
        return self.transport_ship > 0 or self.freighter > 0 or self.capital > 500_000_000
    
    def can_do_manufacturing(self) -> bool:
        """Check if manufacturing is viable"""
        return self.industry > 0 and self.capital > 100_000_000
    
    def can_do_refining(self) -> bool:
        """Check if ore/ice refining is viable"""
        return self.reprocessing >= 4 and self.reprocessing_efficiency >= 4
    
    def get_refining_yield(self) -> float:
        """Calculate base refining yield percentage"""
        if self.reprocessing == 0:
            return 0.0
        # Base 50% + 3% per Reprocessing level + 2% per Reprocessing Efficiency level
        # This is simplified - actual yield also depends on station and implants
        base = 50.0
        from_reprocessing = self.reprocessing * 3.0
        from_efficiency = self.reprocessing_efficiency * 2.0
        return min(base + from_reprocessing + from_efficiency, 90.0)
    
    def can_do_reactions(self) -> bool:
        """Check if moon reactions are viable"""
        return self.reactions >= 4 and self.capital > 500_000_000
    
    def can_do_pi(self) -> bool:
        """Check if Planetary Interaction is set up"""
        return self.command_center_upgrades > 0
    
    def get_max_pi_planets(self) -> int:
        """Get maximum planets for PI"""
        base = 1
        from_interplanetary = self.interplanetary_consolidation
        return base + from_interplanetary
    
    def can_do_mining(self) -> bool:
        """Check if mining is viable"""
        return self.mining >= 3 and (self.mining_barge > 0 or self.exhumers > 0)
    
    def get_mining_capability(self) -> str:
        """Get mining ship capability"""
        if self.exhumers > 0:
            return f"Exhumer (Hulk/Mackinaw/Skiff) - Best yield"
        elif self.mining_barge > 0:
            return f"Mining Barge (Procurer/Retriever/Covetor)"
        elif self.mining >= 3:
            return f"Venture or Mining Frigate - Basic mining"
        return "No mining capability"
    
    def can_do_ice_mining(self) -> bool:
        """Check if ice mining is trained"""
        return self.ice_harvesting > 0
    
    def can_do_gas_mining(self) -> bool:
        """Check if gas huffing is trained"""
        return self.gas_cloud_harvesting > 0
    
    def can_do_exploration(self) -> bool:
        """Check if exploration is viable"""
        return (self.archaeology > 0 or self.hacking > 0) and self.astrometrics >= 3
    
    def get_exploration_capability(self) -> str:
        """Get exploration capability description"""
        if self.covert_ops_ship > 0 and self.cloaking > 0:
            return "Covert Ops (null-sec capable, cloaky)"
        elif self.archaeology > 0 or self.hacking > 0:
            return "Basic exploration (high-sec/low-sec)"
        return "No exploration capability"
    
    def can_do_combat(self) -> bool:
        """Check if combat is viable"""
        has_weapons = (self.gunnery >= 3 or self.missile_launcher_operation >= 3 or self.drones >= 3)
        has_ship = (self.cruiser >= 3 or self.battlecruiser > 0 or self.battleship > 0)
        return has_weapons and has_ship
    
    def get_combat_capability(self) -> str:
        """Get combat capability description"""
        ships = []
        if self.marauders > 0:
            ships.append("Marauder (L4 missions, high DPS)")
        if self.battleship >= 4:
            ships.append("Battleship (L4 missions)")
        if self.heavy_assault_cruisers > 0:
            ships.append("HAC (Abyssal/PvP)")
        if self.command_ships > 0:
            ships.append("Command Ship (Fleet boosts)")
        if self.battlecruiser >= 4:
            ships.append("Battlecruiser (L3 missions)")
        if self.cruiser >= 4:
            ships.append("Cruiser (L2-L3 missions)")
        
        weapons = []
        if self.gunnery >= 4:
            weapons.append("Guns")
        if self.missile_launcher_operation >= 4:
            weapons.append("Missiles")
        if self.drones >= 4:
            weapons.append("Drones")
        
        ship_str = " or ".join(ships) if ships else "Basic combat ships"
        weapon_str = "/".join(weapons) if weapons else "Basic weapons"
        
        return f"{ship_str} with {weapon_str}"
    
    def can_do_salvaging(self) -> bool:
        """Check if salvaging is trained"""
        return self.salvaging > 0
    
    def save_profile(self, filename=None):
        """Save profile to JSON file"""
        path = Path(filename) if filename else PROFILE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        # Get all skill attributes dynamically
        skills = {}
        for attr in dir(self):
            if not attr.startswith('_') and attr not in ['name', 'capital', 'faction_standing', 'corp_standing', 'in_npc_corp', 'can_place_remote_orders']:
                value = getattr(self, attr)
                if isinstance(value, (int, float)) and not callable(value):
                    skills[attr] = value
        
        data = {
            'name': self.name,
            'capital': self.capital,
            'assets': self.assets,  # Save raw assets
            'blueprints': self.blueprints,  # Save owned blueprints
            'skills': skills,
            'standings': {
                'faction': self.faction_standing,
                'corp': self.corp_standing,
            },
            'info': {
                'in_npc_corp': self.in_npc_corp,
            }
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\n✓ Profile saved to {path}")
    
    def load_profile(self, filename=None) -> bool:
        """Load profile from JSON file"""
        path = Path(filename) if filename else PROFILE_FILE
        if not path.exists():
            return False

        with open(path, 'r') as f:
            data = json.load(f)
        
        self.name = data.get('name', '')
        self.capital = data.get('capital', 0.0)
        self.assets = data.get('assets', [])  # Load raw assets
        self.blueprints = data.get('blueprints', [])  # Load owned blueprints
        
        # Load all skills dynamically
        skills = data.get('skills', {})
        for skill_name, skill_value in skills.items():
            if hasattr(self, skill_name):
                setattr(self, skill_name, skill_value)
        
        standings = data.get('standings', {})
        self.faction_standing = standings.get('faction', 0.0)
        self.corp_standing = standings.get('corp', 0.0)
        
        info = data.get('info', {})
        self.in_npc_corp = info.get('in_npc_corp', True)
        
        return True


def load_profile_or_exit() -> "CharacterProfile":
    """Load the saved character profile or exit with a helpful message."""
    profile = CharacterProfile()
    if not profile.load_profile():
        print("\n✗ No character profile found!")
        print("Run 'python 3_refresh_user_profile.py' first to generate your profile.")
        sys.exit(1)
    return profile


def format_isk(amount: float) -> str:
    """Format ISK amount with commas"""
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:,.2f}B"
    elif amount >= 1_000_000:
        return f"{amount / 1_000_000:,.2f}M"
    elif amount >= 1_000:
        return f"{amount / 1_000:,.2f}K"
    else:
        return f"{amount:,.2f}"


def generate_profile_report(profile: CharacterProfile):
    """Generate comprehensive character profile report"""
    
    print("\n" + "=" * 80)
    print(f"CHARACTER PROFILE REPORT - {profile.name}")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Capital
    print(f"\n💰 AVAILABLE CAPITAL")
    print(f"   {format_isk(profile.capital)} ISK")
    
    # Trading Fees
    print(f"\n📊 TRADING COSTS")
    broker_fee = profile.calculate_broker_fee()
    sales_tax = profile.calculate_sales_tax()
    print(f"   Broker Fee: {broker_fee:.2f}% (base 3.0%)")
    print(f"   Sales Tax: {sales_tax:.2f}% (base 8.0%)")
    print(f"   Total Cost per Trade: {(broker_fee * 2 + sales_tax):.2f}%")
    
    margin_benefit = profile.calculate_margin_trading_benefit()
    if margin_benefit > 0:
        print(f"   Margin Trading Escrow: {100 - margin_benefit:.0f}% (save {margin_benefit:.0f}%)")
    
    # Market Orders
    print(f"\n📋 MARKET ORDERS")
    max_orders = profile.get_max_active_orders()
    print(f"   Maximum Active Orders: {max_orders}")
    if profile.daytrading > 0:
        print(f"   Day Trading: Level {profile.daytrading} (place orders remotely)")
    
    # Trading Viability
    print(f"\n✓ TRADING OPPORTUNITIES")
    
    can_station_trade = profile.can_do_station_trading()
    if can_station_trade:
        print(f"   ✓ Station Trading: PROFITABLE")
        print(f"     → Minimum margin needed: {(broker_fee * 2 + sales_tax):.2f}%")
        print(f"     → Recommended margin: >{(broker_fee * 2 + sales_tax + 2):.2f}%")
    else:
        print(f"   ✗ Station Trading: NOT RECOMMENDED (fees too high)")
        print(f"     → Your costs: {(broker_fee * 2 + sales_tax):.2f}%")
        print(f"     → Train Broker Relations and Accounting!")
    
    can_arbitrage = profile.can_do_arbitrage_trading()
    if can_arbitrage:
        print(f"   ✓ Arbitrage Trading: VIABLE")
        print(f"     → Hauling: {profile.get_hauling_capacity()}")
    else:
        print(f"   ✗ Arbitrage Trading: LIMITED (need better hauling or more capital)")
    
    can_manufacture = profile.can_do_manufacturing()
    if can_manufacture:
        print(f"   ✓ Manufacturing: POSSIBLE")
        print(f"     → Industry: Level {profile.industry}")
        if profile.mass_production > 0:
            print(f"     → Mass Production: Level {profile.mass_production}")
        if profile.production_efficiency > 0:
            print(f"     → Production Efficiency: Level {profile.production_efficiency}")
    
    can_refine = profile.can_do_refining()
    if can_refine:
        yield_pct = profile.get_refining_yield()
        print(f"   ✓ Ore/Ice Refining: VIABLE")
        print(f"     → Base yield: {yield_pct:.1f}% (station bonuses add more)")
        print(f"     → Reprocessing: {profile.reprocessing}, Efficiency: {profile.reprocessing_efficiency}")
    elif profile.reprocessing > 0:
        print(f"   ~ Ore/Ice Refining: PARTIAL")
        print(f"     → Train Reprocessing and Reprocessing Efficiency to IV+")
    
    can_reactions_trade = profile.can_do_reactions()
    if can_reactions_trade:
        print(f"   ✓ Moon Reactions: VIABLE")
        print(f"     → Reactions: Level {profile.reactions}")
    elif profile.reactions > 0:
        print(f"   ~ Moon Reactions: LEARNING")
        print(f"     → Need more capital and higher skills")
    
    can_pi = profile.can_do_pi()
    if can_pi:
        max_planets = profile.get_max_pi_planets()
        print(f"   ✓ Planetary Interaction (PI): ACTIVE")
        print(f"     → Max planets: {max_planets}")
        print(f"     → Command Centers: Level {profile.command_center_upgrades}")
        if profile.planetology > 0 or profile.advanced_planetology > 0:
            print(f"     → Planetology: {profile.planetology}, Advanced: {profile.advanced_planetology}")
    
    # Mining
    can_mine = profile.can_do_mining()
    if can_mine:
        print(f"   ✓ Mining: ACTIVE")
        print(f"     → {profile.get_mining_capability()}")
        if profile.ice_harvesting > 0:
            print(f"     → Ice Harvesting: Level {profile.ice_harvesting}")
        if profile.gas_cloud_harvesting > 0:
            print(f"     → Gas Huffing: Level {profile.gas_cloud_harvesting}")
    elif profile.mining >= 3:
        print(f"   ~ Mining: BASIC")
        print(f"     → Train Mining Barge or Exhumer skills")
    
    # Exploration
    can_explore = profile.can_do_exploration()
    if can_explore:
        print(f"   ✓ Exploration: VIABLE")
        print(f"     → {profile.get_exploration_capability()}")
        if profile.salvaging > 0:
            print(f"     → Salvaging: Level {profile.salvaging}")
    
    # Combat/Missions
    can_combat = profile.can_do_combat()
    if can_combat:
        print(f"   ✓ Combat/Missions: CAPABLE")
        print(f"     → {profile.get_combat_capability()}")
    
    # Example Profit Calculations
    print(f"\n💵 PROFIT CALCULATOR (Real Numbers)")
    print(f"   Example: Item costs 10,000 ISK to buy, sells for 11,000 ISK")
    
    net_profit, net_margin, total_fees = profile.calculate_real_profit(10000, 11000)
    print(f"   Gross Profit: 1,000 ISK (10.0%)")
    print(f"   Your Fees: {total_fees:.2f} ISK")
    print(f"   Net Profit: {net_profit:.2f} ISK ({net_margin:.2f}%)")
    
    if net_profit > 0:
        print(f"   → On 100 units: {format_isk(net_profit * 100)} ISK profit")
        print(f"   → On 1,000 units: {format_isk(net_profit * 1000)} ISK profit")
    else:
        print(f"   ⚠️  YOU LOSE MONEY on this trade! Improve your skills!")
    
    # Recommended investments
    print(f"\n💡 RECOMMENDED INVESTMENTS")
    
    if profile.capital < 100_000_000:
        print(f"   • Start with small station trading (< 10M per order)")
        print(f"   • Focus on high-volume, low-margin items")
    elif profile.capital < 1_000_000_000:
        print(f"   • Medium station trading (10-100M per order)")
        print(f"   • Consider arbitrage with transport ship")
    else:
        print(f"   • Large-scale station trading")
        print(f"   • Arbitrage with freighter")
        print(f"   • Manufacturing with significant capital")
    
    # Skill recommendations
    print(f"\n🎓 SKILL TRAINING PRIORITIES")
    priorities = []
    
    # Trading skills
    if profile.broker_relations < 5:
        priority = 5 - profile.broker_relations
        priorities.append((priority * 10, f"Broker Relations to V (save {0.1 * (5 - profile.broker_relations):.1f}% fees)"))
    
    if profile.accounting < 5:
        priority = 5 - profile.accounting
        priorities.append((priority * 10, f"Accounting to V (save {0.11 * (5 - profile.accounting):.2f}% tax)"))
    
    if profile.margin_trading < 4 and can_station_trade:
        priorities.append((8, "Margin Trading to IV (save 100% escrow on buy orders)"))
    
    if max_orders < 100 and can_station_trade:
        priorities.append((7, "Trade/Retail skills (increase active orders)"))
    
    if profile.transport_ship == 0 and can_arbitrage:
        priorities.append((6, "Transport Ships (enable better arbitrage)"))
    
    # Industry skills
    if can_manufacture:
        if profile.production_efficiency < 5:
            priorities.append((9, "Production Efficiency to V (reduce materials needed)"))
        if profile.mass_production < 5:
            priorities.append((7, f"Mass Production to V (currently {profile.mass_production})"))
        if profile.advanced_industry < 5 and profile.industry >= 5:
            priorities.append((6, "Advanced Industry (reduce manufacturing time)"))
    
    # Refining skills
    if profile.reprocessing > 0 and not can_refine:
        if profile.reprocessing < 5:
            priorities.append((8, f"Reprocessing to V (improve ore/ice yield)"))
        if profile.reprocessing_efficiency < 5:
            priorities.append((8, f"Reprocessing Efficiency to V (improve yield)"))
    
    # PI skills
    if profile.command_center_upgrades > 0:
        if profile.command_center_upgrades < 5:
            priorities.append((5, f"Command Center Upgrades to V (more PI production)"))
        if profile.interplanetary_consolidation < 5:
            priorities.append((6, f"Interplanetary Consolidation to V (more planets = more ISK)"))
        if profile.planetology < 5 or profile.advanced_planetology < 5:
            priorities.append((4, "Planetology skills (find better planets)"))
    
    priorities.sort(reverse=True)
    
    for i, (_, skill) in enumerate(priorities[:7], 1):
        print(f"   {i}. {skill}")
    
    # Standing recommendations
    if profile.faction_standing < 5.0:
        print(f"\n🏛️  STANDING IMPROVEMENTS")
        print(f"   • Faction Standing: {profile.faction_standing:.1f}/10.0")
        print(f"   • Each point reduces broker fee by 0.03%")
        print(f"   • Consider running missions to improve standings")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    print("This module is meant to be imported.")
    print("Run 'python 3_refresh_user_profile.py' to automatically generate your profile.")
