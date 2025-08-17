import os
from google.cloud import speech

import google.cloud.speech
print(google.cloud.speech.__file__)
print(google.cloud.speech.__version__)

# 서비스 계정 키 경로
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "data/speach-to-text-463406-b20d087d5f86.json"

def transcribe_diarization_gcs(gcs_uri):
    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(uri=gcs_uri)ㄴ
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.MP3,  # 파일에 따라 조정
        language_code="ko-KR",
#         enable_speaker_diarization=True,
#         diarization_speaker_count=6  # 발화자 예상 수 (2명 이상 가능)
    )

    operation = client.long_running_recognize(config=config, audio=audio)
    response = operation.result(timeout=600)

    diarization_result = []
    for result in response.results:
        alternative = result.alternatives[0]
        for word_info in alternative.words:
            speaker_tag = word_info.speaker_tag
            diarization_result.append((speaker_tag, word_info.word))

    # 화자별 발화 묶기
    transcript = ""
    prev_speaker = None
    sentence = []
    for speaker, word in diarization_result:
        if prev_speaker is None:
            prev_speaker = speaker
        if speaker != prev_speaker:
            transcript += f"[Speaker {prev_speaker}]: {' '.join(sentence)}\n"
            sentence = []
            prev_speaker = speaker
        sentence.append(word)
    if sentence:
        transcript += f"[Speaker {prev_speaker}]: {' '.join(sentence)}\n"
    return transcript


# 사용 예시
gcs_uri = "gs://chick-stt/yourfile.mp3"
text = transcribe_diarization_gcs(gcs_uri)

print(text)
