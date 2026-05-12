#!/usr/bin/env bash
# Download a Piper voice into ./models/piper/
# Usage:  ./scripts/download_piper_voice.sh [voice_name]
# Default: fr_FR-siwis-medium
set -euo pipefail

VOICE="${1:-fr_FR-siwis-medium}"
DEST="$(dirname "$0")/../models/piper"
mkdir -p "$DEST"

# Piper voices are hosted on Hugging Face under rhasspy/piper-voices.
# Path layout: <lang_code>/<locale>/<voice_name>/<quality>/<voice_name>.onnx
# Example for fr_FR-siwis-medium: fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx
case "$VOICE" in
    fr_FR-siwis-medium)
        REMOTE="fr/fr_FR/siwis/medium/fr_FR-siwis-medium"
        ;;
    fr_FR-upmc-medium)
        REMOTE="fr/fr_FR/upmc/medium/fr_FR-upmc-medium"
        ;;
    fr_FR-tom-medium)
        REMOTE="fr/fr_FR/tom/medium/fr_FR-tom-medium"
        ;;
    en_US-amy-medium)
        REMOTE="en/en_US/amy/medium/en_US-amy-medium"
        ;;
    *)
        echo "Unknown voice '$VOICE'. Edit this script to add the HF path." >&2
        exit 1
        ;;
esac

BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/${REMOTE}"
echo "Downloading $VOICE into $DEST ..."
curl -fL --progress-bar -o "${DEST}/${VOICE}.onnx"      "${BASE}.onnx"
curl -fL --progress-bar -o "${DEST}/${VOICE}.onnx.json" "${BASE}.onnx.json"
echo "Done. Files in $DEST:"
ls -lh "${DEST}/${VOICE}".*
