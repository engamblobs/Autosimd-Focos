@echo off
chcp 65001 >nul
title AutoSIMD-FOCOS - Defesa Civil PA
echo ====================================================================
echo   AutoSIMD-FOCOS - Diagnostico Territorial de Focos de Calor
echo   Sala de Informacoes e Monitoramento de Desastres (SIMD) - CEDEC/PA
echo ====================================================================
echo.

rem Arquivos que precisam estar ao lado deste .bat
set "FALTANDO="
if not exist "%~dp0python\python.exe" set "FALTANDO=python\python.exe"
if not exist "%~dp0iniciar.py" set "FALTANDO=%FALTANDO% iniciar.py"
if not exist "%~dp0app.py" set "FALTANDO=%FALTANDO% app.py"
if not exist "%~dp0core\config.py" set "FALTANDO=%FALTANDO% core"
if not exist "%~dp0referencia\municipios_pa.csv" set "FALTANDO=%FALTANDO% referencia"
if not exist "%~dp0BASES_GEOJSON\bdqueimadas_consolidado.parquet" set "FALTANDO=%FALTANDO% BASES_GEOJSON"
if defined FALTANDO goto :arquivos_faltando

cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0iniciar.py"
if errorlevel 1 (
    echo.
    echo Ocorreu um erro. Tire um print desta janela e envie ao suporte.
    pause
)
exit /b

:arquivos_faltando
echo ERRO: arquivos do sistema nao encontrados nesta pasta:
echo   %~dp0
echo Faltando: %FALTANDO%
echo.
echo Causas mais comuns:
echo  1. O .bat foi aberto de DENTRO do arquivo .zip. Clique com o botao
echo     direito no .zip, escolha "Extrair tudo..." e abra o .bat da pasta extraida.
echo  2. A extracao foi interrompida. Apague a pasta e extraia o .zip novamente.
echo  3. O antivirus removeu algum arquivo. Verifique a quarentena do antivirus.
echo.
pause
exit /b 1
