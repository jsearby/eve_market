# EVE ESI API Setup Guide

## Automatic Profile Generation

Instead of manually entering your skills, the script can automatically pull your character data from EVE Online!

## Step-by-Step Setup

### 1. Create an ESI Application

1. **Go to**: https://developers.eveonline.com/applications
2. **Login** with your EVE Online account
3. Click **"Create New Application"**

### 2. Fill in Application Details

- **Name**: `EVE Trading Tools` (or any name you want)
- **Description**: `Personal trading profit analyzer`
- **Connection Type**: **Authentication & API Access** ⚠️ IMPORTANT
- **Permissions (Scopes)** - Check these boxes:
  - ✅ `esi-skills.read_skills.v1` - Read your character skills
  - ✅ `esi-wallet.read_character_wallet.v1` - Read your wallet balance
  - ✅ `esi-characters.read_standings.v1` - Read your faction/corp standings
  - ✅ `esi-location.read_location.v1` - Read your current location
  - ✅ `esi-location.read_ship_type.v1` - Read your current ship
  - ✅ `esi-assets.read_assets.v1` - Read your assets (for blueprint detection)
  - ✅ `esi-universe.read_structures.v1` - Resolve citadel names
- **Callback URL**: `http://localhost:8888/callback` ⚠️ EXACT spelling

### 3. Create and Copy Credentials

1. Click **"Create Application"**
2. You'll see your application details
3. **Copy** these two things:
   - **Client ID** (looks like: `abc123def456789...`)
   - **Secret Key** (click "Show" first, then copy)

### 4. Run the Profile Setup Script

```powershell
# Run the profile setup
python 3_refresh_user_profile.py
```

### 5. Follow the Prompts

1. **Paste** your Client ID when asked
2. **Paste** your Secret Key when asked
3. Choose to **save credentials** (y) for future use
4. Your **browser will open** - login to EVE Online
5. Click **"Authorize"** to allow the app to read your data
6. Browser will show "Success!" - **return to the terminal**
7. Script will automatically:
   - Read all your trade skills
   - Check your wallet balance
   - Get your standings
   - Calculate your real trading costs
   - Save your profile

### 6. Done!

Your profile is now saved in `cache/user/character_profile.json`. 

Run again anytime to update (as your skills improve, wallet grows, etc.)

## What Data is Accessed?

**The script CAN:**
- ✅ Read your skills (READ ONLY)
- ✅ Read your wallet balance (READ ONLY)
- ✅ Read your standings (READ ONLY)
- ✅ Read your assets list (READ ONLY — used for blueprint detection)
- ✅ Read your current location and ship (READ ONLY)

**The script CANNOT:**
- ❌ Transfer ISK
- ❌ Trade items
- ❌ Control your character
- ❌ Send messages
- ❌ Do anything automated in-game

This is 100% within EVE's EULA and uses official CCP APIs.

## Privacy & Security

- Your credentials are stored **locally** in `cache/user/esi_credentials.json`
- Your access tokens are stored **locally** in `cache/user/esi_tokens.json`
- **Nothing is sent to any third party**
- All data stays on **your computer**
- Delete these files anytime to revoke access

## Troubleshooting

### "Authentication failed"
- Check Client ID and Secret are correct
- Make sure Callback URL is exactly: `http://localhost:8888/callback`
- Make sure you selected all 3 scopes (permissions)

### "Port already in use"
- Close any programs using port 8888
- Or change the port in `3_refresh_user_profile.py` (line 35)

### Browser shows "Can't reach this page"
- **This is normal!** The script caught the callback. Return to terminal.

### "API request failed"
- Your access token may have expired
- Delete `cache/user/esi_tokens.json` and run again to re-authenticate

## Refreshing Your Profile

Run `python 3_refresh_user_profile.py` anytime to update your character data
(after training new skills, acquiring blueprints, or gaining standings).
