# READ LAYER - einmalige Git-Einrichtung auf Windows (24.10.2026)
$ErrorActionPreference = "Stop"
$repos = @("C:\Users\sabin\read_layer", "C:\Users\sabin\taella-app")

# 1. Git vorhanden?
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "Git fehlt - installiere Git for Windows ..."
  winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
  Write-Host "Fertig. Fenster schliessen und Skript erneut starten."; Read-Host; exit
}
git --version

# Repos wurden in der Linux-Umgebung angelegt -> als sicher markieren
foreach ($r in $repos) { git config --global --add safe.directory ($r -replace '\\','/') }

# 6. GitHub-Verbindung (Repos read_layer und taella-app vorher privat und OHNE README auf github.com anlegen)
$user = "christiankollschwarze-hash"
# Commits dem GitHub-Konto zuordnen (noreply-Adresse)
$gh = Invoke-RestMethod "https://api.github.com/users/$user"
$mail = "$($gh.id)+$user@users.noreply.github.com"
foreach ($r in $repos) { git -C $r config user.email $mail }
foreach ($r in $repos) {
  $name = Split-Path $r -Leaf
  Set-Location $r
  git branch -M main
  if (git remote) { git remote set-url origin "https://github.com/$user/$name.git" }
  else { git remote add origin "https://github.com/$user/$name.git" }
  git push -u origin main
}

# 7. Aufgabenplanung: taeglich 23:00, unabhaengig von Anmeldung, Reaktivieren, verpassten Start nachholen
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
$action   = New-ScheduledTaskAction -Execute "C:\Users\sabin\read_layer\start_git_sicherung.bat"
$trigger  = New-ScheduledTaskTrigger -Daily -At 23:00
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable
Register-ScheduledTask -TaskName "READ LAYER Git-Sicherung" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Aufgabe angelegt."

# 8. Testlauf
Start-ScheduledTask -TaskName "READ LAYER Git-Sicherung"
Start-Sleep 20
Get-Content "C:\Users\sabin\read_layer\cockpit\logs\git_sicherung.txt" -Tail 15
Read-Host "Fertig - Enter zum Schliessen"
