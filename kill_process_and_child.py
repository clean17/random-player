import subprocess

def kill_process_with_children(pid):
    try:
        subprocess.run(['taskkill', '/PID', str(pid), '/F', '/T'], check=True)
        print(f"Process {pid} and its children have been successfully terminated.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to terminate process {pid} and its children: {e}")

kill_process_with_children(8056)
