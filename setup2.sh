#!/bin/bash
# AI Scribe — Stage 2: Copy static assets, generate cert, verify imports
# Run on dgx-node1 with STTENV active:
#   source ~/.bashrc && conda activate STTENV && bash ~/ai_scribe/setup2.sh 2>&1

set -e

DLDIR="$TMPDIR/vad_dl"

echo "=== 1. Verifying download dir ==="
if [ ! -d "$DLDIR/package" ]; then
  echo "ERROR: $DLDIR/package not found. Did you run step 3 of setup1.sh?"
  exit 1
fi
if [ ! -d "$DLDIR/ort_pkg" ]; then
  echo "ERROR: $DLDIR/ort_pkg not found. Did you run step 4 of setup1.sh?"
  exit 1
fi
echo "Download dirs OK"

echo ""
echo "=== 2. Copying vad-web assets → ~/ai_scribe/static/ ==="
cp -v "$DLDIR/package/dist/bundle.min.js"              ~/ai_scribe/static/
cp -v "$DLDIR/package/dist/vad.worklet.bundle.min.js"  ~/ai_scribe/static/
cp -v "$DLDIR/package/dist/silero_vad_v5.onnx"         ~/ai_scribe/static/
cp -v "$DLDIR/package/dist/silero_vad_legacy.onnx"     ~/ai_scribe/static/

echo ""
echo "=== 3. Copying onnxruntime-web WASM + MJS → ~/ai_scribe/static/ ==="
cp -v "$DLDIR/ort_pkg/package/dist/ort-wasm-simd-threaded.wasm"      ~/ai_scribe/static/
cp -v "$DLDIR/ort_pkg/package/dist/ort-wasm-simd-threaded.mjs"       ~/ai_scribe/static/
cp -v "$DLDIR/ort_pkg/package/dist/ort-wasm-simd-threaded.jsep.wasm" ~/ai_scribe/static/
cp -v "$DLDIR/ort_pkg/package/dist/ort-wasm-simd-threaded.jsep.mjs"  ~/ai_scribe/static/
cp -v "$DLDIR/ort_pkg/package/dist/ort.wasm.bundle.min.mjs"          ~/ai_scribe/static/

echo ""
echo "=== 4. Generating self-signed SSL certificate ==="
cd ~/ai_scribe
if [ -f cert.pem ] && [ -f key.pem ]; then
  echo "cert.pem and key.pem already exist — skipping"
else
  openssl req -x509 -newkey rsa:2048 \
    -keyout key.pem -out cert.pem \
    -days 365 -nodes \
    -subj "/CN=172.16.13.91"
  echo "Certificate generated."
fi

echo ""
echo "=== 5. Removing old flat files ==="
rm -f ~/ai_scribe/server.py ~/ai_scribe/index.html
rm -rf ~/ai_scribe/__pycache__
echo "Old files removed."

echo ""
echo "=== 6. Directory listing ==="
echo "--- ~/ai_scribe/ ---"
ls -lah ~/ai_scribe/

echo ""
echo "--- ~/ai_scribe/server/ ---"
ls -lah ~/ai_scribe/server/

echo ""
echo "--- ~/ai_scribe/client/ ---"
ls -lah ~/ai_scribe/client/

echo ""
echo "--- ~/ai_scribe/static/ ---"
ls -lah ~/ai_scribe/static/

echo ""
echo "=== 7. Python import verification (no GPU load) ==="
cd ~/ai_scribe
python -c "
from server.config import WHISPER_MODEL, PORT, CUDA_DEVICE_INDEX, COMMAND_PREFIXES
print('config OK  —', WHISPER_MODEL, 'port', PORT, 'GPU', CUDA_DEVICE_INDEX)

from server.pipeline import Pipeline
p = Pipeline()
r = p.process({'text': 'Hello world.', 'words': []})
assert r == {'type': 'transcript', 'text': 'Hello world.', 'words': []}, repr(r)
print('pipeline OK —', r)

r2 = p.process({'text': 'Next question.', 'words': []})
assert r2['type'] == 'command', repr(r2)
assert r2['action'] == 'nav_next', repr(r2)
print('command routing OK —', r2)

print('All imports and logic checks passed.')
"

echo ""
echo "=== SETUP COMPLETE ==="
echo "Start the server with:  bash ~/ai_scribe/start.sh"
echo "Access at:              https://172.16.13.91:8765"
echo "(Accept the self-signed cert warning in the browser)"
