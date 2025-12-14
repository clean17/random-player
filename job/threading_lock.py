# lock.py
import os, msvcrt

_lock_fp = None

def acquire_lock(lock_path="scheduler.lock"):
    global _lock_fp
    lock_path = os.path.abspath(lock_path)
    _lock_fp = open(lock_path, "a+")
    try:
        msvcrt.locking(_lock_fp.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise RuntimeError("Scheduler already running (lock held).")
    _lock_fp.write(str(os.getpid()))
    _lock_fp.flush()
