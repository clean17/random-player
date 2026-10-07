# Docker Desktop 감시/자동복구 스크립트 (2026-09-06)
#
# 왜 필요한가: Docker Desktop(WSL2 백엔드)이 윈도우 재부팅 없이 단독으로 가끔(~5일에 한 번꼴)
# 죽는다. mypg(Postgres) 컨테이너가 이 앱의 DB를 담당하는데, 죽어있는 동안 새로 뜨는 사람이
# 없으면 psycopg_pool이 커넥션을 못 받아 PoolTimeout이 계속 난다(2026-09-06 heartbeat 사고 참고).
# 사용자가 직접 눈치채기 전까지 계속 꺼져있던 문제라, Postgres 포트를 주기적으로 확인해서
# 죽어있으면 Docker Desktop을 자동으로 재시작한다.
#
# 컨테이너(mypg/coturn/iglinux)는 이미 restart policy가 unless-stopped/always라
# Docker Desktop 엔진만 다시 뜨면 컨테이너는 알아서 따라 올라온다 — 이 스크립트가 할 일은
# "Docker Desktop 자체를 다시 띄우는 것"뿐이다.
#
# 등록: 작업 스케줄러에 5~10분 간격 반복 실행으로 등록해서 쓴다(등록은 register_docker_watchdog.ps1 참고).

$ErrorActionPreference = 'Stop'

$LogDir = Join-Path $PSScriptRoot 'logs'
$LogFile = Join-Path $LogDir 'docker_watchdog.log'
$DockerExe = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
$PgPort = 5432
$PgHost = 'localhost'

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-Log($msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $LogFile -Value "$ts $msg" -Encoding utf8
}

# Postgres 포트가 열려 있는지만 빠르게 확인 (도커 자체가 죽었는지 판단하는 대리 지표 —
# 이 프로젝트가 실제로 의존하는 건 이 포트라 이걸 직접 체크하는 게 가장 정확하다)
$ok = Test-NetConnection -ComputerName $PgHost -Port $PgPort -InformationLevel Quiet -WarningAction SilentlyContinue

if ($ok) {
    exit 0  # 정상 — 아무것도 안 하고 조용히 종료 (평상시 로그를 채우지 않는다)
}

Write-Log "[WARN] Postgres($PgHost`:$PgPort) 응답 없음 — Docker Desktop 재시작 시도"

# 이미 떠 있을 수도 있는 프로세스를 먼저 정리하고 다시 띄운다(수동으로 껐다 켜는 것과 동일한 절차)
Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5

Start-Process -FilePath $DockerExe
Write-Log "[INFO] Docker Desktop 재시작 명령 실행함(백엔드 기동에는 1~2분 더 걸릴 수 있음)"
