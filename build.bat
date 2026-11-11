@echo off
REM Needs Python 3.10+ (tick "Add to PATH") and Inno Setup 6 for the installer
pip install pyqt6 pyqt6-webengine pyinstaller
pyinstaller --noconsole --onefile --icon icon.ico --add-data "icon.ico;." --name PlaylistPlayer player.py
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% installer.iss
  echo.
  echo Installer ready: installer\PlaylistPlayer-Setup.exe
) else (
  echo.
  echo Install Inno Setup 6, then run this again to get the installer.
  echo Portable exe is at dist\PlaylistPlayer.exe
)
pause
