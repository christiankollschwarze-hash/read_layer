# ============================================================
# READ LAYER - Sitzungs-Setup (einmal pro neuer PowerShell aufrufen)
#   .\setup_env.ps1
# Setzt die zwei fluechtigen Env-Variablen (Service-Account + GRPC-Cert-Pfad)
# und repariert bei Bedarf das certifi-Buendel um das Avast-Root (gegen den
# CERTIFICATE_VERIFY_FAILED-Handshake-Fehler).
# ============================================================

$ErrorActionPreference = "Stop"
$root = "C:\Users\sabin\read_layer"

# --- 1) Service-Account-Key ---------------------------------
$key = (Get-ChildItem "$root\JSON_Key\readlayercloud-*.json" | Select-Object -First 1).FullName
if (-not $key) { Write-Host "[setup] FEHLER: kein Key in JSON_Key\ gefunden" -ForegroundColor Red; return }
$env:GOOGLE_APPLICATION_CREDENTIALS = $key

# --- 2) certifi-Buendel als GRPC-Wurzelzertifikat -----------
$certifi = (python -c "import certifi; print(certifi.where())").Trim()
$env:GRPC_DEFAULT_SSL_ROOTS_FILE_PATH = $certifi

# --- 3) Avast-Root ins certifi-Buendel, falls es fehlt ------
$hasAvast = Select-String -Path $certifi -Pattern 'Avast' -Quiet
if (-not $hasAvast) {
    Write-Host "[setup] Avast-Root fehlt im certifi-Buendel -> haenge es an ..." -ForegroundColor Yellow
    $found = $false
    Get-ChildItem Cert:\CurrentUser\Root, Cert:\LocalMachine\Root |
      Where-Object { $_.Subject -like "*Avast*" } |
      ForEach-Object {
        $found = $true
        "-----BEGIN CERTIFICATE-----"
        [Convert]::ToBase64String($_.RawData, 'InsertLineBreaks')
        "-----END CERTIFICATE-----"
      } | Add-Content -Encoding ascii $certifi
    if (-not $found) {
        Write-Host "[setup] WARN: kein Avast-Root im Zertifikatspeicher gefunden." -ForegroundColor Yellow
        Write-Host "        Laeuft TLS-Inspektion ueberhaupt? Sonst ist nichts anzuhaengen." -ForegroundColor Yellow
    }
} else {
    Write-Host "[setup] certifi-Buendel enthaelt Avast-Root bereits." -ForegroundColor Green
}

# --- 4) Kontrolle -------------------------------------------
Write-Host ""
Write-Host "[setup] GOOGLE_APPLICATION_CREDENTIALS = $env:GOOGLE_APPLICATION_CREDENTIALS"
Write-Host "[setup] GRPC_DEFAULT_SSL_ROOTS_FILE_PATH = $env:GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"
$ok = Select-String -Path $certifi -Pattern 'Avast' -Quiet
Write-Host "[setup] Avast-Root im Buendel: $ok" -ForegroundColor $(if ($ok) { "Green" } else { "Red" })
Write-Host "[setup] Bereit. Jetzt z.B.:" -ForegroundColor Cyan
Write-Host '  python -m pipeline.stage_58_cloud_tts the-yellow-wallpaper --lang de --chapter c001 --force --keep-blocks --cut-guard 0.10'
