# Meeting Transcription API

Upload a meeting recording, or import one straight from Microsoft Teams, and get a speaker-separated
transcript and minutes of meeting.

- Text: OpenAI `gpt-transcribe`, with a prompt and keyword hints
- Word timing: OpenAI `whisper-1` word timestamps
- Who spoke when, one of two engines chosen per job:
  - `nemotron`: [`nvidia/Nemotron-3-Diarization`](https://huggingface.co/nvidia/Nemotron-3-Diarization) through Transformers, offline mode, on the local GPU
  - `who`: [Desert Ant Labs Who](https://huggingface.co/desert-ant-labs/who) through its Node SDK, on the CPU, as a small service in `engines/who/`
- Minutes: OpenAI (`MINUTES_MODEL`) with structured output

## How it works

1. The upload is converted to 16 kHz mono audio. Recordings over 12 minutes are split at silence near every
   10 minutes, because OpenAI accepts at most 25 MB per request.
2. Three passes run in parallel on the same audio:
   - `gpt-transcribe` writes the text, one chunk after another, each prompt carrying the end of the previous chunk
     and the `KEYWORDS` list.
   - `whisper-1` returns word timestamps for every chunk.
   - The job's diarization engine runs over the whole recording. Nemotron, in offline mode, returns the probability of
     each of up to 8 speakers every 10 ms. Who returns speaker turns, which are turned into the same 10 ms grid, so
     everything after this step is identical for both engines.
3. The `gpt-transcribe` words are matched to the `whisper-1` words. Matched words take whisper's times, the rest
   are spread evenly between their matched neighbours.
4. Each word goes to the speaker with the highest average probability over that word. Words with no
   speech under them take the speaker of the word before. A run of one or two words between two runs of the same
   speaker is merged into that speaker, unless it ends a sentence.
5. Consecutive words from the same speaker become turns, then the minutes are written.

## Setup

Requirements: Python 3.11+, git, ffmpeg, an NVIDIA GPU.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./download_model.sh
cp .env.example .env
```

Put your OpenAI key in `.env`, and put product names, project names and people's names in `KEYWORDS`. Transformers
is installed from source because Nemotron 3 Diarization support isn't in a PyPI release yet. `download_model.sh`
fetches only `config.json`, `processor_config.json` and `model.safetensors` (~400 MB).

## Who engine

Who runs in its own Node service. It needs Node 22 or newer.

```
cd engines/who
npm install
npm start
```

The first start downloads the model (about 32 MB) into `models/who/`; later starts load it from there. The service
listens on `127.0.0.1:8090`. Start it before sending `who` jobs. Nemotron jobs don't need it.

On Linux the SDK runs the 8-bit LiteRT build on the CPU. It's the only build Desert Ant publishes for Linux: the
float16 build is Core ML and runs only on Apple devices. LiteRT uses half the machine's cores, at most 8; set
`DAL_LITERT_THREADS` to change that.

| Env var (engines/who) | Default        |                                                                          |
| --------------------- | -------------- | ------------------------------------------------------------------------ |
| `WHO_PORT`            | `8090`         |                                                                          |
| `WHO_HOST`            | `127.0.0.1`    |                                                                          |
| `WHO_MODEL_DIR`       | `models/who`   | where the model is cached                                                |
| `WHO_MIN_SHARE`       | `0`            | drop speakers under this share of the speech, for laughs or jingles that get their own number. `0` keeps everyone |
| `DAL_LITERT_THREADS`  | half the cores |                                                                          |

```
tmux new -s who
cd engines/who && npm start
```

## Comparing engines

```
python compare.py <job_id>
python compare.py <job_id> --engines who
```

`compare.py` runs each engine on a finished job's `audio.wav` and reuses its `text.json` and `timing.json`, so OpenAI is
not called again. It prints speakers, turns, diarization time and how many times faster than real time each engine
ran, then talk time per speaker. Full transcripts per engine go to `data/<id>/compare.json`.

When the job has a Teams transcript, each engine also gets a **Teams agreement** score: for words that one Teams
participant was speaking alone, the share that the engine gave to that participant. People on their own device are
known for sure by Teams, so this is a real accuracy number with no hand labelling. Words from a shared room device
count as that one participant, so meetings with room devices score lower for any engine that splits the room
correctly; compare engines on meetings where everyone joins on their own device.

Every job also records `diarization_seconds` and, with a Teams transcript, `teams_agreement` in its stats.

## Run on EC2

```
tmux new -s meeting
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Detach with `Ctrl+B` then `D`. For a public HTTPS link:

```
tmux new -s tunnel
cloudflared tunnel --url http://localhost:8001
```

Print the link later with:

```
tmux capture-pane -pt tunnel -S -500 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
```

Interactive docs are at `<link>/docs`. The link changes whenever the tunnel restarts, and anyone with it can use the API.

From the terminal, without the server:

```
python cli.py samples/meeting.mp4
python cli.py samples/meeting.mp4 --engine who
```

## API

| Method  | Route                   |                                                                                          |
| ------- | ----------------------- | ---------------------------------------------------------------------------------------- |
| `GET`   | `/health`               | each engine's status, model names, keywords                                              |
| `POST`  | `/jobs`                 | multipart `file`, any format ffmpeg reads, optional `engine` → `202` with the job        |
| `POST`  | `/jobs/teams`           | `{"join_url": "...", "engine": "who"}`, imports the meeting's latest Teams recording → `202` with the job |
| `GET`   | `/jobs/{id}`            | stage, error, stats                                                                      |
| `GET`   | `/jobs/{id}/events`     | SSE, one event per stage change                                                          |
| `GET`   | `/jobs/{id}/transcript` | turns with speaker names applied                                                         |
| `GET`   | `/jobs/{id}/minutes`    | structured minutes                                                                       |
| `PATCH` | `/jobs/{id}/speakers`   | `{"speaker_0": "Ramu"}`, an empty string removes a name                                  |
| `POST`  | `/jobs/{id}/minutes`    | regenerate minutes with the current names                                                |

```
curl -F "file=@meeting.mp4" http://localhost:8001/jobs
curl -F "file=@meeting.mp4" -F "engine=who" http://localhost:8001/jobs
curl -N http://localhost:8001/jobs/<id>/events
curl http://localhost:8001/jobs/<id>/transcript
curl http://localhost:8001/jobs/<id>/minutes
```

Stages: `queued → (downloading) → extracting → analyzing → stitching → minutes → done`, or `failed` with `error_stage`.
Errors: `404` unknown job or meeting, `409` job not finished or recording not ready, `413` upload too large, `415` not a media file, `422` unknown speaker or engine,
`502` Microsoft Graph error, `503` Teams import not configured.

## Teams import

`POST /jobs/teams` reads meetings through Microsoft Graph with an app-only token. It needs an Entra app with
admin consent for `OnlineMeetings.Read.All`, `OnlineMeetingRecording.Read.All` and `OnlineMeetingTranscript.Read.All`,
and a Teams application access policy covering the organiser. Set `TEAMS_TENANT_ID`, `TEAMS_CLIENT_ID`,
`TEAMS_CLIENT_SECRET` and `TEAMS_ORGANIZER_ID` (the organiser's Entra object ID) in `.env`. Only meetings that
organiser scheduled can be imported, and Record must have been pressed in the meeting.

```
curl -X POST -H "Content-Type: application/json" \
  -d '{"join_url": "https://teams.microsoft.com/l/meetup-join/..."}' http://localhost:8001/jobs/teams
```

The meeting and its recording are looked up before the job is created, so a wrong link returns `404` and a
recording that is still processing returns `409` straight away. The MP4 then downloads in the background.

When the meeting also has a Teams transcript, it is saved as `teams.vtt` and used to name the speakers: each Teams
participant is matched to the speaker whose turns they overlap most, one name per speaker. People sharing a room
microphone appear as one Teams participant, so only one of them gets the name. The rest can be renamed with
`PATCH /jobs/{id}/speakers`. Reading Teams transcripts needs Graph transcript access switched on in the Teams admin
center; without it the import still works, just without names.

## Job files

Each job lives in `data/<id>/`:

| File              |                                                         |
| ----------------- | ------------------------------------------------------- |
| `job.json`        | stage, error, speaker names, stats                      |
| `text.json`       | `gpt-transcribe` text per chunk                         |
| `timing.json`     | `whisper-1` words with timestamps                       |
| `speakers.json`   | the engine's segments: who spoke when                   |
| `words.json`      | final words with time and speaker                       |
| `teams.vtt`       | Teams transcript, only for Teams imports that have one  |
| `transcript.json` | final turns                                             |
| `minutes.json`    | minutes                                                 |
| `compare.json`    | written by `compare.py`                                 |

When a line has the wrong words, look at `text.json`. When it has the wrong speaker, compare `words.json` with
`speakers.json` for that time range.

## Configuration

| Env var                                                                           | Default                                          |                                                               |
| --------------------------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------- |
| `OPENAI_API_KEY`                                                                  |                                                  | required                                                      |
| `TRANSCRIBE_MODEL`                                                                | `gpt-transcribe`                                 | text                                                          |
| `TIMING_MODEL`                                                                    | `whisper-1`                                      | word timestamps                                               |
| `MINUTES_MODEL`                                                                   | `gpt-5.6-sol`                                    |                                                               |
| `TRANSCRIBE_CONCURRENCY`                                                          | `4`                                              | parallel OpenAI requests                                      |
| `TRANSCRIBE_PROMPT`                                                               | `A recorded work meeting with several speakers.` | context sent with every chunk                                 |
| `KEYWORDS`                                                                        |                                                  | comma-separated terms the speakers use, also given to minutes |
| `LANGUAGES`                                                                       | auto                                             | comma-separated codes, for example `en,ta`                    |
| `DIARIZATION_ENGINE`                                                              | `nemotron`                                       | engine for jobs that don't name one: `nemotron` or `who`      |
| `DIARIZATION_THRESHOLD`                                                           | `0.2`                                            | lowest speaker probability that counts as speech              |
| `WHO_URL`                                                                         | `http://127.0.0.1:8090`                          | the Who service                                               |
| `WHO_TIMEOUT_SECONDS`                                                             | `600`                                            |                                                               |
| `DEVICE`                                                                          | auto (`cuda` → `mps` → `cpu`)                    | force a device                                                |
| `MAX_UPLOAD_MB`                                                                   | `2048`                                           |                                                               |
| `TEAMS_TENANT_ID`, `TEAMS_CLIENT_ID`, `TEAMS_CLIENT_SECRET`, `TEAMS_ORGANIZER_ID` |                                                  | enable `POST /jobs/teams`                                     |
| `TEAMS_LOGIN_URL`, `TEAMS_GRAPH_URL`                                              | Microsoft endpoints                              |                                                               |

Keywords are hints. Keep the list to terms that are actually said in your meetings, since unused terms can
occasionally appear in the text.

## Limits

- Nemotron labels up to 8 speakers. Who labels up to 4 speakers in each five-minute section and matches voices across
  sections. Who misses more speech on far-field room audio and when people talk over each other. Speakers are labelled
  `speaker_0`, `speaker_1`, … by each engine.
- When two speakers overlap in Who's output, a word goes to the lower-numbered one.
- Who's license (Desert Ant Labs Source-Available 1.0) is written for on-device apps. Running it server-side on client
  meetings needs written confirmation from Desert Ant Labs before production. Its native core also contacts Desert
  Ant's license server; the audio itself stays on the machine.
- Overlapping speech comes out as one stream of text. Each word goes to the most likely speaker, so a word said
  over someone else can land on the louder person.
- Nemotron's offline mode processes the recording in chunks internally, so GPU memory stays flat for long meetings.
- Jobs that were running when the server stopped are marked `failed` on the next start.

## Layout

```
app/
  core/          config, errors
  audio/         probe, convert (wav, samples, cut), silence, chunking
  services/      transcription (OpenAI text + timing), diarization (engine registry), nemotron, who, minutes, teams (Graph)
  processing/    align (text → word times), grid (turns → 10 ms grid), assign (word → speaker), turns,
                 names (Teams → speakers), score (agreement with Teams), stitch
  jobs/          job folders on disk
  schemas/       job, transcript, minutes
  api/           routes
  pipeline.py    stage order
  bootstrap.py   builds the services
  main.py        FastAPI app
engines/who/     Node service for Who
samples/         test media
cli.py           terminal runner, --engine
compare.py       run every engine on a finished job
download_model.sh
```
