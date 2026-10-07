' docker_watchdog.ps1을 완전히 안 보이게 실행하기 위한 래퍼.
'
' 작업 스케줄러에서 powershell.exe를 직접 -WindowStyle Hidden으로 돌려도 콘솔 창(conhost)이
' 생성됐다가 숨김 처리되는 순간의 깜빡임(flash)이 화면에 보일 수 있다(윈도우 콘솔 호스트의
' 알려진 동작). WScript.Shell.Run의 windowStyle=0은 애초에 창을 띄우지 않아 깜빡임이 없다.

Dim fso, scriptDir, psPath
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
psPath = scriptDir & "\docker_watchdog.ps1"

Set shell = CreateObject("WScript.Shell")
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & psPath & """", 0, False
