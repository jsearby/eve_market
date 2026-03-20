# EVE Online ISK Making Tools

Python scripts to help you make ISK in EVE Online using legitimate market analysis.

## Setup (Run Once)

| Step | Script | What it does |
|------|--------|-------------|
| 1 | `1_setup_python.ps1` | Installs Python 3.12 + pip + all dependencies |
| 2 | `python 2_refresh_sde.py` | Downloads EVE game data (~500MB) + builds jump graph |
| 3 | `python 3_refresh_user_profile.py` | Authenticates with EVE & fetches your character data |

See [SETUP_API.md](SETUP_API.md) for ESI API setup instructions (needed for step 3).

## Usage (Run Anytime)

### Manufacturing Optimizer (`A_manufacturing_optimizer.py`)
Analyzes the most cost-efficient way to build items based on your skills.

```bash
python A_manufacturing_optimizer.py --target "Orca"
python A_manufacturing_optimizer.py --target "Retriever"
```

- Full recursive material breakdown
- Compares mining vs buying materials
- Tracks your blueprint ownership
- Calculates profitability with your skills

### Trading Route Finder (`B_trading_route_finder.py`)
Finds profitable buy/transport/sell opportunities within jump range.

```bash
python B_trading_route_finder.py
```

- Scans ALL stations and items within your jump range
- Uses your actual location, ship, and cargo capacity
- Calculates profit after your real sales tax
- Sorts by ISK/jump for best time efficiency
- First run downloads market data (~5-10 min), subsequent runs use cache

### Market Analyzer (`C_eve_market_analyzer.py`)
Quick comparison of prices between major trade hubs.

```bash
python C_eve_market_analyzer.py
```

- Compares prices across Jita, Amarr, Dodixie, Rens, Hek
- Shows arbitrage opportunities and profit margins

## Library Files (Don't Run Directly)

| File | Purpose |
|------|---------|
| `tools/esi_auth.py` | ESI API authentication handling |
| `tools/character_model.py` | Character profile data model |

## Data Files

| File/Dir | Purpose |
|----------|---------|
| `cache/sde/` | EVE Static Data Export (created by step 2) |
| `cache/market/` | Cached market orders per region |
| `cache/esi/` | ESI reference data (player structures) |
| `cache/user/` | Your character data and tokens (created by step 3) |
| `requirements.txt` | Python package dependencies |

## Privacy & Security

- All credentials stored **locally** on your computer
- **Nothing is sent to any third party**
- Uses official CCP ESI APIs only (read-only access)
- Delete `esi_tokens.json` anytime to revoke access

## Legal Notice
This tool uses EVE Online's official ESI API and complies with the game's EULA.
It provides market analysis and decision-making tools only - no automation or botting.

Fly safe and trade smart! o7
