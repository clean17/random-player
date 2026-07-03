"""Gemini REST API 테스트 (Python 3.8 호환).

SDK(google-genai / google-generativeai)는 Python 3.9+ 를 요구하므로,
Python 3.8 환경에서는 REST API 를 requests 로 직접 호출한다.

API 키는 프로젝트 루트의 .env 파일에서 읽는다:
    GEMINI_API_KEY=발급받은_키
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODEL = "gemini-2.5-flash"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(MODEL)


def generate(prompt):
    if not API_KEY:
        raise SystemExit("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")

    resp = requests.post(
        URL,
        headers={"x-goog-api-key": API_KEY, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


if __name__ == "__main__":
    print(generate("Explain how AI works in a few words"))
