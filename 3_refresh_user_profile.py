"""
==============================================================================
STEP 3: Character Profile Setup
==============================================================================
Authenticates with EVE Online and fetches your character data:
- Skills (trading, industry, mining, combat, etc.)
- Wallet balance
- Current location
- Assets and blueprints
- Corporation standings

Run this:
- ONCE during initial setup
- Anytime you want to refresh your character data
- After learning new skills or acquiring blueprints

Requires: EVE Developer Application (see SETUP_API.md)
Estimated time: 2-5 minutes (includes ESI authentication)
==============================================================================
"""

import os
import sys
from tools.character_model import CharacterProfile, generate_profile_report, format_isk
from tools.esi_auth import ESIAuth, load_client_credentials, save_client_credentials, setup_esi_credentials
from tools.config import ESI_TOKENS_FILE


# Skill type IDs from EVE database
SKILL_TYPE_IDS = {
    # Trade skills
    'broker_relations': 3446,
    'accounting': 16622,
    'margin_trading': 16597,
    'trade': 3443,
    'retail': 3444,
    'wholesale': 18580,
    'tycoon': 3361,
    'daytrading': 33467,
    
    # Hauling skills
    'transport_ships': 3756,
    'caldari_freighter': 20342,
    'gallente_freighter': 20526,
    'amarr_freighter': 20527,
    'minmatar_freighter': 20528,
    'jump_freighters': 28374,
    
    # Industry skills
    'industry': 3380,
    'mass_production': 3387,
    'advanced_industry': 28585,
    'production_efficiency': 3388,
    
    # Science/Invention skills
    'science': 3402,
    'metallurgy': 3409,
    'research': 3403,
    'laboratory_operation': 3406,
    
    # Refining skills
    'reprocessing': 3385,
    'reprocessing_efficiency': 3389,
    'scrapmetal_processing': 12196,
    
    # Reactions
    'reactions': 45746,
    'mass_reactions': 46156,
    
    # Planetary Interaction
    'planetology': 2406,
    'advanced_planetology': 2495,
    'command_center_upgrades': 2505,
    'interplanetary_consolidation': 2494,
    
    # Mining Skills
    'mining': 3386,
    'ice_harvesting': 16281,
    'gas_cloud_harvesting': 25544,
    'mining_upgrades': 3396,
    'mining_frigate': 32918,
    'mining_barge': 17940,
    'exhumers': 22551,
    'expedition_frigates': 33856,
    'deep_core_mining': 11395,
    'astrogeology': 3410,
    
    # Exploration Skills
    'archaeology': 13278,
    'hacking': 21718,
    'salvaging': 25863,
    'astrometrics': 3412,
    'astrometric_rangefinding': 25739,
    'astrometric_acquisition': 25810,
    'astrometric_pinpointing': 25811,
    'cloaking': 3566,
    'covert_ops': 12098,
    
    # Combat - Gunnery
    'gunnery': 3300,
    'small_hybrid_turret': 3301,
    'medium_hybrid_turret': 3302,
    'large_hybrid_turret': 3303,
    'small_projectile_turret': 3304,
    'medium_projectile_turret': 3305,
    'large_projectile_turret': 3306,
    'small_energy_turret': 3307,
    'medium_energy_turret': 3308,
    'large_energy_turret': 3309,
    'motion_prediction': 3310,
    'rapid_firing': 3311,
    'sharpshooter': 3312,
    'surgical_strike': 3315,
    'controlled_bursts': 3316,
    'weapon_upgrades': 3318,
    'advanced_weapon_upgrades': 11207,
    
    # Combat - Missiles
    'missile_launcher_operation': 3319,
    'light_missiles': 3320,
    'heavy_missiles': 3324,
    'cruise_missiles': 3325,
    'torpedoes': 3326,
    'rockets': 3321,
    'rapid_launch': 3327,
    'warhead_upgrades': 20209,
    'guided_missile_precision': 20312,
    'missile_bombardment': 12441,
    'missile_projection': 20314,
    
    # Combat - Drones
    'drones': 3436,
    'light_drone_operation': 3437,
    'medium_drone_operation': 3442,
    'heavy_drone_operation': 3441,
    'drone_avionics': 3439,
    'drone_interfacing': 3442,
    'drone_navigation': 12305,
    'drone_durability': 3440,
    'combat_drone_operation': 23606,
    'sentry_drone_interfacing': 23594,
    'fighters': 23069,
    'fighter_hangar_management': 40573,
    
    # Ship Skills - Frigates
    'caldari_frigate': 3330,
    'gallente_frigate': 3328,
    'minmatar_frigate': 3329,
    'amarr_frigate': 3331,
    'assault_frigates': 3331,
    'interceptors': 12092,
    'covert_ops': 12093,
    'electronic_attack_ships': 33095,
    
    # Ship Skills - Destroyers
    'caldari_destroyer': 33091,
    'gallente_destroyer': 33092,
    'minmatar_destroyer': 33093,
    'amarr_destroyer': 33094,
    'tactical_destroyers': 33095,
    'command_destroyers': 33699,
    
    # Ship Skills - Cruisers
    'caldari_cruiser': 3335,
    'gallente_cruiser': 3333,
    'minmatar_cruiser': 3334,
    'amarr_cruiser': 3336,
    'heavy_assault_cruisers': 16591,
    'logistics_cruisers': 11567,
    'recon_ships': 22761,
    'heavy_interdiction_cruisers': 28615,
    'combat_recon_ships': 33095,
    
    # Ship Skills - Battlecruisers
    'caldari_battlecruiser': 419,
    'gallente_battlecruiser': 420,
    'minmatar_battlecruiser': 418,
    'amarr_battlecruiser': 3335,
    'command_ships': 3348,
    'strategic_cruisers': 30650,
    
    # Ship Skills - Battleships
    'caldari_battleship': 3339,
    'gallente_battleship': 3337,
    'minmatar_battleship': 3338,
    'amarr_battleship': 3340,
    'marauders': 28667,
    'black_ops': 28656,
    
    # Ship Skills - Industrial
    'caldari_industrial': 20342,
    'gallente_industrial': 20526,
    'minmatar_industrial': 20527,
    'amarr_industrial': 20528,
    'mining_frigate': 32918,
    'mining_barge': 17940,
    'exhumers': 22551,
    
    # Ship Skills - Capitals
    'caldari_carrier': 24311,
    'gallente_carrier': 24312,
    'minmatar_carrier': 24313,
    'amarr_carrier': 24314,
    'caldari_dreadnought': 20525,
    'gallente_dreadnought': 20530,
    'minmatar_dreadnought': 20531,
    'amarr_dreadnought': 20532,
    'capital_ships': 20533,
    
    # Support Skills
    'hull_upgrades': 3394,
    'mechanics': 3392,
    'shield_management': 3416,
    'shield_operation': 3413,
    'tactical_shield_manipulation': 11566,
    'capacitor_management': 3418,
    'capacitor_systems_operation': 3417,
    'energy_grid_upgrades': 3429,
    'cpu_management': 3426,
    'power_grid_management': 3413,
    'electronics_upgrades': 3426,
    'navigation': 3449,
    'evasive_maneuvering': 3452,
    'warp_drive_operation': 3454,
    'afterburner': 3450,
    'high_speed_maneuvering': 3453,
}

# Faction and corp IDs
FACTIONS = {
    'caldari_state': 500001,
    'amarr_empire': 500003,
    'gallente_federation': 500004,
    'minmatar_republic': 500002,
}

JITA_CORP = 1000035  # Caldari Navy (for Jita broker fees)


class AutoProfileFetcher:
    """Automatically fetch character profile from ESI"""
    
    def __init__(self, esi: ESIAuth):
        self.esi = esi
        self.profile = CharacterProfile()
    
    def fetch_skills(self) -> bool:
        """Fetch character skills"""
        print("\n📚 Fetching your skills...")
        
        skills_data = self.esi.get(f"/characters/{self.esi.character_id}/skills/")
        if not skills_data:
            print("✗ Failed to fetch skills")
            return False
        
        # Build skill ID to level mapping
        skill_map = {}
        for skill in skills_data.get('skills', []):
            skill_id = skill['skill_id']
            level = skill.get('trained_skill_level', 0)
            skill_map[skill_id] = level
        
        # Map to profile
        self.profile.broker_relations = skill_map.get(SKILL_TYPE_IDS['broker_relations'], 0)
        self.profile.accounting = skill_map.get(SKILL_TYPE_IDS['accounting'], 0)
        self.profile.margin_trading = skill_map.get(SKILL_TYPE_IDS['margin_trading'], 0)
        self.profile.trade = skill_map.get(SKILL_TYPE_IDS['trade'], 0)
        self.profile.retail = skill_map.get(SKILL_TYPE_IDS['retail'], 0)
        self.profile.wholesale = skill_map.get(SKILL_TYPE_IDS['wholesale'], 0)
        self.profile.tycoon = skill_map.get(SKILL_TYPE_IDS['tycoon'], 0)
        self.profile.daytrading = skill_map.get(SKILL_TYPE_IDS['daytrading'], 0)
        
        self.profile.transport_ship = skill_map.get(SKILL_TYPE_IDS['transport_ships'], 0)
        
        # Check for any freighter skill
        freighter_skills = [
            skill_map.get(SKILL_TYPE_IDS['caldari_freighter'], 0),
            skill_map.get(SKILL_TYPE_IDS['gallente_freighter'], 0),
            skill_map.get(SKILL_TYPE_IDS['amarr_freighter'], 0),
            skill_map.get(SKILL_TYPE_IDS['minmatar_freighter'], 0),
        ]
        self.profile.freighter = max(freighter_skills)
        
        self.profile.jump_freighter = skill_map.get(SKILL_TYPE_IDS['jump_freighters'], 0)
        
        self.profile.industry = skill_map.get(SKILL_TYPE_IDS['industry'], 0)
        self.profile.mass_production = skill_map.get(SKILL_TYPE_IDS['mass_production'], 0)
        self.profile.advanced_industry = skill_map.get(SKILL_TYPE_IDS['advanced_industry'], 0)
        self.profile.production_efficiency = skill_map.get(SKILL_TYPE_IDS['production_efficiency'], 0)
        
        # Science/Research
        self.profile.science = skill_map.get(SKILL_TYPE_IDS['science'], 0)
        self.profile.metallurgy = skill_map.get(SKILL_TYPE_IDS['metallurgy'], 0)
        self.profile.research = skill_map.get(SKILL_TYPE_IDS['research'], 0)
        self.profile.laboratory_operation = skill_map.get(SKILL_TYPE_IDS['laboratory_operation'], 0)
        
        # Refining
        self.profile.reprocessing = skill_map.get(SKILL_TYPE_IDS['reprocessing'], 0)
        self.profile.reprocessing_efficiency = skill_map.get(SKILL_TYPE_IDS['reprocessing_efficiency'], 0)
        self.profile.scrapmetal_processing = skill_map.get(SKILL_TYPE_IDS['scrapmetal_processing'], 0)
        
        # Reactions
        self.profile.reactions = skill_map.get(SKILL_TYPE_IDS['reactions'], 0)
        self.profile.mass_reactions = skill_map.get(SKILL_TYPE_IDS['mass_reactions'], 0)
        
        # Planetary Interaction
        self.profile.planetology = skill_map.get(SKILL_TYPE_IDS['planetology'], 0)
        self.profile.advanced_planetology = skill_map.get(SKILL_TYPE_IDS['advanced_planetology'], 0)
        self.profile.command_center_upgrades = skill_map.get(SKILL_TYPE_IDS['command_center_upgrades'], 0)
        self.profile.interplanetary_consolidation = skill_map.get(SKILL_TYPE_IDS['interplanetary_consolidation'], 0)
        
        # Mining Skills
        self.profile.mining = skill_map.get(SKILL_TYPE_IDS['mining'], 0)
        self.profile.ice_harvesting = skill_map.get(SKILL_TYPE_IDS['ice_harvesting'], 0)
        self.profile.gas_cloud_harvesting = skill_map.get(SKILL_TYPE_IDS['gas_cloud_harvesting'], 0)
        self.profile.mining_upgrades = skill_map.get(SKILL_TYPE_IDS['mining_upgrades'], 0)
        self.profile.mining_barge = skill_map.get(SKILL_TYPE_IDS['mining_barge'], 0)
        self.profile.exhumers = skill_map.get(SKILL_TYPE_IDS['exhumers'], 0)
        self.profile.deep_core_mining = skill_map.get(SKILL_TYPE_IDS['deep_core_mining'], 0)
        self.profile.astrogeology = skill_map.get(SKILL_TYPE_IDS['astrogeology'], 0)
        
        # Exploration Skills
        self.profile.archaeology = skill_map.get(SKILL_TYPE_IDS['archaeology'], 0)
        self.profile.hacking = skill_map.get(SKILL_TYPE_IDS['hacking'], 0)
        self.profile.salvaging = skill_map.get(SKILL_TYPE_IDS['salvaging'], 0)
        self.profile.astrometrics = skill_map.get(SKILL_TYPE_IDS['astrometrics'], 0)
        self.profile.cloaking = skill_map.get(SKILL_TYPE_IDS['cloaking'], 0)
        self.profile.covert_ops = skill_map.get(SKILL_TYPE_IDS['covert_ops'], 0)
        
        # Combat - General
        self.profile.gunnery = skill_map.get(SKILL_TYPE_IDS['gunnery'], 0)
        self.profile.missile_launcher_operation = skill_map.get(SKILL_TYPE_IDS['missile_launcher_operation'], 0)
        self.profile.drones = skill_map.get(SKILL_TYPE_IDS['drones'], 0)
        
        # Ship Skills - Take highest across all races
        self.profile.frigate = max([
            skill_map.get(SKILL_TYPE_IDS['caldari_frigate'], 0),
            skill_map.get(SKILL_TYPE_IDS['gallente_frigate'], 0),
            skill_map.get(SKILL_TYPE_IDS['minmatar_frigate'], 0),
            skill_map.get(SKILL_TYPE_IDS['amarr_frigate'], 0),
        ])
        
        self.profile.destroyer = max([
            skill_map.get(SKILL_TYPE_IDS['caldari_destroyer'], 0),
            skill_map.get(SKILL_TYPE_IDS['gallente_destroyer'], 0),
            skill_map.get(SKILL_TYPE_IDS['minmatar_destroyer'], 0),
            skill_map.get(SKILL_TYPE_IDS['amarr_destroyer'], 0),
        ])
        
        self.profile.cruiser = max([
            skill_map.get(SKILL_TYPE_IDS['caldari_cruiser'], 0),
            skill_map.get(SKILL_TYPE_IDS['gallente_cruiser'], 0),
            skill_map.get(SKILL_TYPE_IDS['minmatar_cruiser'], 0),
            skill_map.get(SKILL_TYPE_IDS['amarr_cruiser'], 0),
        ])
        
        self.profile.battlecruiser = max([
            skill_map.get(SKILL_TYPE_IDS['caldari_battlecruiser'], 0),
            skill_map.get(SKILL_TYPE_IDS['gallente_battlecruiser'], 0),
            skill_map.get(SKILL_TYPE_IDS['minmatar_battlecruiser'], 0),
            skill_map.get(SKILL_TYPE_IDS['amarr_battlecruiser'], 0),
        ])
        
        self.profile.battleship = max([
            skill_map.get(SKILL_TYPE_IDS['caldari_battleship'], 0),
            skill_map.get(SKILL_TYPE_IDS['gallente_battleship'], 0),
            skill_map.get(SKILL_TYPE_IDS['minmatar_battleship'], 0),
            skill_map.get(SKILL_TYPE_IDS['amarr_battleship'], 0),
        ])
        
        self.profile.industrial = max([
            skill_map.get(SKILL_TYPE_IDS['caldari_industrial'], 0),
            skill_map.get(SKILL_TYPE_IDS['gallente_industrial'], 0),
            skill_map.get(SKILL_TYPE_IDS['minmatar_industrial'], 0),
            skill_map.get(SKILL_TYPE_IDS['amarr_industrial'], 0),
        ])
        
        # Specialized Ships
        self.profile.assault_frigates = skill_map.get(SKILL_TYPE_IDS['assault_frigates'], 0)
        self.profile.interceptors = skill_map.get(SKILL_TYPE_IDS['interceptors'], 0)
        self.profile.covert_ops_ship = skill_map.get(SKILL_TYPE_IDS['covert_ops'], 0)
        self.profile.heavy_assault_cruisers = skill_map.get(SKILL_TYPE_IDS['heavy_assault_cruisers'], 0)
        self.profile.logistics_cruisers = skill_map.get(SKILL_TYPE_IDS['logistics_cruisers'], 0)
        self.profile.recon_ships = skill_map.get(SKILL_TYPE_IDS['recon_ships'], 0)
        self.profile.command_ships = skill_map.get(SKILL_TYPE_IDS['command_ships'], 0)
        self.profile.marauders = skill_map.get(SKILL_TYPE_IDS['marauders'], 0)
        self.profile.black_ops_ship = skill_map.get(SKILL_TYPE_IDS['black_ops'], 0)
        
        self.profile.carriers = max([
            skill_map.get(SKILL_TYPE_IDS['caldari_carrier'], 0),
            skill_map.get(SKILL_TYPE_IDS['gallente_carrier'], 0),
            skill_map.get(SKILL_TYPE_IDS['minmatar_carrier'], 0),
            skill_map.get(SKILL_TYPE_IDS['amarr_carrier'], 0),
        ])
        
        self.profile.dreadnoughts = max([
            skill_map.get(SKILL_TYPE_IDS['caldari_dreadnought'], 0),
            skill_map.get(SKILL_TYPE_IDS['gallente_dreadnought'], 0),
            skill_map.get(SKILL_TYPE_IDS['minmatar_dreadnought'], 0),
            skill_map.get(SKILL_TYPE_IDS['amarr_dreadnought'], 0),
        ])
        
        print("✓ Skills loaded")
        return True
    
    def fetch_wallet(self) -> bool:
        """Fetch character wallet balance"""
        print("💰 Fetching your wallet...")
        
        wallet = self.esi.get(f"/characters/{self.esi.character_id}/wallet/")
        if wallet is None:
            print("✗ Failed to fetch wallet")
            return False
        
        self.profile.capital = float(wallet)
        print(f"✓ Wallet balance: {format_isk(self.profile.capital)} ISK")
        return True
    
    def fetch_standings(self) -> bool:
        """Fetch character standings"""
        print("🏛️  Fetching your standings...")
        
        standings = self.esi.get(f"/characters/{self.esi.character_id}/standings/")
        if not standings:
            print("✗ Failed to fetch standings")
            return False
        
        # Look for relevant faction and corp standings
        for standing in standings:
            from_type = standing.get('from_type')
            from_id = standing.get('from_id')
            value = standing.get('standing', 0.0)
            
            # Check for major trade factions (use highest)
            if from_type == 'faction' and from_id in FACTIONS.values():
                self.profile.faction_standing = max(self.profile.faction_standing, value)
            
            # Check for Jita corp (Caldari Navy)
            if from_type == 'npc_corp' and from_id == JITA_CORP:
                self.profile.corp_standing = value
        
        print(f"✓ Best faction standing: {self.profile.faction_standing:.2f}")
        print(f"✓ Jita corp standing: {self.profile.corp_standing:.2f}")
        return True
    
    def fetch_all(self) -> CharacterProfile:
        """Fetch all character data"""
        self.profile.name = self.esi.character_name
        
        print("\n" + "=" * 80)
        print(f"FETCHING CHARACTER DATA: {self.profile.name}")
        print("=" * 80)
        
        success = True
        success = self.fetch_skills() and success
        success = self.fetch_wallet() and success
        success = self.fetch_standings() and success
        success = self.fetch_assets() and success
        
        if success:
            print("\n✓ All data fetched successfully!")
        else:
            print("\n⚠️  Some data could not be fetched. Profile may be incomplete.")
        
        return self.profile
    
    def fetch_assets(self) -> bool:
        """Fetch all character assets from ESI (no filtering)"""
        print("\n📦 Fetching assets from ESI...")
        
        try:
            # Fetch all assets - let consuming scripts do their own filtering
            assets = self.esi.get_character_assets()
            
            if not assets:
                print("   ⚠️  No assets returned from ESI")
                print("   This could mean:")
                print("     - Your character has no assets")
                print("     - The ESI scope 'esi-assets.read_assets.v1' was not granted")
                print("     - Token needs to be refreshed")
                print("\n   💡 Try deleting 'cache/user/esi_tokens.json' and re-authenticating with:")
                print("      python 3_refresh_user_profile.py")
                self.profile.assets = []
                return True  # Don't fail
            
            print(f"   ✓ Fetched {len(assets)} total assets")
            
            # Save raw assets - consuming scripts will filter as needed
            self.profile.assets = assets
            print(f"   ✓ Asset data saved to profile")
            
            return True
        except Exception as e:
            print(f"   ✗ Failed to fetch blueprints: {e}")
            import traceback
            traceback.print_exc()
            self.profile.blueprints = []
            return False


def main():
    """Main function"""
    print("\n" + "=" * 80)
    print("STEP 3: Character Profile Setup")
    print("=" * 80)
    print("Fetches your character data directly from EVE Online")
    print("=" * 80)
    
    # Setup credentials
    client_id, client_secret = setup_esi_credentials()
    
    if not client_id or not client_secret:
        print("\n✗ No credentials provided. Exiting.")
        return
    
    # Initialize ESI auth
    esi = ESIAuth(client_id, client_secret)
    
    # Try to load existing tokens
    if ESI_TOKENS_FILE.exists():
        print("\nTrying to use saved authentication...")
        if esi.load_tokens():
            print(f"✓ Authenticated as: {esi.character_name}")
        else:
            print("✗ Saved tokens expired, need to re-authenticate")
            if not esi.authenticate():
                print("\n✗ Authentication failed")
                return
            esi.save_tokens()
    else:
        # Authenticate
        if not esi.authenticate():
            print("\n✗ Authentication failed")
            return
        esi.save_tokens()
    
    # Fetch character data
    fetcher = AutoProfileFetcher(esi)
    profile = fetcher.fetch_all()
    
    # Save profile
    profile.save_profile()
    
    # Generate report
    generate_profile_report(profile)
    
    print("\n" + "=" * 80)
    print("✓ STEP 3 COMPLETE!")
    print("=" * 80)
    print("\nYour character profile has been saved to 'cache/user/character_profile.json'")
    print("\nYou can now use the functional tools:")
    print("  • python A_manufacturing_optimizer.py --target \"<item>\"")
    print("  • python B_trading_route_finder.py")
    print("  • python C_eve_market_analyzer.py")
    print("\nRe-run 3_refresh_user_profile.py anytime to update your data")
    print("\no7 Fly safe!")


if __name__ == "__main__":
    main()
