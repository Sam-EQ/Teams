import argparse
import asyncio
import logging
import shutil
import sys
from pathlib import Path

from app.audio.probe import probe_duration
from app.bootstrap import build_services
from app.main import LOG_FORMAT
from app.schemas.job import Stage
from app.services.minutes import clock


async def run(path: Path):
    services = build_services()
    job = services.store.create(path.name)
    source = f"source{path.suffix.lower()}"
    shutil.copy(path, services.store.dir(job.id) / source)
    services.store.update(job.id, source=source)

    await services.pipeline.run(job.id)
    await services.client.close()
    job = services.store.get(job.id)

    if job.stage != Stage.done:
        print(f"failed during {job.error_stage.value}: {job.error}")
        sys.exit(1)

    for turn in services.store.load_turns(job.id):
        print(f"[{clock(turn.start)}] {turn.speaker}: {turn.text}")
    print(f"\n{services.store.load_minutes(job.id).model_dump_json(indent=2)}")
    print(f"\n{job.stats.model_dump_json(indent=2)}")
    print(f"\njob folder: {services.store.dir(job.id)}")


def main():
    parser = argparse.ArgumentParser(description="Transcribe a meeting recording with speakers and minutes")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    probe_duration(args.file)
    asyncio.run(run(args.file))


if __name__ == "__main__":
    main()
