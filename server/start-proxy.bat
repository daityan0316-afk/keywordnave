@echo off
chcp 65001 > nul
echo キーワードなび プロキシサーバー起動中...
cd /d "%~dp0"

where node >nul 2>&1
if errorlevel 1 (
  echo Node.js がインストールされていません。
  echo https://nodejs.org からインストールしてください。
  pause
  exit /b 1
)

if not exist node_modules (
  echo 初回セットアップ中... (npm install)
  npm install
)

node server.js
pause
