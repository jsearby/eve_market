# ==============================================================================
# STEP 1: Python Environment Setup
# ==============================================================================
# Installs Python 3.12 + pip and all required Python packages
# Run this ONCE when first setting up the project
# Estimated time: 5-10 minutes
# ==============================================================================

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "EVE Tools - Python Setup" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Check if winget is available
Try {
    $wingetVersion = winget --version
    Write-Host "✓ winget is available: $wingetVersion" -ForegroundColor Green
}
Catch {
    Write-Host "✗ winget is not available on this system" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install App Installer from the Microsoft Store" -ForegroundColor Yellow
    Write-Host "Then re-run this script" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Press any key to exit..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host ""
Write-Host "Installing Python 3.12..." -ForegroundColor Yellow
Write-Host ""

# Check if Python is already installed
$pythonInstalled = $false
Try {
    $pyVersion = python --version 2>&1
    If ($pyVersion -match "Python 3\.\d+") {
        Write-Host "✓ Python is already installed: $pyVersion" -ForegroundColor Green
        $pythonInstalled = $true
    }
}
Catch {}

If (-not $pythonInstalled) {
    # Install Python 3.12 (includes pip)
    winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements

    If ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "✗ Python installation failed" -ForegroundColor Red
        Write-Host "  Install Python manually from https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }

    Write-Host ""
    Write-Host "✓ Python installation completed!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Refreshing PATH environment variable..." -ForegroundColor Yellow

    # Refresh PATH in current session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

Write-Host ""
Write-Host "Installing Python packages from requirements.txt..." -ForegroundColor Yellow
Write-Host ""

# Install requirements
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

If ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "✓ Setup Complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Python and all dependencies are installed." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Run: python 2_refresh_sde.py" -ForegroundColor White
    Write-Host "     (Downloads EVE game data - takes 5-10 min)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  2. Run: python 3_refresh_user_profile.py" -ForegroundColor White
    Write-Host "     (Authenticate and fetch your character data)" -ForegroundColor Gray
    Write-Host ""
}
Else {
    Write-Host ""
    Write-Host "✗ Failed to install Python packages" -ForegroundColor Red
    Write-Host "Try running manually: pip install -r requirements.txt" -ForegroundColor Yellow
    Write-Host ""
}
