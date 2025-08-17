import os
from google.cloud import speech

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "data/speach-to-text-463406-b20d087d5f86.json"

def transcribe_diarization(audio_file_path):
    client = speech.SpeechClient()
    with open(audio_file_path, "rb") as audio_file:
        content = audio_file.read()

#     audio = speech.RecognitionAudio(content=content)
    audio = speech.RecognitionAudio(uri="gs://chick-stt/yourfile.mp3")
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.MP3,  # mp3 파일이면 MP3
        sample_rate_hertz=16000,
        language_code="ko-KR",
        enable_speaker_diarization=True,
#         diarization_speaker_count=2
    )

    operation = client.long_running_recognize(config=config, audio=audio)
    response = operation.result(timeout=1800)

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

audio_path = "C:/Users/user/Downloads/2025-06-19_10_34_22.mp3"
transcript = transcribe_diarization(audio_path)
print(transcript)
