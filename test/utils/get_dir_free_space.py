import shutil

def get_drive_free_space(drive):
    total, used, free = shutil.disk_usage(drive)
    free_gb = free / (1024 ** 3)  # Convert bytes to GB
    return free_gb

drive = 'F:'
free_space_gb = get_drive_free_space(drive)
print(f"{drive} 드라이브의 남은 용량: {free_space_gb:.2f} GB")
