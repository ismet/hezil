@echo off
rem ===========================================================================
rem  HEZIL HES — PANO BASLATICI
rem  Cift tiklayin: sunucu baslar ve pano tarayicida acilir.
rem  Kapatmak icin bu pencerede Ctrl+C veya pencereyi kapatin.
rem ===========================================================================
chcp 65001 >nul
cd /d "%~dp0"
title Hezil HES - Pano Sunucusu
set PYTHONIOENCODING=utf-8

echo.
echo ==========================================================
echo   HEZIL HES - ALTERNATIF ANALIZ PANOSU
echo ==========================================================
echo.

rem --- Python var mi? -------------------------------------------------------
set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
  where py >nul 2>&1
  if not errorlevel 1 set "PY=py"
)
if not defined PY (
  echo [HATA] Python bulunamadi.
  echo.
  echo Python'u kurun ^(python.org^) ve kurulumda
  echo "Add Python to PATH" secenegini isaretleyin.
  echo.
  pause
  exit /b 1
)

rem --- Gerekli paketler ------------------------------------------------------
%PY% -c "import numpy, pandas, matplotlib, openpyxl" >nul 2>&1
if errorlevel 1 (
  echo [HATA] Gerekli Python paketleri eksik.
  echo Kurmak icin bu komutu calistirin:
  echo    %PY% -m pip install numpy pandas matplotlib openpyxl scipy
  echo.
  pause
  exit /b 1
)

rem --- Pano dosyasi yoksa uret ----------------------------------------------
if not exist "hezil_dashboard.html" (
  echo Pano dosyasi yok, uretiliyor...
  %PY% dashboard.py
  if errorlevel 1 (
    echo.
    echo [HATA] Pano uretilemedi. Once  %PY% alternatifler.py  calistirin.
    pause
    exit /b 1
  )
  echo.
)

rem --- Sunucuyu baslat -------------------------------------------------------
echo Sunucu baslatiliyor... Tarayici otomatik acilacak.
echo Bu pencereyi KAPATMAYIN - sunucu burada calisiyor.
echo Durdurmak icin: Ctrl+C
echo.
%PY% pano_sunucu.py

echo.
echo Sunucu durdu.
pause
