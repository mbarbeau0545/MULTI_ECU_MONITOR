@echo off
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"

rem =====================================================
rem USER CONFIG (double-click this .bat after editing)
rem =====================================================
set "UDP_HOST=127.0.0.1"
set "ECU_COUNT=2"

rem ECU 1
set "ECU_1_EXE=D:\Project\Software\STM32\Gamma\Gamma_Safety_AddCfg\.pio\build\pc_sim_debug\program.exe"
set "ECU_1_UDP_PORT=19091"
set "ECU_1_EXTRA_ARGS_LINE=--ANA 1 3000"

rem ECU 2
set "ECU_2_EXE=D:\Project\Software\STM32\Gamma\Gamma_Safety_AddCfg\.pio\build\pc_sim_debug\program.exe"
set "ECU_2_UDP_PORT=19090"
set "ECU_2_EXTRA_ARGS_LINE=--ANA 1 2400"

rem Optional global switches
set "DRY_RUN=0"
set "WAIT_PROCESSES=0"

if "%~1"=="" (
  if "%ECU_COUNT%"=="" (
    echo [ERROR] ECU_COUNT is empty. Edit this .bat first.
    exit /b 2
  )

  set "EXE_PATH_LIST="
  set "UDP_PORT_LIST="
  set "EXTRA_ARGS_LIST="

  for /L %%I in (1,1,%ECU_COUNT%) do (
    call set "CUR_EXE=%%ECU_%%I_EXE%%"
    call set "CUR_PORT=%%ECU_%%I_UDP_PORT%%"
    call set "CUR_EXTRA=%%ECU_%%I_EXTRA_ARGS_LINE%%"

    if "!CUR_EXE!"=="" (
      echo [ERROR] Missing ECU_%%I_EXE
      exit /b 2
    )
    if "!CUR_PORT!"=="" (
      echo [ERROR] Missing ECU_%%I_UDP_PORT
      exit /b 2
    )

    if defined EXE_PATH_LIST (
      set "EXE_PATH_LIST=!EXE_PATH_LIST!;!CUR_EXE!"
      set "UDP_PORT_LIST=!UDP_PORT_LIST!;!CUR_PORT!"
      set "EXTRA_ARGS_LIST=!EXTRA_ARGS_LIST!;!CUR_EXTRA!"
    ) else (
      set "EXE_PATH_LIST=!CUR_EXE!"
      set "UDP_PORT_LIST=!CUR_PORT!"
      set "EXTRA_ARGS_LIST=!CUR_EXTRA!"
    )
  )

  set "DRY_RUN_OPT="
  set "WAIT_OPT="
  if "%DRY_RUN%"=="1" set "DRY_RUN_OPT=-DryRun"
  if "%WAIT_PROCESSES%"=="1" set "WAIT_OPT=-Wait"

  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%launch_multi_exe.ps1" ^
    -ExePathList "!EXE_PATH_LIST!" ^
    -UdpHost "%UDP_HOST%" ^
    -UdpPortList "!UDP_PORT_LIST!" ^
    -ExtraArgsList "!EXTRA_ARGS_LIST!" ^
    %DRY_RUN_OPT% %WAIT_OPT%
) else (
  rem Manual mode: pass through CLI args to ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%launch_multi_exe.ps1" %*
)

set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo launch_multi_exe failed with code %RC%
)

echo Press any key to continue...
pause
exit /b %RC%
