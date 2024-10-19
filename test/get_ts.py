import os
import requests
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import subprocess
import time

def download_video_from_m3u8(url, output_filename):
    # Setup headless Chromeo
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Start WebDriver with selenium-wire for network monitoring
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        # Open the URL
        driver.get(url)

        # Wait for a few seconds to let the page load and m3u8 file to appear in network traffic
        time.sleep(2)

        # Extract the m3u8 URL from the network requests
        m3u8_url = None
        for request in driver.requests:
            if request.response and 'm3u8' in request.url:
                m3u8_url = request.url
                break

        if not m3u8_url:
            print("No m3u8 URL found.")
            return

        # Download the m3u8 file
        download_m3u8(m3u8_url, "temp.m3u8")

        # Convert m3u8 to mp4 using ffmpeg
        convert_m3u8_to_mp4("temp.m3u8", output_filename)

        print(f"Video saved as {output_filename}")

    finally:
        driver.quit()
        if os.path.exists("temp.m3u8"):
            os.remove("temp.m3u8")

def download_m3u8(m3u8_url, output_filename):
    response = requests.get(m3u8_url)
    with open(output_filename, 'wb') as f:
        f.write(response.content)

def convert_m3u8_to_mp4(m3u8_file, output_filename):
    command = [
        "ffmpeg",
        "-i", m3u8_file,
        "-c", "copy",
        output_filename
    ]
    subprocess.run(command, check=True)

if __name__ == "__main__":
    url = "https://www.pandalive.co.kr/live/play/eerttyui12"
    output_filename = "output.mp4"

    download_video_from_m3u8(url, output_filename)
