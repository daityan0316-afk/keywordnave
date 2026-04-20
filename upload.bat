@echo off
chcp 65001 > nul
cd /d "g:\マイドライブ\Claude\projects\trend-research-web"

echo GitHubにアップロード中...
git add index.html css/style.css py/app.py requirements.txt render.yaml
git commit -m "update"
git push origin main

echo.
echo 完了しました！Renderに自動反映されます。
pause
