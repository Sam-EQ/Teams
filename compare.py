import argparse
import json
import logging
import sys
from collections import defaultdict

from pydantic import TypeAdapter
from pydantic_core import to_json

from app.audio.probe import probe_duration
from app.core.config import DATA_DIR, ENGINES
from app.jobs.store import JobStore
from app.main import LOG_FORMAT
from app.pipeline import timed_run
from app.processing.align import align_chunks
from app.processing.stitch import read_cues, stitch
from app.schemas.transcript import Word
from app.services.diarization import build_diarizer
from app.services.minutes import clock

WORDS = TypeAdapter(list[Word])


def talk_time(turns) -> dict[str, float]:
    totals = defaultdict(float)
    for t in turns:
        totals[t.speaker] += t.duration
    return dict(sorted(totals.items()))


def run_engine(engine: str, wav, words, cues, duration: float) -> dict:
    diarization, seconds = timed_run(build_diarizer(engine), wav)
    result = stitch(words, diarization, cues)
    return {
        "engine": engine,
        "speakers": len({t.speaker for t in result.turns}),
        "turns": len(result.turns),
        "seconds": round(seconds, 2),
        "realtime_factor": round(duration / seconds, 1) if seconds else None,
        "talk_time": {s: round(v, 1) for s, v in talk_time(result.turns).items()},
        "names": result.names,
        "teams_agreement": result.agreement,
        "transcript": result.turns,
    }


def print_report(report: dict, duration: float, has_cues: bool):
    print(f"\naudio {clock(duration)}, Teams transcript {'found' if has_cues else 'missing, no agreement score'}\n")
    print(f"{'engine':<10} {'speakers':>8} {'turns':>6} {'seconds':>8} {'x realtime':>11} {'teams agreement':>16}")
    for r in report.values():
        agreement = r["teams_agreement"]
        score = f"{agreement['accuracy']:.1%} of {agreement['words']}" if agreement else "-"
        print(f"{r['engine']:<10} {r['speakers']:>8} {r['turns']:>6} {r['seconds']:>8} {r['realtime_factor'] or '-':>11} {score:>16}")
    for r in report.values():
        print(f"\n{r['engine']} talk time")
        for speaker, seconds in r["talk_time"].items():
            name = r["names"].get(speaker, "")
            print(f"  {speaker:<11} {name:<24} {clock(seconds)}")


def main():
    parser = argparse.ArgumentParser(description="Run every diarization engine on a finished job and compare them")
    parser.add_argument("job_id")
    parser.add_argument("--engines", nargs="+", default=ENGINES, choices=ENGINES)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format=LOG_FORMAT)

    work = JobStore(DATA_DIR).dir(args.job_id)
    missing = [name for name in ("audio.wav", "text.json", "timing.json") if not (work / name).exists()]
    if missing:
        print(f"job {args.job_id} has no {', '.join(missing)}, run it through the current pipeline first")
        sys.exit(1)

    wav = work / "audio.wav"
    duration = probe_duration(wav)
    words = align_chunks(json.loads((work / "text.json").read_text()), WORDS.validate_json((work / "timing.json").read_bytes()))
    cues = read_cues(work)

    report = {engine: run_engine(engine, wav, words, cues, duration) for engine in args.engines}
    print_report(report, duration, bool(cues))
    (work / "compare.json").write_bytes(to_json(report, indent=2))
    print(f"\nfull transcripts per engine: {work / 'compare.json'}")


if __name__ == "__main__":
    main()
