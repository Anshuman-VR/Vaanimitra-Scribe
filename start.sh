#!/bin/bash
# AI Scribe — Start Server
# Run from anywhere on dgx-node1:
#   bash ~/ai_scribe/start.sh

source ~/.bashrc
conda activate STTENV
cd ~/ai_scribe

# GPU 3 had 55 GB free and 0% utilisation at last check.
# Change this if GPU 3 is now occupied — check with: nvidia-smi
export CUDA_VISIBLE_DEVICES=3

echo "============================================"
echo "  AI Scribe — starting"
echo "  GPU 3 status:"
nvidia-smi --query-gpu=index,memory.free,memory.used,utilization.gpu \
           --format=csv,noheader -i 3
echo ""
echo "  URL: https://172.16.13.91:8765"
echo "  (Accept the self-signed cert warning once)"
echo "============================================"

uvicorn server.main:app \
  --host 0.0.0.0 \
  --port 8765 \
  --ssl-keyfile key.pem \
  --ssl-certfile cert.pem \
  --workers 1
