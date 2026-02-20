@echo off
setlocal ENABLEDELAYEDEXPANSION

if "%BOT_TOKEN%"=="" (
  echo [ERROR] BOT_TOKEN is required.
  exit /b 1
)

if "%BOT_SECRET%"=="" (
  echo [ERROR] BOT_SECRET is required.
  exit /b 1
)

python main
exit /b %ERRORLEVEL%
