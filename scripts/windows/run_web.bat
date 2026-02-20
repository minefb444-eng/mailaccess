@echo off
setlocal ENABLEDELAYEDEXPANSION

if "%WEB_SESSION_SECRET%"=="" (
  echo [ERROR] WEB_SESSION_SECRET is required.
  exit /b 1
)

if "%BOT_SECRET%"=="" (
  echo [ERROR] BOT_SECRET is required.
  exit /b 1
)

python web_main.py
exit /b %ERRORLEVEL%
