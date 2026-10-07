# docker_watchdog.ps1을 작업 스케줄러에 10분 간격 반복 작업으로 등록한다.
# 한 번만 실행하면 됨(재등록하려면 다시 실행 — 기존 작업을 덮어씀).
#
# Docker Desktop은 대화형 세션이 있어야 정상 동작하는 데스크톱 앱이라
# "사용자가 로그온해 있을 때만" 실행되도록 등록한다(SYSTEM 계정으로는 GUI 앱을 못 띄운다).
#
# powershell.exe를 -WindowStyle Hidden으로 직접 실행해도 콘솔 창이 잠깐 깜빡였다 사라지는
# 현상이 있어(conhost 생성 후 숨김 처리되는 타이밍 문제), wscript.exe로 vbs 래퍼를 거쳐
# WScript.Shell.Run(windowStyle=0)으로 띄운다 — 이쪽은 애초에 창 자체를 안 만든다.

$ErrorActionPreference = 'Stop'

$TaskName = 'DockerWatchdog'
$VbsPath = Join-Path $PSScriptRoot 'docker_watchdog_silent.vbs'

$Action = New-ScheduledTaskAction -Execute 'wscript.exe' `
    -Argument "`"$VbsPath`""

# 지금부터 10분마다, 사실상 무기한(10년) 반복
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Principal $Principal -Force | Out-Null

Write-Output "등록 완료: '$TaskName' (10분마다 실행, 사용자 로그온 세션에서만 동작)"
Write-Output "지금 바로 한 번 실행해서 확인하려면: Start-ScheduledTask -TaskName '$TaskName'"
