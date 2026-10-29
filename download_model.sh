#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
hf download nvidia/Nemotron-3-Diarization \
  config.json processor_config.json model.safetensors \
  --local-dir ./models/nemotron-3-diarization
ls -lh ./models/nemotron-3-diarization
