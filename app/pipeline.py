import asyncio
import logging
import time
from pathlib import Path

from app.audio.chunking import Chunk, plan_cuts, split_audio
from app.audio.convert import to_wav
from app.audio.probe import probe_duration
from app.audio.silence import find_silences
from app.core.config import (
    CHUNK_MAX_SECONDS,
    CHUNK_TARGET_SECONDS,
    CHUNK_WINDOW_SECONDS,
    SILENCE_MIN_SECONDS,
    SILENCE_NOISE_DB,
)
from app.jobs.store import JobStore
from app.processing.align import align_chunks
from app.processing.stitch import read_cues, stitch
from app.schemas.job import JobStats, Stage
from app.schemas.minutes import Minutes
from app.services.diarization import Diarization
from app.services.minutes import MinutesWriter
from app.services.teams import TeamsClient
from app.services.transcription import Transcriber

log = logging.getLogger(__name__)


def timed_run(diarizer, wav: Path) -> tuple[Diarization, float]:
    started = time.monotonic()
    result = diarizer.run(wav)
    return result, time.monotonic() - started


class Pipeline:
    def __init__(self, store: JobStore, transcriber: Transcriber, diarizers: dict, minutes_writer: MinutesWriter, teams: TeamsClient | None = None):
        self.store = store
        self.transcriber = transcriber
        self.diarizers = diarizers
        self.minutes_writer = minutes_writer
        self.teams = teams

    async def run_teams(self, job_id: str, meeting_id: str, recording_id: str):
        try:
            self.store.update(job_id, stage=Stage.downloading)
            work = self.store.dir(job_id)
            await self.teams.download_recording(meeting_id, recording_id, work / "source.mp4")
            await self._save_teams_transcript(job_id, meeting_id, work)
            self.store.update(job_id, source="source.mp4")
        except Exception as exc:
            log.exception("job %s failed during download", job_id)
            self.store.update(job_id, stage=Stage.failed, error=str(exc) or type(exc).__name__, error_stage=Stage.downloading)
            return
        await self.run(job_id)

    async def run(self, job_id: str):
        started = time.monotonic()
        stage = Stage.extracting
        try:
            job = self.store.update(job_id, stage=stage)
            work = self.store.dir(job_id)
            wav = await asyncio.to_thread(to_wav, work / job.source, work / "audio.wav")
            duration = await asyncio.to_thread(probe_duration, wav)

            stage = Stage.analyzing
            self.store.update(job_id, stage=stage)
            log.info("job %s analyzing %.1fs of audio with %s", job_id, duration, job.engine)
            chunks = await asyncio.to_thread(self._chunks, wav, work, duration)
            (texts, timings), (diarization, diarization_seconds) = await asyncio.gather(
                self.transcriber.transcribe(chunks),
                asyncio.to_thread(timed_run, self.diarizers[job.engine], wav),
            )
            text_chunks = [{"start": c.start, "end": c.end, "text": t} for c, t in zip(chunks, texts)]
            anchors = [w for words in timings for w in words]
            self.store.write(job_id, "text", text_chunks)
            self.store.write(job_id, "timing", anchors)
            self.store.write(job_id, "speakers", diarization.segments)

            stage = Stage.stitching
            self.store.update(job_id, stage=stage)
            result = stitch(align_chunks(text_chunks, anchors), diarization, read_cues(work))
            self.store.write(job_id, "words", result.words)
            self.store.write(job_id, "transcript", result.turns)

            stage = Stage.minutes
            self.store.update(job_id, stage=stage, speaker_names=result.names)
            self.store.write(job_id, "minutes", await self.minutes_writer.write(result.turns, result.names))

            stats = JobStats(
                duration_seconds=round(duration, 2),
                speakers=len({t.speaker for t in result.turns}),
                turns=len(result.turns),
                words=len(result.words),
                diarization_seconds=round(diarization_seconds, 2),
                teams_agreement=result.agreement["accuracy"] if result.agreement else None,
                processing_seconds=round(time.monotonic() - started, 1),
            )
            self.store.update(job_id, stage=Stage.done, stats=stats)
            log.info("job %s done in %.1fs, %s diarized in %.1fs", job_id, stats.processing_seconds, job.engine, diarization_seconds)
        except Exception as exc:
            log.exception("job %s failed during %s", job_id, stage.value)
            self.store.update(job_id, stage=Stage.failed, error=str(exc) or type(exc).__name__, error_stage=stage)

    async def regenerate_minutes(self, job_id: str) -> Minutes:
        job = self.store.require_done(job_id)
        minutes = await self.minutes_writer.write(self.store.load_turns(job_id), job.speaker_names)
        self.store.write(job_id, "minutes", minutes)
        return minutes

    async def _save_teams_transcript(self, job_id: str, meeting_id: str, work: Path):
        try:
            vtt = await self.teams.transcript(meeting_id)
        except Exception as exc:
            log.warning("job %s has no Teams transcript, continuing without names: %s", job_id, str(exc)[:200])
            return
        if vtt:
            (work / "teams.vtt").write_text(vtt)

    def _chunks(self, wav: Path, work: Path, duration: float) -> list[Chunk]:
        if duration <= CHUNK_MAX_SECONDS:
            return [Chunk(path=wav, start=0.0, end=duration)]
        silences = find_silences(wav, SILENCE_NOISE_DB, SILENCE_MIN_SECONDS)
        cuts = plan_cuts(duration, silences, CHUNK_TARGET_SECONDS, CHUNK_WINDOW_SECONDS, CHUNK_MAX_SECONDS)
        return split_audio(wav, work / "chunks", duration, cuts)
