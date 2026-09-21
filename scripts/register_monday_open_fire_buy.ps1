# 2026-09-21(월) 09:00:05 1회성 작업 등록 — 모의계좌 fire 매수예약 종목을 장 시작 직후 매수.
# 배경: auto_trading/monday_open_fire_buy_20260921.py 헤더 참고. 정기 15:21 fire 매수와는
# 별개의 1회성 예외 실행이며, 정기 스케줄러(job/batch_runner.py)는 건드리지 않는다.
#
# 실행 후 태스크는 자동으로 남아있으므로(1회 실행 후 Ready 상태 유지), 확인 후
# Unregister-ScheduledTask -TaskName 'MondayOpenFireBuy_20260921' -Confirm:$false 로 정리할 것.

$ErrorActionPreference = 'Stop'

$TaskName = 'MondayOpenFireBuy_20260921'
$RepoRoot = 'C:\my-project\random-player'
$PythonExe = Join-Path $RepoRoot 'venv\Scripts\python.exe'
$Script = Join-Path $RepoRoot 'auto_trading\monday_open_fire_buy_20260921.py'
$LogFile = Join-Path $RepoRoot 'logs\kiwoom_trading\monday_open_fire_buy_20260921.log'

New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null

$Cmd = "chcp 65001>NUL & `"$PythonExe`" -X utf8 `"$Script`" >> `"$LogFile`" 2>&1"
$Action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c $Cmd" -WorkingDirectory $RepoRoot

$Trigger = New-ScheduledTaskTrigger -Once -At '2026-09-21T09:00:05'

$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew

$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Principal $Principal -Force | Out-Null

Write-Output "등록 완료: '$TaskName' — 2026-09-21 09:00:05 1회 실행"
Write-Output "로그: $LogFile"
Write-Output "확인: Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Write-Output "삭제: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
