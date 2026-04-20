@echo off
cd /d "g:\My Drive\Claude\projects\trend-research-web"
if errorlevel 1 (
  cd /d "g:\マイドライブ\Claude\projects\trend-research-web"
)
git add index.html css/style.css py/app.py requirements.txt render.yaml
git commit -m "update"
git push origin main
echo Done.
pause
