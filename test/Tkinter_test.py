import tkinter as tk
import subprocess

def open_folder_test():
    folder_path = r"\\wsl.localhost\docker-desktop-data\data\docker\volumes\igdata\_data"  # 원하는 경로
    subprocess.Popen(f'explorer "{folder_path}"')

root = tk.Tk()
button = tk.Button(root, text="폴더 열기", command=open_folder_test)
button.pack(pady=20)

root.mainloop()