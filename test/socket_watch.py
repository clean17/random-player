import psutil
import time
import csv
from datetime import datetime
from collections import Counter, defaultdict
import socket
import os

INTERVAL_SEC = 5
TOP_N = 20
LOG_DIR = "socket_watch_logs"

os.makedirs(LOG_DIR, exist_ok=True)

summary_log = os.path.join(LOG_DIR, "socket_summary.csv")
detail_log = os.path.join(LOG_DIR, "socket_detail.csv")

TCP_STATES = {
    "ESTABLISHED",
    "SYN_SENT",
    "SYN_RECV",
    "FIN_WAIT1",
    "FIN_WAIT2",
    "TIME_WAIT",
    "CLOSE",
    "CLOSE_WAIT",
    "LAST_ACK",
    "LISTEN",
    "CLOSING",
    "NONE",
}


def safe_process_name(pid):
    if pid is None:
        return "NO_PID"
    try:
        p = psutil.Process(pid)
        return p.name()
    except Exception:
        return "UNKNOWN"


def safe_process_exe(pid):
    if pid is None:
        return ""
    try:
        p = psutil.Process(pid)
        return p.exe()
    except Exception:
        return ""


def addr_to_str(addr):
    if not addr:
        return ""
    try:
        return f"{addr.ip}:{addr.port}"
    except Exception:
        return str(addr)


def init_csv():
    if not os.path.exists(summary_log):
        with open(summary_log, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "time",
                "total_tcp",
                "listen",
                "established",
                "time_wait",
                "close_wait",
                "syn_sent",
                "top_process_summary",
            ])

    if not os.path.exists(detail_log):
        with open(detail_log, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "time",
                "pid",
                "process",
                "exe",
                "state",
                "local",
                "remote",
            ])


def collect():
    conns = psutil.net_connections(kind="inet")

    state_counter = Counter()
    proc_counter = Counter()
    proc_state_counter = defaultdict(Counter)

    details = []

    for c in conns:
        status = c.status or "NONE"
        pid = c.pid
        pname = safe_process_name(pid)

        state_counter[status] += 1
        proc_counter[(pid, pname)] += 1
        proc_state_counter[(pid, pname)][status] += 1

        details.append({
            "pid": pid,
            "process": pname,
            "exe": safe_process_exe(pid),
            "state": status,
            "local": addr_to_str(c.laddr),
            "remote": addr_to_str(c.raddr),
        })

    return conns, state_counter, proc_counter, proc_state_counter, details


def print_report(state_counter, proc_counter, proc_state_counter):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total_tcp = sum(state_counter.values())

    print("\n" + "=" * 100)
    print(f"[{now}] TCP/UDP 소켓 감시")
    print("=" * 100)

    print("[상태별 소켓 수]")
    for state, count in state_counter.most_common():
        print(f"{state:15} {count}")

    print("\n[프로세스별 소켓 수 TOP]")
    for (pid, pname), count in proc_counter.most_common(TOP_N):
        states = proc_state_counter[(pid, pname)]
        state_text = ", ".join([f"{s}:{c}" for s, c in states.most_common()])
        print(f"PID={str(pid):>6}  {pname:<30} TOTAL={count:<5}  {state_text}")

    print("\n[주의]")
    print("- TIME_WAIT가 수천~수만 개로 계속 증가하면 임시 포트 고갈 가능성이 큼")
    print("- CLOSE_WAIT가 특정 프로세스에 많이 쌓이면 해당 프로그램이 소켓을 제대로 닫지 못하는 가능성이 큼")
    print("- ESTABLISHED가 특정 프로그램에 과도하게 많으면 그 프로그램이 연결을 많이 유지 중")


def write_logs(state_counter, proc_counter, proc_state_counter, details):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total_tcp = sum(state_counter.values())
    listen = state_counter.get("LISTEN", 0)
    established = state_counter.get("ESTABLISHED", 0)
    time_wait = state_counter.get("TIME_WAIT", 0)
    close_wait = state_counter.get("CLOSE_WAIT", 0)
    syn_sent = state_counter.get("SYN_SENT", 0)

    top_summary = []
    for (pid, pname), count in proc_counter.most_common(10):
        states = proc_state_counter[(pid, pname)]
        state_text = "/".join([f"{s}:{c}" for s, c in states.most_common()])
        top_summary.append(f"{pname}({pid})={count}[{state_text}]")

    with open(summary_log, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            now,
            total_tcp,
            listen,
            established,
            time_wait,
            close_wait,
            syn_sent,
            " | ".join(top_summary),
        ])

    with open(detail_log, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        for d in details:
            writer.writerow([
                now,
                d["pid"],
                d["process"],
                d["exe"],
                d["state"],
                d["local"],
                d["remote"],
            ])


def main():
    init_csv()

    print("소켓 감시 시작")
    print(f"주기: {INTERVAL_SEC}초")
    print(f"요약 로그: {summary_log}")
    print(f"상세 로그: {detail_log}")
    print("종료: Ctrl + C")
    print()
    print("가능하면 관리자 권한 CMD/PowerShell에서 실행하세요.")

    while True:
        try:
            _, state_counter, proc_counter, proc_state_counter, details = collect()
            print_report(state_counter, proc_counter, proc_state_counter)
            write_logs(state_counter, proc_counter, proc_state_counter, details)
            time.sleep(INTERVAL_SEC)
        except KeyboardInterrupt:
            print("\n감시 종료")
            break
        except Exception as e:
            print(f"오류 발생: {e}")
            time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()