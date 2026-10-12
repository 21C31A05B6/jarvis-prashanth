' ============================================================
' JARVIS Voice Wake Listener — Completely Silent Launcher
' Runs in the background without any terminal or command prompt window.
' Listens for "Hey JARVIS" / "Hay JARVIS" to open the interface.
' ============================================================
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ScriptDir
WshShell.Run "cmd.exe /c start_jarvis_voice.bat", 0, False
