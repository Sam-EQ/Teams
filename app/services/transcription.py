import asyncio
from pathlib import Path

from openai import AsyncOpenAI

from app.audio.chunking import Chunk
from app.core.config import TRANSCRIBE_CONCURRENCY, TRANSCRIBE_MODEL
from app.schemas.transcript import TextSegment


class Transcriber:
    def __init__(self, client: AsyncOpenAI):
        self.client = client
        self.semaphore = asyncio.Semaphore(TRANSCRIBE_CONCURRENCY)

    async def transcribe(self, path: Path, offset: float = 0.0, label_prefix: str = "") -> list[TextSegment]:
        async with self.semaphore:
            with path.open("rb") as audio:
                result = await self.client.audio.transcriptions.create(
                    model=TRANSCRIBE_MODEL,
                    file=audio,
                    response_format="diarized_json",
                    chunking_strategy="auto",
                )
        return [
            TextSegment(start=s.start + offset, end=s.end + offset, text=s.text.strip(), label=f"{label_prefix}{s.speaker}")
            for s in result.segments
            if s.text.strip()
        ]

    async def transcribe_chunks(self, chunks: list[Chunk]) -> list[TextSegment]:
        results = await asyncio.gather(*(self.transcribe(c.path, c.offset, f"{i}:") for i, c in enumerate(chunks)))
        return sorted((s for segments in results for s in segments), key=lambda s: s.start)
