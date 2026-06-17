#!/bin/bash
# AI Scribe — Start Server
# Run from anywhere on dgx-node1:
#   bash ~/ai_scribe/start.sh

source ~/.bashrc
conda activate STTENV
cd ~/ai_scribe

# Dynamically find the GPU with the most free memory
BEST_GPU=$(nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits | sort -t ',' -k2 -nr | head -n 1 | awk -F',' '{print $1}')

export CUDA_VISIBLE_DEVICES=$BEST_GPU

echo "============================================"
echo "  AI Scribe — starting"
echo "  Auto-selected GPU $BEST_GPU (most free memory)"
echo "  GPU $BEST_GPU status:"
nvidia-smi --query-gpu=index,memory.free,memory.used,utilization.gpu \
           --format=csv,noheader -i $BEST_GPU
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
