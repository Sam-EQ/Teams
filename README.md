# Meeting Transcription API

Upload a meeting recording, or import one straight from Microsoft Teams, and get a speaker-separated
transcript and minutes of meeting.

- Text and timestamps: OpenAI `gpt-4o-transcribe-diarize`
- Who spoke when: `[nvidia/Nemotron-3-Diarization](https://huggingface.co/nvidia/Nemotron-3-Diarization)` through Transformers, on the local GPU
- Minutes: OpenAI (`MINUTES_MODEL`) with structured output

## How it works

1. The upload is converted to 16 kHz mono audio.
2. OpenAI and Nemotron run on the same audio in parallel. Recordings over 12 minutes are split at silence
  near every 10 minutes for OpenAI (25 MB upload limit). Nemotron always sees the whole recording, so speaker
   labels stay consistent.
3. Each OpenAI segment keeps its text exactly and goes to the Nemotron speaker it overlaps most.
  OpenAI's own speaker labels are kept in `segments.json` for reference but not used.
4. Speech Nemotron heard for at least `GAP_MIN_SECONDS` that no OpenAI text covers is cut out, transcribed
  on its own and given to that speaker. This recovers speech OpenAI drops, for example under laughter.
5. Back-to-back lines from the same speaker are merged into turns, then the minutes are written.

Overlapping speech is never cut up and re-transcribed, because short or overlapping clips make the model invent text.

## Setup

Requirements: Python 3.11+, git, ffmpeg, an NVIDIA GPU.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./download_model.sh
cp .env.example .env
```

Put your OpenAI key in `.env`. Transformers is installed from source because Nemotron 3 Diarization support
isn't in a PyPI release yet. `download_model.sh` fetches only `config.json`, `processor_config.json` and
`model.safetensors` (~400 MB).

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
```



## API


| Method  | Route                   |                                                                                          |
| ------- | ----------------------- | ---------------------------------------------------------------------------------------- |
| `GET`   | `/health`               | device, diarization mode, model names                                                    |
| `POST`  | `/jobs`                 | multipart `file`, any format ffmpeg reads → `202` with the job                           |
| `POST`  | `/jobs/teams`           | `{"join_url": "..."}`, imports the meeting's latest Teams recording → `202` with the job |
| `GET`   | `/jobs/{id}`            | stage, error, stats                                                                      |
| `GET`   | `/jobs/{id}/events`     | SSE, one event per stage change                                                          |
| `GET`   | `/jobs/{id}/transcript` | turns with speaker names applied                                                         |
| `GET`   | `/jobs/{id}/minutes`    | structured minutes                                                                       |
| `PATCH` | `/jobs/{id}/speakers`   | `{"speaker_0": "Ramu"}`, an empty string removes a name                                  |
| `POST`  | `/jobs/{id}/minutes`    | regenerate minutes with the current names                                                |


```
curl -F "file=@meeting.mp4" http://localhost:8001/jobs
curl -N http://localhost:8001/jobs/<id>/events
curl http://localhost:8001/jobs/<id>/transcript
curl http://localhost:8001/jobs/<id>/minutes
```

Stages: `queued → (downloading) → extracting → analyzing → stitching → minutes → done`, or `failed` with `error_stage`.
Errors: `404` unknown job or meeting, `409` job not finished or recording not ready, `413` upload too large, `415` not a media file, `422` unknown speaker,
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
participant is matched to the Nemotron speaker they overlap most, one name per speaker. People sharing a room
microphone appear as one Teams participant, so only one of them gets the name. The rest can be renamed with
`PATCH /jobs/{id}/speakers`.

### Mock Graph

`mock/graph.py` imitates the Graph endpoints this service calls, so the whole Teams flow can be tested without a
tenant. It serves one meeting, one recording and one transcript from local files.

```
MOCK_VIDEO=samples/meeting.mp4 MOCK_VTT=samples/friends.vtt uvicorn mock.graph:app --port 8002
```

Then point the service at it in `.env` and restart:

```
TEAMS_TENANT_ID=mock
TEAMS_CLIENT_ID=mock
TEAMS_CLIENT_SECRET=mock
TEAMS_ORGANIZER_ID=mock
TEAMS_LOGIN_URL=http://localhost:8002
TEAMS_GRAPH_URL=http://localhost:8002
```

Any `join_url` finds the mock meeting, and one containing `missing` returns `404`. Without `MOCK_VTT` the meeting
has no transcript, and without `MOCK_VIDEO` it has no recording (`409`). `samples/friends.vtt` names the four main
speakers of a two-minute Friends clip, for testing name matching.

## Job files

Each job lives in `data/<id>/`:


| File              |                                                         |
| ----------------- | ------------------------------------------------------- |
| `job.json`        | stage, error, speaker names, stats                      |
| `segments.json`   | OpenAI output: text, timestamps, OpenAI's speaker label |
| `speakers.json`   | Nemotron output: who spoke when                         |
| `gaps.json`       | speech recovered from gaps in OpenAI's output           |
| `teams.vtt`       | Teams transcript, only for Teams imports that have one  |
| `transcript.json` | final turns                                             |
| `minutes.json`    | minutes                                                 |


When a transcript looks wrong, compare `segments.json` and `speakers.json` for that time range first.

## Configuration


| Env var                                                                           | Default                       |                                                                                                                                                          |
| --------------------------------------------------------------------------------- | ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `OPENAI_API_KEY`                                                                  |                               | required                                                                                                                                                 |
| `TRANSCRIBE_MODEL`                                                                | `gpt-4o-transcribe-diarize`   |                                                                                                                                                          |
| `MINUTES_MODEL`                                                                   | `gpt-5.6-sol`                 |                                                                                                                                                          |
| `TRANSCRIBE_CONCURRENCY`                                                          | `4`                           | parallel OpenAI requests                                                                                                                                 |
| `DIARIZATION_MODE`                                                                | `offline`                     | `offline` is most accurate. `low_latency`, `very_low_latency` or `ultra_low_latency` process the audio in chunks with flat GPU memory, for long meetings |
| `DIARIZATION_THRESHOLD`                                                           | `0.2`                         | speech probability cutoff, lower for quiet voices                                                                                                        |
| `GAP_MIN_SECONDS`                                                                 | `1.0`                         | shortest uncovered speech worth transcribing                                                                                                             |
| `DEVICE`                                                                          | auto (`cuda` → `mps` → `cpu`) | force a device                                                                                                                                           |
| `MAX_UPLOAD_MB`                                                                   | `2048`                        |                                                                                                                                                          |
| `TEAMS_TENANT_ID`, `TEAMS_CLIENT_ID`, `TEAMS_CLIENT_SECRET`, `TEAMS_ORGANIZER_ID` |                               | enable `POST /jobs/teams`                                                                                                                                |
| `TEAMS_LOGIN_URL`, `TEAMS_GRAPH_URL`                                              | Microsoft endpoints           | point at `mock/graph.py` for testing                                                                                                                     |




## Limits

- Up to 8 speakers, labelled `speaker_0`, `speaker_1`, … in order of first appearance.
- When people talk over each other, the text reads choppy and a line said over laughter can land on the wrong person.
That comes from diarization, not from stitching.
- `offline` diarization holds the whole recording on the GPU. Try a one-hour file before relying on long meetings,
and switch to `low_latency` if it runs out of memory.
- Jobs that were running when the server stopped are marked `failed` on the next start.



## Layout

```
app/
  core/          config, errors
  audio/         probe, convert (wav, samples, cut), silence, chunking
  services/      transcription (OpenAI), diarization (Nemotron), minutes (OpenAI), teams (Graph)
  processing/    assign (segment → speaker), gaps (uncovered speech), turns, names (Teams → speakers)
  jobs/          job folders on disk
  schemas/       job, transcript, minutes
  api/           routes
  pipeline.py    stage order
  bootstrap.py   builds the services
  main.py        FastAPI app
mock/graph.py    mock Microsoft Graph for testing Teams import
samples/         test media and transcripts
cli.py           terminal runner
download_model.sh
```

