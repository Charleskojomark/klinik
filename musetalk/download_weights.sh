#!/bin/bash
# ── Download MuseTalk model weights ─────────────────────────────
# Run this ONCE on the droplet before starting the musetalk service:
#   bash musetalk/download_weights.sh
#
# Total download: ~4-6 GB
# Requires: huggingface_hub, git-lfs

set -e
MODELS_DIR="/opt/klinik/musetalk/models"
mkdir -p "$MODELS_DIR"

echo "📦 Downloading MuseTalk model weights to $MODELS_DIR..."

# Install huggingface_hub CLI if needed
pip install -q huggingface_hub

python3 - <<'PYEOF'
import os
from huggingface_hub import snapshot_download, hf_hub_download

MODELS = "/opt/klinik/musetalk/models"

# 1. MuseTalk V1.5 weights
print("⬇️  Downloading MuseTalk V1.5...")
snapshot_download(
    repo_id="TMElyralab/MuseTalk",
    local_dir=f"{MODELS}/musetalkV15",
    ignore_patterns=["*.md", "*.txt"]
)

# 2. Stable Diffusion VAE (ft-mse)
print("⬇️  Downloading SD VAE...")
snapshot_download(
    repo_id="stabilityai/sd-vae-ft-mse",
    local_dir=f"{MODELS}/sd-vae",
    ignore_patterns=["*.md", "*.txt", "*.ckpt"]
)

# 3. Whisper tiny (audio encoder)
print("⬇️  Downloading Whisper tiny...")
snapshot_download(
    repo_id="openai/whisper-tiny",
    local_dir=f"{MODELS}/whisper",
    ignore_patterns=["*.md", "flax_*", "tf_*", "rust_*"]
)

# 4. DWPose (face landmark detection)
print("⬇️  Downloading DWPose...")
os.makedirs(f"{MODELS}/dwpose", exist_ok=True)
hf_hub_download(
    repo_id="yzd-v/DWPose",
    filename="dw-ll_ucoco_384.pth",
    local_dir=f"{MODELS}/dwpose"
)

# 5. SyncNet (optional, for sync loss)
print("⬇️  Downloading SyncNet...")
os.makedirs(f"{MODELS}/syncnet", exist_ok=True)
hf_hub_download(
    repo_id="ByteDance/LatentSync",
    filename="latentsync_syncnet.pt",
    local_dir=f"{MODELS}/syncnet"
)

# 6. ResNet18 (face parsing)
print("⬇️  Downloading ResNet18...")
os.makedirs(f"{MODELS}/face-parse-bisent", exist_ok=True)
import urllib.request
urllib.request.urlretrieve(
    "https://download.pytorch.org/models/resnet18-5c106cde.pth",
    f"{MODELS}/face-parse-bisent/resnet18-5c106cde.pth"
)

print("✅ All weights downloaded!")
PYEOF

# Verify structure
echo ""
echo "📁 Model directory structure:"
find "$MODELS_DIR" -name "*.pth" -o -name "*.bin" -o -name "*.pt" 2>/dev/null | head -20

echo ""
echo "✅ Download complete. You can now start the musetalk service:"
echo "   docker compose --profile gpu up -d musetalk"
