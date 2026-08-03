@echo off
REM Kylin VM SSH Ironclad Transfer Tool - Global Launcher
REM Ironclad Rule: Every transfer MUST pass SHA256 verification.
REM If verification fails, it MUST report an explicit error.
REM No silent success. No false success.

set PYTHON=C:\Users\jackb\AppData\Local\Programs\Python\Python313\python.exe
set MODULE=%~dp0evidence\ssh_transfer_diagnosis\kylin_transfer.py

if "%~1"=="" goto :usage
%PYTHON% "%MODULE%" %1 %2 %3 %4 %5 %6 %7
exit /b %errorlevel%

:usage
echo Kylin VM SSH Ironclad Transfer Tool
echo ===================================
echo.
echo   Ironclad 1: Upload = SFTP put + remote SHA256 + retry x3
echo   Ironclad 2: Download = SFTP get + local SHA256 + retry x3
echo   Ironclad 3: Write = base64 heredoc + SHA256 verification
echo   Ironclad 4: listdir() after verifying directory exists
echo   Ironclad 5: All errors report explicitly, never silently swallowed
echo.
echo Usage:
echo   kylin-ssh upload   ^<local_file^> ^<remote_path^>
echo   kylin-ssh batch    ^<local_dir^>  ^<remote_dir^>
echo   kylin-ssh download ^<remote_path^> ^<local_path^>
echo   kylin-ssh evidence ^<remote_dir^> ^<local_dir^>
echo   kylin-ssh exec     "^<command^>" [--sudo]
echo   kylin-ssh diagnose
exit /b 0