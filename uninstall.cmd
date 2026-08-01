@echo off
REM ============================================================
REM  DTXScribe - Full Uninstaller
REM  Finds and removes every DTXScribe component scattered across
REM  this PC: downloaded model weights, cache, logs, the legacy
REM  DTXForge data folder, Demucs weights, any shortcuts, and
REM  (optionally) the program folder itself.
REM  Your saved .dtx charts are never touched.
REM ============================================================
setlocal EnableDelayedExpansion
title DTXScribe Uninstaller
cd /d "%~dp0"

REM app folder without a trailing backslash (for later self-delete)
set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"

set "DATA=%LOCALAPPDATA%\DTXScribe"
set "LEGACY=%LOCALAPPDATA%\DTXForge"
set "DENO=%LOCALAPPDATA%\deno"
set "__DTXAPP=%APPDIR%"

echo.
echo ============================================================
echo   DTXScribe - Full Uninstaller
echo ============================================================
echo.
echo The following DTXScribe components were found on this PC:
echo.

REM --- report each location with its size (powershell is always present) ---
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "function Add($label,$path){ if(Test-Path $path){ try{ $mb=[math]::Round(((Get-ChildItem $path -Recurse -File -EA SilentlyContinue | Measure-Object -Sum Length).Sum)/1MB,1) }catch{ $mb='?' }; Write-Host ('   [x] {0,-44} {1,8} MB' -f $label,$mb) } else { Write-Host ('   [ ] {0,-44} {1}' -f $label,'(not present)') } }; " ^
  "Add 'Model weights, cache and logs' $env:LOCALAPPDATA'\DTXScribe'; " ^
  "Add 'Legacy DTXForge data (pre-rebrand)' $env:LOCALAPPDATA'\DTXForge'; " ^
  "Add 'Deno runtime (YouTube downloader)' $env:LOCALAPPDATA'\deno'; " ^
  "$ck = Join-Path $env:USERPROFILE '.cache\torch\hub\checkpoints'; $dm = 0; if(Test-Path $ck){ $dm = (Get-ChildItem $ck -File -EA SilentlyContinue | Where-Object { $_.Name -match 'demucs' } | Measure-Object -Sum Length).Sum }; " ^
  "if($dm -gt 0){ Write-Host ('   [x] {0,-44} {1,8} MB' -f 'Demucs drum-separation weights',[math]::Round($dm/1MB,1)) } else { Write-Host ('   [ ] {0,-44} {1}' -f 'Demucs drum-separation weights','(not present)') }; " ^
  "$app = $env:__DTXAPP; $ws = New-Object -ComObject WScript.Shell; $sc=0; " ^
  "foreach($d in @([Environment]::GetFolderPath('Programs'),[Environment]::GetFolderPath('Desktop'),(Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'))){ if(Test-Path $d){ Get-ChildItem $d -Recurse -Filter '*.lnk' -EA SilentlyContinue | ForEach-Object { try{ $t=$ws.CreateShortcut($_.FullName).TargetPath; if($t -and $t -like ($app+'*')){ $sc++ } }catch{} } } }; " ^
  "if($sc){ Write-Host ('   [x] {0,-44} {1,8}' -f 'Shortcuts pointing at this app',$sc) } else { Write-Host ('   [ ] {0,-44} {1}' -f 'Shortcuts pointing at this app','(none found)') }"

echo.
echo   Your saved .dtx charts (Downloads / your songs folder) are NOT touched.
echo.
set /p "ANS=Remove the DTXScribe data listed above now? [y/N] "
if /i not "%ANS%"=="y" goto :cancel

echo.
echo Removing DTXScribe data...

REM --- 1. main data folder (models ~1 GB, cache, logs) ---
if exist "%DATA%" (
    rmdir /s /q "%DATA%" 2>nul
    if exist "%DATA%" ( echo   WARNING: Some files are in use - close DTXScribe and re-run. ) else ( echo   - Removed model weights, cache and logs. )
)

REM --- 2. legacy pre-rebrand data folder ---
if exist "%LEGACY%" (
    rmdir /s /q "%LEGACY%" 2>nul
    if not exist "%LEGACY%" echo   - Removed legacy DTXForge data.
)

REM --- 3. Demucs weights (only demucs-named files in the shared torch cache) ---
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ck = Join-Path $env:USERPROFILE '.cache\torch\hub\checkpoints'; if(Test-Path $ck){ $f = Get-ChildItem $ck -File -EA SilentlyContinue | Where-Object { $_.Name -match 'demucs' }; if($f){ $f | Remove-Item -Force -EA SilentlyContinue; Write-Host '   - Removed Demucs weights.' } }"

REM --- 4. shortcuts that point at THIS app folder ---
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$app = $env:__DTXAPP; $ws = New-Object -ComObject WScript.Shell; $n=0; " ^
  "foreach($d in @([Environment]::GetFolderPath('Programs'),[Environment]::GetFolderPath('Desktop'),(Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'))){ if(Test-Path $d){ Get-ChildItem $d -Recurse -Filter '*.lnk' -EA SilentlyContinue | ForEach-Object { try{ $t=$ws.CreateShortcut($_.FullName).TargetPath; if($t -and $t -like ($app+'*')){ Remove-Item $_.FullName -Force -EA SilentlyContinue; $n++ } }catch{} } } }; " ^
  "if($n){ Write-Host ('   - Removed {0} shortcut(s).' -f $n) }"

REM --- 5. deno runtime (opt-in: it lives at deno's standard path and is a
REM     general JS runtime, so remove it only if you don't use deno elsewhere) ---
if exist "%DENO%" (
    echo.
    echo A Deno runtime is installed at "%DENO%".
    echo It was fetched for DTXScribe's YouTube downloads, but Deno is a general
    echo JavaScript runtime and may be used by other tools.
    set "DN="
    set /p "DN=Remove the Deno runtime too? [y/N] "
    if /i "!DN!"=="y" (
        rmdir /s /q "%DENO%" 2>nul
        if not exist "%DENO%" ( echo   - Removed Deno runtime. ) else ( echo   WARNING: Deno is in use - close anything using it and re-run. )
    ) else (
        echo   - Left the Deno runtime in place.
    )
)

echo.
echo Done. The scattered DTXScribe data has been removed.
echo.

REM --- 6. optionally delete the program folder itself ---
echo The DTXScribe program folder is:
echo     "%APPDIR%"
echo.
set /p "SELF=Also delete the program folder itself now? [y/N] "
if /i not "%SELF%"=="y" (
    echo.
    echo Left the program folder in place. You can delete it any time -
    echo DTXScribe is portable, so removing the folder fully removes the app.
    goto :end
)

echo.
echo The folder will be deleted after this window closes.
REM spawn a detached step that waits for this script to exit, then removes the folder
start "" /min cmd /c "timeout /t 2 >nul & rmdir /s /q ""%APPDIR%"""
echo Goodbye.
timeout /t 2 >nul
endlocal
exit

:cancel
echo.
echo Cancelled - nothing was removed.
:end
echo.
pause
endlocal
