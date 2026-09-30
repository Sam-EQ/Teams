import asyncio
import logging
import time
from pathlib import Path

from app.audio.chunking import Chunk, plan_cuts, split_audio
from app.audio.convert import cut, to_wav
from app.audio.probe import probe_duration
from app.audio.silence import find_silences
from app.core.config import (
    CHUNK_MAX_SECONDS,
    CHUNK_TARGET_SECONDS,
    CHUNK_WINDOW_SECONDS,
    GAP_MAX_COVERAGE,
    GAP_MIN_SECONDS,
    NAME_MIN_SECONDS,
    REGION_JOIN_SECONDS,
    SILENCE_MIN_SECONDS,
    SILENCE_NOISE_DB,
    TURN_GAP_SECONDS,
)
from app.jobs.store import JobStore
from app.processing.assign import assign
from app.processing.gaps import find_gaps
from app.processing.names import match_names, parse_vtt
from app.processing.turns import merge_turns
from app.schemas.job import JobStats, Stage
from app.schemas.minutes import Minutes
from app.schemas.transcript import SpeakerSegment, TextSegment, Turn
from app.services.minutes import MinutesWriter
from app.services.teams import TeamsClient
from app.services.transcription import Transcriber

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, store: JobStore, transcriber: Transcriber, diarizer, minutes_writer: MinutesWriter, teams: TeamsClient | None = None):
        self.store = store
        self.transcriber = transcriber
        self.diarizer = diarizer
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
            log.info("job %s analyzing %.1fs of audio", job_id, duration)
            segments, speakers = await asyncio.gather(
                self._transcribe(wav, work, duration),
                asyncio.to_thread(self.diarizer.run, wav),
            )
            self.store.write(job_id, "segments", segments)
            self.store.write(job_id, "speakers", speakers)

            stage = Stage.stitching
            self.store.update(job_id, stage=stage)
            filled = await self._fill_gaps(segments, speakers, wav, work)
            self.store.write(job_id, "gaps", filled)
            turns = merge_turns(assign(segments, speakers) + filled, TURN_GAP_SECONDS)
            self.store.write(job_id, "transcript", turns)
            names = self._teams_names(work, speakers)

            stage = Stage.minutes
            self.store.update(job_id, stage=stage, speaker_names=names)
            self.store.write(job_id, "minutes", await self.minutes_writer.write(turns, names))

            stats = JobStats(
                duration_seconds=round(duration, 2),
                speakers=len({t.speaker for t in turns}),
                turns=len(turns),
                gaps_filled=len(filled),
                processing_seconds=round(time.monotonic() - started, 1),
            )
            self.store.update(job_id, stage=Stage.done, stats=stats)
            log.info("job %s done in %.1fs, %d gaps filled", job_id, stats.processing_seconds, stats.gaps_filled)
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
        except Exception:
            log.warning("job %s could not fetch the Teams transcript, continuing without names", job_id, exc_info=True)
            return
        if vtt:
            (work / "teams.vtt").write_text(vtt)

    def _teams_names(self, work: Path, speakers: list[SpeakerSegment]) -> dict[str, str]:
        vtt = work / "teams.vtt"
        if not vtt.exists():
            return {}
        return match_names(parse_vtt(vtt.read_text()), speakers, NAME_MIN_SECONDS)

    async def _transcribe(self, wav: Path, work: Path, duration: float) -> list[TextSegment]:
        chunks = await asyncio.to_thread(self._chunks, wav, work, duration)
        return await self.transcriber.transcribe_chunks(chunks)

    def _chunks(self, wav: Path, work: Path, duration: float) -> list[Chunk]:
        if duration <= CHUNK_MAX_SECONDS:
            return [Chunk(path=wav, offset=0.0)]
        silences = find_silences(wav, SILENCE_NOISE_DB, SILENCE_MIN_SECONDS)
        cuts = plan_cuts(duration, silences, CHUNK_TARGET_SECONDS, CHUNK_WINDOW_SECONDS, CHUNK_MAX_SECONDS)
        return split_audio(wav, work / "chunks", duration, cuts)

    async def _fill_gaps(self, segments: list[TextSegment], speakers: list[SpeakerSegment], wav: Path, work: Path) -> list[Turn]:
        gaps = find_gaps(speakers, segments, GAP_MIN_SECONDS, GAP_MAX_COVERAGE, REGION_JOIN_SECONDS)
        if not gaps:
            return []
        clips = work / "gaps"
        clips.mkdir(exist_ok=True)
        filled = await asyncio.gather(*(self._transcribe_gap(g, wav, clips) for g in gaps))
        return [t for t in filled if t]

    async def _transcribe_gap(self, gap: SpeakerSegment, wav: Path, clips: Path) -> Turn | None:
        clip = await asyncio.to_thread(cut, wav, clips / f"{gap.start:.2f}_{gap.end:.2f}.wav", gap.start, gap.end)
        text = " ".join(s.text for s in await self.transcriber.transcribe(clip, gap.start))
        return Turn(start=gap.start, end=gap.end, speaker=gap.speaker, text=text) if text else None
