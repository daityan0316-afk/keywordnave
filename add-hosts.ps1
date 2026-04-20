# 管理者権限で実行
$entry = "127.0.0.1    trend.local"
$hostsPath = "C:\Windows\System32\drivers\etc\hosts"
$current = Get-Content $hostsPath -Raw
if ($current -notmatch "trend\.local") {
    Add-Content -Path $hostsPath -Value "`n$entry" -Encoding ASCII
    Write-Host "追加しました！" -ForegroundColor Green
} else {
    Write-Host "すでに追加済みです。" -ForegroundColor Yellow
}
Write-Host "ブラウザで http://trend.local:3737/ を開いてください。"
pause
