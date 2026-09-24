@echo off
chcp 65001 >nul
title AutoSIMD-FOCOS - Defesa Civil PA
cd /d "%~dp0"
echo ====================================================================
echo   AutoSIMD-FOCOS - Diagnostico Territorial de Focos de Calor
echo   Sala de Informacoes e Monitoramento de Desastres (SIMD) - CEDEC/PA
echo ====================================================================
echo.
"%~dp0python\python.exe" "%~dp0iniciar.py"
if errorlevel 1 (
    echo.
    echo Ocorreu um erro. Tire um print desta janela e envie ao suporte.
    pause
)
