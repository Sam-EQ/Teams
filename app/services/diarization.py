import copy
import logging
import threading
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForAudioFrameClassification, AutoProcessor

from app.audio.convert import load_samples
from app.core.config import DEVICE, DIARIZATION_MODE, DIARIZATION_THRESHOLD, MODEL_DIR, MODEL_ID, SAMPLE_RATE
from app.schemas.transcript import SpeakerSegment

log = logging.getLogger(__name__)


def pick_device() -> str:
    if DEVICE:
        return DEVICE
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class Diarizer:
    def __init__(self):
        source = str(MODEL_DIR) if (MODEL_DIR / "config.json").exists() else MODEL_ID
        self.device = pick_device()
        log.info("loading %s on %s in %s mode", source, self.device, DIARIZATION_MODE)
        self.processor = AutoProcessor.from_pretrained(source)
        self.model = AutoModelForAudioFrameClassification.from_pretrained(source).to(self.device).eval()
        modes = ["offline", *self.processor.streaming_modes]
        if DIARIZATION_MODE not in modes:
            raise ValueError(f"DIARIZATION_MODE must be one of {modes}")
        self.lock = threading.Lock()

    def run(self, wav: Path) -> list[SpeakerSegment]:
        audio = load_samples(wav)
        if not len(audio):
            return []
        with self.lock, torch.inference_mode():
            if DIARIZATION_MODE == "offline" or len(audio) < self.processor.num_samples_first_audio_chunk:
                segments = self._offline(audio)
            else:
                segments = self._streaming(audio)
        return sorted(segments, key=lambda s: s.start)

    def _forward(self, inputs, speaker_cache=None):
        return self.model(**inputs.to(self.device, dtype=self.model.dtype), speaker_cache=speaker_cache)

    def _offline(self, audio: np.ndarray) -> list[SpeakerSegment]:
        inputs = self.processor(audio, sampling_rate=SAMPLE_RATE)
        return self._segments(self._forward(inputs).logits, inputs.attention_mask)

    def _streaming(self, audio: np.ndarray) -> list[SpeakerSegment]:
        processor = copy.deepcopy(self.processor)
        processor.set_streaming_mode(DIARIZATION_MODE)
        logits = []
        cache = None
        mel_frame = 0
        start = 0

        def step(chunk: np.ndarray, first: bool, last: bool):
            nonlocal cache, mel_frame, start
            inputs = processor(chunk, sampling_rate=SAMPLE_RATE, is_streaming=True, is_first_audio_chunk=first, is_last_audio_chunk=last)
            out = self._forward(inputs, cache)
            cache = out.speaker_cache
            logits.append(out.logits)
            mel_frame += processor.num_mel_frames_per_step
            start = processor.audio_chunk_start(mel_frame)

        while True:
            size = processor.num_samples_first_audio_chunk if mel_frame == 0 else processor.num_samples_per_audio_chunk
            if start + size > len(audio):
                break
            step(audio[start : start + size], first=mel_frame == 0, last=False)
        tail = audio[start:]
        if len(tail) >= processor.feature_extractor.win_length:
            step(tail, first=False, last=True)
        return self._segments(torch.cat(logits, dim=1))

    def _segments(self, logits, attention_mask=None) -> list[SpeakerSegment]:
        raw = self.processor.extract_speaker_dict(logits.float().cpu(), attention_mask, threshold=DIARIZATION_THRESHOLD)[0]
        return [SpeakerSegment(start=float(s["Start"]), end=float(s["End"]), speaker=f"speaker_{s['Speaker']}") for s in raw]
