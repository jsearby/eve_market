"""
EVE ESI API Authentication Helper
Handles OAuth2 authentication with EVE Online ESI API
"""

import os
import requests
import webbrowser
import json
import base64
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, quote
from typing import Optional, Dict, List

from tools.config import ESI_TOKENS_FILE, ESI_CREDS_FILE


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback"""
    
    auth_code = None
    state_received = None
    
    def do_GET(self):
        """Handle the OAuth callback"""
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if 'code' in params:
            CallbackHandler.auth_code = params['code'][0]
            CallbackHandler.state_received = params.get('state', [None])[0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body>
                    <h1>Success!</h1>
                    <p>Authorization successful. You can close this window and return to the script.</p>
                </body>
                </html>
            """)
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body>
                    <h1>Error</h1>
                    <p>Authorization failed. Please try again.</p>
                </body>
                </html>
            """)
    
    def log_message(self, format, *args):
        """Suppress log messages"""
        pass


class ESIAuth:
    """Handles EVE ESI API authentication and requests"""
    
    BASE_URL = "https://esi.evetech.net/latest"
    AUTH_URL = "https://login.eveonline.com/v2/oauth/authorize"
    TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
    
    SCOPES = [
        "esi-skills.read_skills.v1",
        "esi-wallet.read_character_wallet.v1",
        "esi-characters.read_standings.v1",
        "esi-location.read_location.v1",
        "esi-location.read_ship_type.v1",
        "esi-assets.read_assets.v1",  # For reading character assets (blueprints, etc.)
        "esi-universe.read_structures.v1",  # For reading structure names (citadels)
    ]
    
    def __init__(self, client_id: str, client_secret: str, callback_port: int = 8888):
        self.client_id = client_id
        self.client_secret = client_secret
        self.callback_url = f"http://localhost:{callback_port}/callback"
        self.callback_port = callback_port
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.character_id: Optional[int] = None
        self.character_name: Optional[str] = None
    
    def authenticate(self) -> bool:
        """
        Perform OAuth authentication flow
        Returns True if successful
        """
        # Generate random state for CSRF protection
        state = secrets.token_urlsafe(32)
        
        # Build authorization URL
        scope_string = " ".join(self.SCOPES)
        auth_url = (
            f"{self.AUTH_URL}"
            f"?response_type=code"
            f"&redirect_uri={quote(self.callback_url)}"
            f"&client_id={self.client_id}"
            f"&scope={quote(scope_string)}"
            f"&state={state}"
        )
        
        print("\n" + "=" * 80)
        print("ESI API AUTHENTICATION")
        print("=" * 80)
        print("\n1. Your browser will open to the EVE login page")
        print("2. Log in with your EVE character")
        print("3. Authorize the application")
        print("4. You'll be redirected back (it may show 'can't be reached' - that's OK!)")
        print("\nOpening browser in 3 seconds...")
        
        import time
        time.sleep(3)
        
        # Open browser
        webbrowser.open(auth_url)
        
        # Start local HTTP server to catch callback
        print(f"\nWaiting for authorization callback on port {self.callback_port}...")
        
        server = HTTPServer(('localhost', self.callback_port), CallbackHandler)
        
        # Handle one request (the callback)
        server.handle_request()
        server.server_close()
        
        if not CallbackHandler.auth_code:
            print("\n✗ Failed to get authorization code")
            return False
        
        # Verify state parameter
        if CallbackHandler.state_received != state:
            print("\n✗ State parameter mismatch - possible security issue")
            return False
        
        # Exchange code for token
        print("✓ Authorization code received")
        print("Exchanging for access token...")
        
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_b64 = base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "login.eveonline.com"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": CallbackHandler.auth_code,
        }
        
        try:
            response = requests.post(self.TOKEN_URL, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data['access_token']
            self.refresh_token = token_data.get('refresh_token')
            
            # Verify and get character info
            self._verify_token()
            
            print(f"✓ Authenticated as: {self.character_name}")
            return True
            
        except Exception as e:
            print(f"\n✗ Token exchange failed: {e}")
            return False
    
    def _verify_token(self):
        """Verify token and get character ID"""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        response = requests.get(
            "https://login.eveonline.com/oauth/verify",
            headers=headers
        )
        response.raise_for_status()
        
        data = response.json()
        self.character_id = data['CharacterID']
        self.character_name = data['CharacterName']
    
    def get(self, endpoint: str, **params) -> Optional[Dict]:
        """Make authenticated GET request to ESI"""
        if not self.access_token:
            print("Not authenticated!")
            return None
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"API request failed: {e}")
            return None
    
    def save_tokens(self, filename=None):
        """Save tokens to file"""
        path = filename or ESI_TOKENS_FILE
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'character_id': self.character_id,
            'character_name': self.character_name,
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def load_tokens(self, filename=None) -> bool:
        """Load tokens from file"""
        path = filename or ESI_TOKENS_FILE
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            self.access_token = data.get('access_token')
            self.refresh_token = data.get('refresh_token')
            self.character_id = data.get('character_id')
            self.character_name = data.get('character_name')
            
            # Verify token is still valid
            try:
                self._verify_token()
                return True
            except:
                return False
        except:
            return False
    
    def get_character_assets(self) -> Optional[List[Dict]]:
        """Get all character assets (includes blueprints)"""
        if not self.character_id or not self.access_token:
            return None
        
        try:
            # ESI returns assets in pages
            all_assets = []
            page = 1
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            while True:
                url = f"https://esi.evetech.net/latest/characters/{self.character_id}/assets/?page={page}"
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                if not data or not isinstance(data, list) or len(data) == 0:
                    break
                
                all_assets.extend(data)
                page += 1
                
                # Check if there are more pages
                if 'x-pages' in response.headers:
                    total_pages = int(response.headers['x-pages'])
                    if page > total_pages:
                        break
            
            return all_assets
        except Exception as e:
            print(f"Failed to fetch assets: {e}")
            return None
    
    def get_location_name(self, location_id: int) -> str:
        """Get human-readable location name from location ID"""
        if not location_id:
            return "Unknown Location"
        
        # Station IDs are in range 60000000-64000000
        if 60000000 <= location_id < 64000000:
            # It's an NPC station - no auth required
            try:
                url = f"https://esi.evetech.net/latest/universe/stations/{location_id}/"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                return data.get('name', f'Station {location_id}')
            except:
                pass
            return f"NPC Station {location_id}"
        
        # Structure IDs are > 1000000000000
        elif location_id >= 1000000000000:
            # It's a player structure (citadel, etc.) - auth required
            try:
                headers = {"Authorization": f"Bearer {self.access_token}"}
                url = f"https://esi.evetech.net/latest/universe/structures/{location_id}/"
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                return data.get('name', f'Structure {location_id}')
            except:
                pass
            return f"Player Structure {location_id}"
        
        # Other location (might be in space, container, etc.)
        return f"Location {location_id}"


def load_client_credentials(filename=None) -> tuple:
    """Load client ID and secret from file"""
    path = filename or ESI_CREDS_FILE
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return data.get('client_id'), data.get('client_secret')
    except:
        return None, None


def save_client_credentials(client_id: str, client_secret: str, filename=None):
    """Save client credentials to file"""
    path = filename or ESI_CREDS_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        'client_id': client_id,
        'client_secret': client_secret,
    }
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"✓ Credentials saved to {path}")


def setup_esi_credentials() -> tuple:
    """
    Resolve ESI client credentials using priority order:
      1. Environment variables EVE_CLIENT_ID / EVE_CLIENT_SECRET
      2. Saved credentials file (cache/user/esi_credentials.json)
      3. Interactive prompt
    Returns (client_id, client_secret).
    """
    print("\n" + "=" * 80)
    print("ESI API SETUP")
    print("=" * 80)

    # 1. Environment variables (set by cred.ps1)
    client_id = os.getenv('EVE_CLIENT_ID')
    client_secret = os.getenv('EVE_CLIENT_SECRET')
    if client_id and client_secret:
        print("\n✓ Found credentials in environment variables")
        print(f"   Client ID: {client_id[:8]}...")
        return client_id, client_secret

    # 2. Saved credentials file
    client_id, client_secret = load_client_credentials()
    if client_id and client_secret:
        print("\n✓ Found saved credentials in file")
        use_saved = input("Use saved credentials? (y/n): ").strip().lower()
        if use_saved in ['y', 'yes', '']:
            return client_id, client_secret

    # 3. Interactive prompt
    print("\n📝 You need to create an ESI application first!")
    print("\nSteps:")
    print("1. Go to: https://developers.eveonline.com/applications")
    print("2. Click 'Create New Application'")
    print("3. Fill in:")
    print("   - Name: EVE Trading Tools")
    print("   - Description: Personal trading analyzer")
    print("   - Connection Type: Authentication & API Access")
    print("   - Scopes (select these):")
    print("     ✓ esi-skills.read_skills.v1")
    print("     ✓ esi-wallet.read_character_wallet.v1")
    print("     ✓ esi-characters.read_standings.v1")
    print("     ✓ esi-location.read_location.v1")
    print("     ✓ esi-location.read_ship_type.v1")
    print("     ✓ esi-assets.read_assets.v1")
    print("     ✓ esi-universe.read_structures.v1")
    print("   - Callback URL: http://localhost:8888/callback")
    print("4. Click 'Create Application'")
    print("5. Copy the Client ID and Secret Key")
    print("\nPress Enter when ready...")
    input()

    client_id = input("\nEnter Client ID: ").strip()
    client_secret = input("Enter Client Secret: ").strip()

    save = input("\nSave credentials for future use? (y/n): ").strip().lower()
    if save in ['y', 'yes', '']:
        save_client_credentials(client_id, client_secret)

    return client_id, client_secret
