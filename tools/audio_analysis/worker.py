"""음성 분석 워커 — 오디오 파일을 받아쓰고, 화자를 나누고, 내용을 정리해 result.md 로 저장한다.

Flask(venv, Python 3.8)는 torch/whisper/pyannote 를 못 쓰므로 이 스크립트를 venv_audio(Python 3.12)로
서브프로세스 실행한다 (app/audio.py). 진행 상황은 outdir/status.json 에 계속 덮어쓴다.

    venv_audio/Scripts/python.exe tools/audio_analysis/worker.py --input a.m4a --outdir data/audio_analysis/<id>

단계
  1. ffmpeg 로 16kHz mono wav 변환
  2. faster-whisper 받아쓰기 (단어 단위 타임스탬프)
  3. pyannote 화자분리 — HF_TOKEN 이 없으면 생략하고 화자 구분 없이 대본만 만든다
  4. 단어마다 가장 많이 겹치는 화자 구간을 붙이고, 같은 화자의 연속 발화를 묶는다
  5. 로컬 Ollama 로 요약 — 서버가 없으면 생략 (녹음이 외부로 나가지 않게 클라우드 LLM 은 쓰지 않는다)

환경변수
  HF_TOKEN               pyannote/speaker-diarization-3.1, pyannote/segmentation-3.0 약관 동의한 계정 토큰
  AUDIO_WHISPER_MODEL    기본 large-v3
  AUDIO_OLLAMA_URL       기본 http://127.0.0.1:11434
  AUDIO_OLLAMA_MODEL     기본 exaone3.5:7.8b (한국어 특화)
"""
import argparse
import gc
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

def _load_dotenv():
    """프로젝트 .env 에서 HF_TOKEN / AUDIO_* 를 읽는다 (이미 환경변수로 있으면 그쪽 우선).

    Flask 가 넘겨주긴 하지만 서버를 띄운 파이썬에 python-dotenv 가 없으면 조용히 빠진다 — 워커가 직접 읽는다.
    """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key, val = key.strip(), val.strip().strip('"').strip("'")
                if (key in ('HF_TOKEN', 'HUGGINGFACE_TOKEN') or key.startswith('AUDIO_')) and val and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


_load_dotenv()

import vocab  # noqa: E402
import summarizer  # noqa: E402 — .env 를 읽은 뒤에 import 해야 AUDIO_OLLAMA_* 설정이 반영된다
from summarizer import fmt_ts, fmt_dur  # noqa: E402

WHISPER_MODEL = os.environ.get('AUDIO_WHISPER_MODEL', 'large-v3')
DIARIZATION_MODEL = 'pyannote/speaker-diarization-3.1'

# 같은 화자라도 이만큼 쉬면 발화를 끊는다(초) — 긴 독백이 한 덩어리로 붙는 걸 막는다
UTTERANCE_GAP_SEC = 2.0

# 진행률 구간 배분 (전체 100)
P_CONVERT, P_TRANSCRIBE, P_DIARIZE, P_SUMMARY = 3, 60, 85, 99


class Status:
    def __init__(self, outdir: str):
        self.path = os.path.join(outdir, 'status.json')
        self.data = {'stage': 'running', 'progress': 0, 'message': '', 'started_at': _now()}

    def update(self, progress: Optional[float] = None, message: Optional[str] = None, **extra):
        if progress is not None:
            self.data['progress'] = round(min(max(progress, 0), 100), 1)
        if message is not None:
            self.data['message'] = message
            print('[{}] {:5.1f}% {}'.format(_now(), self.data['progress'], message), flush=True)
        self.data.update(extra)
        self.data['updated_at'] = _now()
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False)
        # Flask 가 폴링으로 읽는 순간과 겹치면 윈도우에서 WinError 5 — 잠깐 기다렸다 재시도
        for i in range(40):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                time.sleep(min(0.01 * (i + 1), 0.1))
        # 계속 막히면 직접 덮어쓴다 (읽기용으로 열린 파일도 쓰기는 허용됨, 읽는 쪽은 깨진 JSON 이면 재시도)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False)
        try:
            os.remove(tmp)
        except OSError:
            pass


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ─────────────────────────── 1. 변환 ───────────────────────────

def convert_to_wav(src: str, dst: str) -> float:
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', src,
           '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', dst]
    subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)
    import soundfile as sf
    return float(sf.info(dst).duration)


# ─────────────────────────── 2. 받아쓰기 ───────────────────────────

def _add_cuda_dll_dirs():
    # ctranslate2 는 cuBLAS/cuDNN DLL 을 PATH 에서 찾는다 — torch(cu124) 휠에 같이 들어 있는 걸 빌려 쓴다
    try:
        import torch
        lib = os.path.join(os.path.dirname(torch.__file__), 'lib')
        if os.path.isdir(lib):
            os.add_dll_directory(lib)
            os.environ['PATH'] = lib + os.pathsep + os.environ.get('PATH', '')
    except Exception:
        pass


def transcribe(wav: str, duration: float, language: str, status: Status) -> Tuple[List[Dict], List[Dict]]:
    """returns (segments, words) — words 는 [{start, end, text}]

    단어장은 받아쓰기 힌트(hotwords)로 넘기지 않는다 — 힌트 목록을 그대로 받아 적는 누출이 생겨서
    받아쓴 뒤 vocab.py 로 교정한다 (자세한 사정은 vocab.py 머리말).
    """
    _add_cuda_dll_dirs()
    from faster_whisper import WhisperModel

    status.update(P_CONVERT, '받아쓰기 모델 로딩 ({})'.format(WHISPER_MODEL))
    try:
        model = WhisperModel(WHISPER_MODEL, device='cuda', compute_type='int8_float16')
        device = 'cuda'
    except Exception as e:
        print('CUDA 로딩 실패, CPU 로 진행: {}'.format(e), flush=True)
        model = WhisperModel(WHISPER_MODEL, device='cpu', compute_type='int8')
        device = 'cpu'

    # 경로를 넘기면 PyAV 로 다시 디코딩하는데 설치된 av 버전과 faster-whisper 가 안 맞는다 — 이미 16kHz mono 라 배열로 넘긴다
    import soundfile as sf
    samples, _ = sf.read(wav, dtype='float32')
    seg_iter, info = model.transcribe(
        samples,
        language=language or None,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={'min_silence_duration_ms': 500},
        # 앞 문맥을 이어 받으면 같은 문장이 무한 반복되는 환각이 잦다 — 통화/회의 녹음에선 끄는 게 낫다
        condition_on_previous_text=False,
    )

    segments, words = [], []
    for seg in seg_iter:
        text = seg.text.strip()
        if not text:
            continue
        segments.append({'start': seg.start, 'end': seg.end, 'text': text})
        for w in (seg.words or []):
            if w.word.strip():
                words.append({'start': w.start, 'end': w.end, 'text': w.word})
        pct = P_CONVERT + (P_TRANSCRIBE - P_CONVERT) * (seg.end / duration if duration else 0)
        status.update(pct, '받아쓰기 중 ({} / {})'.format(fmt_ts(seg.end), fmt_ts(duration)))

    status.update(P_TRANSCRIBE, '받아쓰기 완료 — 언어 {} ({:.0%}), {}'.format(
        info.language, info.language_probability, device), language=info.language)

    del model
    gc.collect()
    return segments, words


# ─────────────────────────── 3. 화자분리 ───────────────────────────

def diarization_options(num_speakers: int, title: str) -> Dict:
    """pyannote 에 넘길 화자 수 조건.

    자동 감지는 통화 녹음에서 화자를 과하게 쪼갠다 — 내 목소리(마이크)와 상대 목소리(전화망 코덱)의 음질이 달라서,
    상대 목소리 일부가 음량·잡음이 바뀌면 별도 인물로 잡힌다 (2026-10-12, 2인 통화가 3명으로 나온 사례).
    삼성 통화 녹음 파일명('통화 홍길동_261008_162732')이면 최대 2명으로 제한한다. 한쪽만 녹음됐을 수도 있어 정확히 2명은 강제하지 않는다.
    """
    if num_speakers:
        return {'num_speakers': num_speakers}
    if is_call_recording(title):
        return {'max_speakers': 2}
    return {}


def is_call_recording(title: str) -> bool:
    name = os.path.basename(title or '').lower()
    return name.startswith(('통화', 'call')) or 'call_' in name or '통화 녹음' in name


def diarize(wav: str, options: Dict, status: Status) -> Optional[List[Tuple[float, float, str]]]:
    token = os.environ.get('HF_TOKEN') or os.environ.get('HUGGINGFACE_TOKEN')
    if not token:
        status.update(P_TRANSCRIBE, 'HF_TOKEN 이 없어 화자분리를 건너뜁니다')
        return None

    import torch
    import soundfile as sf
    from pyannote.audio import Pipeline

    torch.cuda.empty_cache()
    status.update(P_TRANSCRIBE, '화자분리 모델 로딩')
    pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, use_auth_token=token)
    if pipeline is None:
        raise RuntimeError('{} 로딩 실패 — HF 에서 모델 약관 동의 여부와 토큰을 확인하세요'.format(DIARIZATION_MODEL))
    if torch.cuda.is_available():
        pipeline.to(torch.device('cuda'))

    # 파일 경로를 넘기면 torchaudio 백엔드(윈도우에서 자주 깨짐)를 타므로 메모리 waveform 으로 넘긴다
    data, sr = sf.read(wav, dtype='float32', always_2d=True)
    waveform = torch.from_numpy(data.T.copy())

    steps = {'segmentation': 0.3, 'speaker_counting': 0.35, 'embeddings': 0.95, 'discrete_diarization': 1.0}

    def hook(step_name, step_artifact, file=None, total=None, completed=None):
        frac = steps.get(step_name)
        if frac is None:
            return
        if total and completed is not None and step_name == 'embeddings':
            frac = 0.35 + 0.6 * completed / total
        status.update(P_TRANSCRIBE + (P_DIARIZE - P_TRANSCRIBE) * frac, '화자분리 중 ({})'.format(step_name))

    annotation = pipeline({'waveform': waveform, 'sample_rate': sr}, hook=hook, **options)

    turns = [(t.start, t.end, spk) for t, _, spk in annotation.itertracks(yield_label=True)]
    del pipeline
    gc.collect()
    torch.cuda.empty_cache()
    status.update(P_DIARIZE, '화자분리 완료 — {}명'.format(len({t[2] for t in turns})))
    return turns


# ─────────────────────────── 4. 합치기 ───────────────────────────

def assign_speakers(words: List[Dict], turns: List[Tuple[float, float, str]]) -> List[Dict]:
    """단어마다 가장 많이 겹치는 화자를 붙이고 연속된 같은 화자 단어를 발화로 묶는다."""
    labels = {}  # SPEAKER_00 → 화자 1 (처음 말한 순서)
    for _, _, spk in sorted(turns):
        labels.setdefault(spk, '화자 {}'.format(len(labels) + 1))

    utterances = []
    for w in words:
        best, best_ov = None, 0.0
        for s, e, spk in turns:
            ov = min(e, w['end']) - max(s, w['start'])
            if ov > best_ov:
                best, best_ov = spk, ov
        if best is None:  # 화자 구간 사이 틈에 떨어진 단어 — 가장 가까운 구간
            mid = (w['start'] + w['end']) / 2
            best = min(turns, key=lambda t: min(abs(t[0] - mid), abs(t[1] - mid)))[2]
        speaker = labels[best]

        last = utterances[-1] if utterances else None
        if last and last['speaker'] == speaker and w['start'] - last['end'] < UTTERANCE_GAP_SEC:
            last['text'] += w['text']
            last['end'] = w['end']
        else:
            utterances.append({'speaker': speaker, 'start': w['start'], 'end': w['end'], 'text': w['text']})

    for u in utterances:
        u['text'] = u['text'].strip()
    return [u for u in utterances if u['text']]


def segments_as_utterances(segments: List[Dict]) -> List[Dict]:
    return [{'speaker': '화자', 'start': s['start'], 'end': s['end'], 'text': s['text']} for s in segments]


def _load_whisper_cache(path: str, language: str) -> Optional[Dict]:
    """모델·언어가 같을 때만 재사용. 단어 힌트를 넣고 받아쓴 캐시(2026-10-12 한때)는 힌트 누출이 섞였을 수 있어 버린다."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except (OSError, ValueError):
        return None
    if (cache.get('model') != WHISPER_MODEL or cache.get('language_arg') != language
            or cache.get('hotwords') or not cache.get('segments')):
        return None
    return cache


def _read_json_file(path: str) -> Dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_vocabulary(outdir: str) -> Tuple[List[str], List[Tuple[str, str]]]:
    """업로드한 사용자의 단어장 + 업로드 때 적은 이 파일의 단어(job.json hotwords).

    단어장 위치는 app/audio.py dictionary_path() 와 같은 규칙: data/audio_analysis/dictionary/<user>.json
    returns ([용어, ...], [(틀린 말, 바른 말), ...])
    """
    job = _read_json_file(os.path.join(outdir, 'job.json'))
    user = re.sub(r'[^A-Za-z0-9_.-]', '_', job.get('user') or 'unknown')
    dic = _read_json_file(os.path.join(os.path.dirname(os.path.abspath(outdir)), 'dictionary', user + '.json'))
    terms = []
    for w in list(job.get('hotwords') or []) + list(dic.get('hotwords') or []):
        w = str(w).strip()
        if w and w not in terms:
            terms.append(w)
    corrections = [(c.get('from', ''), c.get('to', '')) for c in dic.get('corrections') or [] if c.get('from')]
    return terms, corrections


def summary_input_key(utterances: List[Dict], terms: List[str], prev: Optional[Dict], kind_hint: str) -> str:
    """요약 결과를 좌우하는 입력 전부의 해시 — 같으면 이전 요약을 재사용한다.

    요약 코드(summarizer.py) 자체도 넣는다: 지시문·스키마를 고치면 같은 녹음이라도 새로 만들어야 하니까.
    """
    with open(summarizer.__file__, 'rb') as f:
        code = hashlib.sha1(f.read()).hexdigest()
    payload = {
        'utterances': utterances, 'terms': terms, 'kind': kind_hint, 'model': summarizer.OLLAMA_MODEL, 'code': code,
        'previous': prev and {'id': prev['info']['job_id'],
                              'analysis': hashlib.sha1(json.dumps(prev['analysis'], sort_keys=True,
                                                                  ensure_ascii=False).encode('utf-8')).hexdigest()},
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def load_previous(outdir: str) -> Optional[Dict]:
    """job.json previous_job 으로 지정한 이전 회의의 분석 결과. 같은 사용자의 완료된 작업만 쓴다."""
    job = _read_json_file(os.path.join(outdir, 'job.json'))
    prev_id = job.get('previous_job') or ''
    if not re.fullmatch(r'[0-9a-f]{32}', prev_id) or prev_id == os.path.basename(os.path.abspath(outdir)):
        return None
    prev_dir = os.path.join(os.path.dirname(os.path.abspath(outdir)), prev_id)
    prev_job = _read_json_file(os.path.join(prev_dir, 'job.json'))
    prev = _read_json_file(os.path.join(prev_dir, 'analysis.json'))
    if prev_job.get('user') != job.get('user') or not prev.get('analysis'):
        return None
    a = prev['analysis']
    return {'analysis': a, 'meta': prev.get('meta') or {},
            'info': {'job_id': prev_id, 'title': a.get('title') or prev_job.get('filename', ''),
                     'recorded_at': (prev.get('meta') or {}).get('recorded_at', ''),
                     'created_at': prev_job.get('created_at', '')}}


def _load_diar_cache(path: str, options: Dict) -> Optional[List[Tuple[float, float, str]]]:
    """화자 수 조건이 같을 때만 재사용 — 화자 수를 바꿔 재분석하면 화자분리만 다시 한다."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except (OSError, ValueError):
        return None
    if cache.get('options') != options or not cache.get('turns'):
        return None
    return [tuple(t) for t in cache['turns']]


def _write_text(path: str, text: str):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--title', default='')
    ap.add_argument('--num-speakers', type=int, default=0)
    ap.add_argument('--language', default='ko')
    args = ap.parse_args()

    status = Status(args.outdir)
    t0 = time.time()
    try:
        status.update(0, '오디오 변환 중')
        wav = os.path.join(args.outdir, 'audio.wav')
        duration = convert_to_wav(args.input, wav)
        status.update(P_CONVERT, '변환 완료 — {}'.format(fmt_dur(duration)), duration=duration)

        # 받아쓰기가 가장 오래 걸린다(38분 녹음 ≈ 5~11분) — 재분석(화자 수 변경, 토큰 추가 후 재시도) 때 재사용
        cache_path = os.path.join(args.outdir, 'whisper.json')
        terms, corrections = load_vocabulary(args.outdir)
        cache = _load_whisper_cache(cache_path, args.language)
        if cache:
            segments, words = cache['segments'], cache['words']
            status.update(P_TRANSCRIBE, '이전 받아쓰기 결과 재사용 ({})'.format(WHISPER_MODEL), language=cache['language'])
        else:
            summarizer.ollama_unload()  # 직전 작업의 요약 모델이 아직 GPU 에 남아 있을 수 있다
            segments, words = transcribe(wav, duration, args.language, status)
            if not segments:
                raise RuntimeError('인식된 음성이 없습니다')
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump({'model': WHISPER_MODEL, 'language_arg': args.language,
                           'language': status.data.get('language', args.language),
                           'segments': segments, 'words': words}, f, ensure_ascii=False)

        # 화자분리가 실패해도(토큰·약관·GPU 메모리) 받아쓰기 결과는 살린다 — 이유는 md 에 경고로 남긴다.
        # 결과는 화자 수 설정별로 저장해 두고 재분석(요약만 다시) 때 재사용한다
        diar_cache = os.path.join(args.outdir, 'diarization.json')
        diar_opts = diarization_options(args.num_speakers, args.title or args.input)
        diar_skip = ''
        turns = _load_diar_cache(diar_cache, diar_opts)
        if turns:
            status.update(P_DIARIZE, '이전 화자분리 결과 재사용 ({}명)'.format(len({t[2] for t in turns})))
        else:
            try:
                turns = diarize(wav, diar_opts, status)
                if turns is None:
                    diar_skip = 'HF_TOKEN 미설정'
                else:
                    with open(diar_cache, 'w', encoding='utf-8') as f:
                        json.dump({'options': diar_opts, 'turns': turns}, f)
            except Exception as e:
                traceback.print_exc()
                turns, diar_skip = None, str(e)
                status.update(P_DIARIZE, '화자분리 실패 — 화자 구분 없이 계속: {}'.format(e))
        if turns:
            utterances = assign_speakers(words, turns)
        else:
            utterances = segments_as_utterances(segments)
        # 단어장 교정은 캐시(원본 받아쓰기)에 손대지 않고 매번 적용 — 단어장만 고친 재분석은 받아쓰기 없이 바로 반영된다
        vocab_changes = vocab.apply_vocabulary(utterances, corrections, terms)
        if vocab_changes:
            status.update(P_DIARIZE, '단어장 교정 {}곳: {}'.format(
                sum(c['count'] for c in vocab_changes),
                ', '.join('{}→{}'.format(c['from'], c['to']) for c in vocab_changes[:5])))
        speakers = [s['speaker'] for s in summarizer.speaker_stats(utterances)]

        analysis, summary_skip, compare = None, '', None
        kind_hint = '통화 녹음' if is_call_recording(args.title or args.input) else ''
        prev = load_previous(args.outdir)
        # 요약 입력이 그대로면 LLM 을 다시 돌리지 않고 이전 결과를 쓴다. temperature 0·고정 seed·요청마다 빈 상태로
        # 시작해도 GPU 병렬 연산의 미세한 차이로 긴 회의는 뒤쪽 구간 문장이 갈린다 — 같은 입력에 다른 회의록이
        # 나오지 않게 (2026-10-12). 대화록·단어장·이전 회의·모델·요약 코드 중 하나라도 바뀌면 새로 만든다
        input_key = summary_input_key(utterances, terms, prev, kind_hint)
        old = _read_json_file(os.path.join(args.outdir, 'analysis.json'))
        ok, reason = summarizer.ollama_available()
        if old.get('input_key') == input_key and old.get('analysis'):
            analysis, compare = old['analysis'], old.get('compare')
            status.update(P_SUMMARY, '입력이 같아 이전 요약을 그대로 사용')
        elif not ok:
            summary_skip = reason
            status.update(P_DIARIZE, '요약 생략 — ' + reason)
        else:
            try:
                analysis = summarizer.analyze(utterances, duration, bool(turns), speakers,
                                              lambda p, m: status.update(p, m), P_DIARIZE, P_SUMMARY,
                                              kind_hint=kind_hint, user_terms=terms)
                if prev:
                    status.update(P_SUMMARY, '이전 회의와 비교 중 ({})'.format(prev['info']['title']))
                    compare = summarizer.compare_with_previous(prev['analysis'], prev['meta'], analysis)
                    compare['previous'] = prev['info']
            except Exception as e:
                traceback.print_exc()
                if analysis is None:
                    summary_skip = '요약 중 오류: {}'.format(e)
            finally:
                summarizer.ollama_unload()

        title = args.title or os.path.splitext(os.path.basename(args.input))[0]
        meta = {
            'title': title,
            'recorded_at': summarizer.recorded_at_from_title(title),
            'duration': duration,
            'analyzed_at': _now(),
            'whisper_model': WHISPER_MODEL,
            'elapsed': time.time() - t0,
            'language': status.data.get('language', args.language),
        }
        result = {
            'version': 2,
            'meta': meta,
            'diarized': bool(turns),
            'diar_skip': diar_skip,
            'summary_skip': summary_skip,
            'speakers': summarizer.speaker_stats(utterances),
            'utterances': utterances,
            'vocab_changes': vocab_changes,
            'analysis': analysis,
            'compare': compare,
            'input_key': input_key if analysis else '',
            'minutes_md': summarizer.build_minutes(meta, analysis) if analysis else '',
        }
        _write_text(os.path.join(args.outdir, 'analysis.json'), json.dumps(result, ensure_ascii=False))
        _write_text(os.path.join(args.outdir, 'result.md'),
                    summarizer.build_markdown(meta, analysis, utterances, bool(turns), diar_skip, summary_skip, compare))
        if analysis:
            _write_text(os.path.join(args.outdir, 'minutes.md'), result['minutes_md'])

        os.remove(wav)
        status.update(100, '완료', stage='done', finished_at=_now(),
                      speakers=len(speakers) if turns else 0, summarized=bool(analysis),
                      title=(analysis or {}).get('title') or '')
    except Exception as e:
        traceback.print_exc()
        status.update(message='오류: {}'.format(e), stage='error', finished_at=_now())
        sys.exit(1)


if __name__ == '__main__':
    main()
