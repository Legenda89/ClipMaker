# Opens TikTok Apps + ClipMaker fill helper side by side.
$fill = "https://legenda89.github.io/ClipMaker/tiktok-fill.html"
$apps = "https://developers.tiktok.com/apps/"
Start-Process $fill
Start-Sleep -Milliseconds 800
Start-Process $apps
Set-Clipboard -Value "https://legenda89.github.io/ClipMaker/"
Write-Host "Avattu: TikTok Apps + taytto-ohje."
Write-Host "Leikepoydalla nyt: Web/Desktop URL"
Write-Host "Seuraavaksi kopioi Terms/Privacy taytto-sivulta."
