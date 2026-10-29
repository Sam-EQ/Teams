import asyncio

from openai import AsyncOpenAI, omit

from app.audio.chunking import Chunk
from app.core.config import (
    KEYWORDS,
    LANGUAGES,
    PROMPT_TAIL_WORDS,
    TIMING_MODEL,
    TRANSCRIBE_CONCURRENCY,
    TRANSCRIBE_MODEL,
    TRANSCRIBE_PROMPT,
)
from app.schemas.transcript import Word


def prompt(previous: str) -> str:
    tail = " ".join(previous.split()[-PROMPT_TAIL_WORDS:])
    return f"{TRANSCRIBE_PROMPT} Previous part: {tail}" if tail else TRANSCRIBE_PROMPT


class Transcriber:
    def __init__(self, client: AsyncOpenAI):
        self.client = client
        self.semaphore = asyncio.Semaphore(TRANSCRIBE_CONCURRENCY)

    async def transcribe(self, chunks: list[Chunk]) -> tuple[list[str], list[list[Word]]]:
        texts, timings = await asyncio.gather(self._texts(chunks), asyncio.gather(*(self._timing(c) for c in chunks)))
        return texts, timings

    async def _texts(self, chunks: list[Chunk]) -> list[str]:
        texts = []
        for chunk in chunks:
            texts.append(await self._text(chunk, texts[-1] if texts else ""))
        return texts

    async def _text(self, chunk: Chunk, previous: str) -> str:
        async with self.semaphore:
            with chunk.path.open("rb") as audio:
                result = await self.client.audio.transcriptions.create(
                    model=TRANSCRIBE_MODEL,
                    file=audio,
                    prompt=prompt(previous),
                    keywords=KEYWORDS or omit,
                    languages=LANGUAGES or omit,
                )
        return result.text.strip()

    async def _timing(self, chunk: Chunk) -> list[Word]:
        async with self.semaphore:
            with chunk.path.open("rb") as audio:
                result = await self.client.audio.transcriptions.create(
                    model=TIMING_MODEL,
                    file=audio,
                    prompt=", ".join(KEYWORDS) or omit,
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                )
        return [
            Word(start=w.start + chunk.start, end=w.end + chunk.start, text=w.word.strip())
            for w in result.words or []
            if w.word.strip()
        ]
