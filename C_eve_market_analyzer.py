"""
==============================================================================
EVE Online Market Analyzer
==============================================================================
Finds profitable trading opportunities between major trade hubs
- Compares prices across Jita, Amarr, Dodixie, Rens, Hek
- Shows arbitrage opportunities
- Calculates profit margins

Usage:
  python C_eve_market_analyzer.py
  (Script will scan popular items across all hubs)

Note: This is a simpler alternative to B_trading_route_finder.py
Requires: Internet connection (uses ESI API)
==============================================================================
"""

import requests
import time
from typing import List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime
from tools.character_model import format_isk
from tools.config import ESI_BASE

# Major trade hubs with their station IDs
TRADE_HUBS = {
    "Jita": 60003760,      # Jita IV - Moon 4 - Caldari Navy Assembly Plant
    "Amarr": 60008494,     # Amarr VIII (Oris) - Emperor Family Academy
    "Dodixie": 60011866,   # Dodixie IX - Moon 20 - Federation Navy Assembly Plant
    "Rens": 60004588,      # Rens VI - Moon 8 - Brutor Tribe Treasury
    "Hek": 60005686,       # Hek VIII - Moon 12 - Boundless Creation Factory
}

# Popular tradeable items (Type IDs) - you can add more
POPULAR_ITEMS = {
    "PLEX": 44992,
    "Tritanium": 34,
    "Pyerite": 35,
    "Mexallon": 36,
    "Isogen": 37,
    "Nocxium": 38,
    "Zydrine": 39,
    "Megacyte": 40,
    "Morphite": 11399,
}


@dataclass
class MarketOpportunity:
    """Represents a profitable market opportunity"""
    item_name: str
    item_id: int
    buy_hub: str
    sell_hub: str
    buy_price: float
    sell_price: float
    profit_per_unit: float
    profit_margin: float
    buy_volume: int
    sell_volume: int


class EVEMarketAnalyzer:
    """Analyzes EVE Online market data for profit opportunities"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'EVE Market Analyzer'
        })
    
    def get_market_orders(self, region_id: int, type_id: int) -> List[Dict]:
        """Fetch market orders for an item in a region"""
        url = f"{ESI_BASE}/markets/{region_id}/orders/"
        params = {
            'datasource': 'tranquility',
            'order_type': 'all',
            'type_id': type_id
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching market data: {e}")
            return []
    
    def get_station_orders(self, orders: List[Dict], station_id: int) -> Tuple[float, float, int, int]:
        """
        Get best buy and sell prices at a station
        Returns: (best_buy_price, best_sell_price, buy_volume, sell_volume)
        """
        station_orders = [o for o in orders if o.get('location_id') == station_id]
        
        buy_orders = [o for o in station_orders if o['is_buy_order']]
        sell_orders = [o for o in station_orders if not o['is_buy_order']]
        
        best_buy = max([o['price'] for o in buy_orders], default=0)
        best_sell = min([o['price'] for o in sell_orders], default=0)
        
        buy_volume = sum([o['volume_remain'] for o in buy_orders])
        sell_volume = sum([o['volume_remain'] for o in sell_orders])
        
        return best_buy, best_sell, buy_volume, sell_volume
    
    def analyze_arbitrage(self, item_name: str, item_id: int, region_id: int = 10000002) -> List[MarketOpportunity]:
        """
        Find arbitrage opportunities for an item across trade hubs
        Default region: 10000002 (The Forge - includes Jita)
        """
        print(f"Analyzing {item_name}...")
        
        orders = self.get_market_orders(region_id, item_id)
        if not orders:
            return []
        
        opportunities = []
        
        # Compare all hub combinations
        for buy_hub_name, buy_station_id in TRADE_HUBS.items():
            for sell_hub_name, sell_station_id in TRADE_HUBS.items():
                if buy_hub_name == sell_hub_name:
                    continue
                
                buy_price, _, buy_vol, _ = self.get_station_orders(orders, buy_station_id)
                _, sell_price, _, sell_vol = self.get_station_orders(orders, sell_station_id)
                
                if buy_price > 0 and sell_price > 0 and sell_price > buy_price:
                    profit = sell_price - buy_price
                    margin = (profit / buy_price) * 100
                    
                    # Only include if profit margin is at least 5%
                    if margin >= 5:
                        opportunities.append(MarketOpportunity(
                            item_name=item_name,
                            item_id=item_id,
                            buy_hub=buy_hub_name,
                            sell_hub=sell_hub_name,
                            buy_price=buy_price,
                            sell_price=sell_price,
                            profit_per_unit=profit,
                            profit_margin=margin,
                            buy_volume=buy_vol,
                            sell_volume=sell_vol
                        ))
        
        time.sleep(0.1)  # Rate limiting
        return opportunities
    
    def find_station_trading_opportunities(self, station_id: int, region_id: int = 10000002) -> List[Dict]:
        """
        Find station trading opportunities (buy low, sell high in same station)
        """
        print(f"Analyzing station trading opportunities...")
        opportunities = []
        
        for item_name, item_id in POPULAR_ITEMS.items():
            orders = self.get_market_orders(region_id, item_id)
            if not orders:
                continue
            
            best_buy, best_sell, buy_vol, sell_vol = self.get_station_orders(orders, station_id)
            
            if best_buy > 0 and best_sell > 0 and best_sell > best_buy:
                spread = best_sell - best_buy
                margin = (spread / best_sell) * 100
                
                # Significant spread for station trading
                if margin >= 3:
                    opportunities.append({
                        'item_name': item_name,
                        'buy_price': best_buy,
                        'sell_price': best_sell,
                        'spread': spread,
                        'margin': margin,
                        'buy_volume': buy_vol,
                        'sell_volume': sell_vol
                    })
            
            time.sleep(0.1)
        
        return sorted(opportunities, key=lambda x: x['margin'], reverse=True)


def main():
    """Main function to run the market analyzer"""
    print("=" * 70)
    print("EVE Online Market Analyzer - ISK Making Tool")
    print("=" * 70)
    print()
    
    analyzer = EVEMarketAnalyzer()
    
    while True:
        print("\nWhat would you like to do?")
        print("1. Find arbitrage opportunities (trade between hubs)")
        print("2. Find station trading opportunities (Jita)")
        print("3. Analyze specific item")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1-4): ").strip()
        
        if choice == "1":
            print("\n" + "=" * 70)
            print("ARBITRAGE OPPORTUNITIES")
            print("=" * 70)
            
            all_opportunities = []
            for item_name, item_id in POPULAR_ITEMS.items():
                opportunities = analyzer.analyze_arbitrage(item_name, item_id)
                all_opportunities.extend(opportunities)
            
            # Sort by profit margin
            all_opportunities.sort(key=lambda x: x.profit_margin, reverse=True)
            
            if all_opportunities:
                print(f"\nFound {len(all_opportunities)} profitable opportunities:\n")
                for i, opp in enumerate(all_opportunities[:10], 1):  # Top 10
                    print(f"{i}. {opp.item_name}")
                    print(f"   Buy from: {opp.buy_hub} @ {format_isk(opp.buy_price)} ISK")
                    print(f"   Sell to: {opp.sell_hub} @ {format_isk(opp.sell_price)} ISK")
                    print(f"   Profit: {format_isk(opp.profit_per_unit)} ISK per unit ({opp.profit_margin:.2f}%)")
                    print(f"   Available: {opp.sell_volume:,} units to buy")
                    print()
            else:
                print("\nNo significant arbitrage opportunities found at the moment.")
        
        elif choice == "2":
            print("\n" + "=" * 70)
            print("JITA STATION TRADING OPPORTUNITIES")
            print("=" * 70)
            
            opportunities = analyzer.find_station_trading_opportunities(TRADE_HUBS["Jita"])
            
            if opportunities:
                print(f"\nFound {len(opportunities)} station trading opportunities:\n")
                for i, opp in enumerate(opportunities, 1):
                    print(f"{i}. {opp['item_name']}")
                    print(f"   Buy orders: {format_isk(opp['buy_price'])} ISK")
                    print(f"   Sell orders: {format_isk(opp['sell_price'])} ISK")
                    print(f"   Spread: {format_isk(opp['spread'])} ISK ({opp['margin']:.2f}%)")
                    print(f"   Volume: {opp['buy_volume']:,} buy / {opp['sell_volume']:,} sell")
                    print()
            else:
                print("\nNo significant station trading opportunities found.")
        
        elif choice == "3":
            print("\nEnter item type ID (or item name from popular items):")
            print("Popular items:", ", ".join(POPULAR_ITEMS.keys()))
            
            item_input = input("\nItem: ").strip()
            
            if item_input in POPULAR_ITEMS:
                item_name = item_input
                item_id = POPULAR_ITEMS[item_input]
            else:
                try:
                    item_id = int(item_input)
                    item_name = f"Item {item_id}"
                except ValueError:
                    print("Invalid input. Please enter a valid item name or type ID.")
                    continue
            
            opportunities = analyzer.analyze_arbitrage(item_name, item_id)
            
            if opportunities:
                opportunities.sort(key=lambda x: x.profit_margin, reverse=True)
                print(f"\nFound {len(opportunities)} opportunities for {item_name}:\n")
                for i, opp in enumerate(opportunities, 1):
                    print(f"{i}. {opp.buy_hub} → {opp.sell_hub}")
                    print(f"   Buy: {format_isk(opp.buy_price)} ISK")
                    print(f"   Sell: {format_isk(opp.sell_price)} ISK")
                    print(f"   Profit: {format_isk(opp.profit_per_unit)} ISK ({opp.profit_margin:.2f}%)")
                    print()
            else:
                print(f"\nNo profitable opportunities found for {item_name}.")
        
        elif choice == "4":
            print("\nFly safe, capsuleer! o7")
            break
        
        else:
            print("\nInvalid choice. Please try again.")


if __name__ == "__main__":
    main()
