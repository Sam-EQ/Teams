import logging
import threading
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForAudioFrameClassification, AutoProcessor

from app.audio.convert import load_samples
from app.core.config import DEVICE, DIARIZATION_THRESHOLD, MODEL_DIR, MODEL_ID, SAMPLE_RATE
from app.schemas.transcript import SpeakerSegment
from app.services.diarization import Diarization

log = logging.getLogger(__name__)


def pick_device() -> str:
    if DEVICE:
        return DEVICE
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class NemotronDiarizer:
    def __init__(self):
        source = str(MODEL_DIR) if (MODEL_DIR / "config.json").exists() else MODEL_ID
        self.device = pick_device()
        log.info("loading %s on %s", source, self.device)
        self.processor = AutoProcessor.from_pretrained(source)
        self.model = AutoModelForAudioFrameClassification.from_pretrained(source).to(self.device).eval()
        self.lock = threading.Lock()

    def health(self) -> dict:
        return {"ok": True, "device": self.device}

    def run(self, wav: Path) -> Diarization:
        audio = load_samples(wav)
        if not len(audio):
            return Diarization(probs=np.zeros((0, 1), dtype=np.float32), segments=[])
        inputs = self.processor(audio, sampling_rate=SAMPLE_RATE)
        mask = inputs.attention_mask
        with self.lock, torch.inference_mode():
            logits = self.model(**inputs.to(self.device, dtype=self.model.dtype)).logits.float().cpu()
        raw = self.processor.extract_speaker_dict(logits, mask, threshold=DIARIZATION_THRESHOLD)[0]
        segments = [SpeakerSegment(start=float(s["Start"]), end=float(s["End"]), speaker=f"speaker_{s['Speaker']}") for s in raw]
        probs = logits[0, : int(mask[0].sum())].sigmoid().numpy()
        return Diarization(probs=probs, segments=sorted(segments, key=lambda s: s.start))
