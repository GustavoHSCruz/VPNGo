@echo off
if "%~1"=="--help" goto help
if "%~1"=="-h" goto help
if "%~1"=="help" if "%~2"=="--temp" goto helptemp
if "%~1"=="help" if "%~2"=="-d" goto helpdetach
if "%~1"=="help" if "%~2"=="--detach" goto helpdetach
if "%~1"=="--temp" goto temp
if "%~1"=="start" if "%~4"=="--temp" goto starttemp
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0vpngo.ps1" %*
exit /b

:help
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0vpngo.ps1" help
exit /b

:helptemp
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0vpngo.ps1" help temp
exit /b

:helpdetach
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0vpngo.ps1" help detach
exit /b

:temp
if not "%~5"=="" goto invalid
if "%~4"=="-d" goto tempdetached
if "%~4"=="--detach" goto tempdetached
if not "%~4"=="" goto invalid
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0vpngo.ps1" temp "%~2" "%~3"
exit /b

:tempdetached
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0vpngo.ps1" temp "%~2" "%~3" detach
exit /b

:starttemp
if not "%~6"=="" goto invalid
if "%~5"=="-d" goto startdetached
if "%~5"=="--detach" goto startdetached
if not "%~5"=="" goto invalid
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0vpngo.ps1" temp "%~3" "%~2"
exit /b

:startdetached
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0vpngo.ps1" temp "%~3" "%~2" detach
exit /b

:invalid
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0vpngo.ps1"
exit /b 2
