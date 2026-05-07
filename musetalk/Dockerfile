# ── MuseTalk Service Dockerfile ──────────────────────────────────
# Uses AMD ROCm PyTorch base image for MI300X GPU
FROM rocm/pytorch:latest

ENV DEBIAN_FRONTEND=noninteractive
ENV HSA_OVERRIDE_GFX_VERSION=11.0.0

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git wget curl \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /musetalk

# Clone MuseTalk
RUN git clone https://github.com/TMElyralab/MuseTalk.git . && \
    git checkout main

# FastAPI server deps
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] python-multipart aiofiles

# Core ML deps — using versions known to work with ROCm PyTorch 2.3
RUN pip install --no-cache-dir \
    diffusers==0.27.2 \
    transformers==4.40.2 \
    accelerate \
    einops \
    omegaconf \
    huggingface_hub

# OpenCV (headless, no X11 needed)
RUN pip install --no-cache-dir opencv-python-headless

# onnxruntime for DWPose face detection (CPU backend, no CUDA/HIP needed)
RUN pip install --no-cache-dir onnxruntime

# mmcv ecosystem — try CPU-only build first (avoids HIP extension compile)
RUN pip install --no-cache-dir openmim && \
    mim install mmengine && \
    pip install --no-cache-dir mmcv==2.0.1 \
        -f https://download.openmmlab.com/mmcv/dist/cpu/torch2.0/index.html && \
    mim install "mmdet==3.1.0" && \
    mim install "mmpose==1.1.0"

# Remaining MuseTalk requirements (skip failures gracefully)
RUN pip install --no-cache-dir -r requirements.txt || true

# Copy our FastAPI server
COPY server.py /musetalk/server.py
COPY data/aria_avatar.jpg /musetalk/data/aria_avatar.jpg

# Directories for output and models
RUN mkdir -p /musetalk/videos /musetalk/models

EXPOSE 8090

# Start the API server (models pre-loaded at startup)
CMD ["python", "server.py"]
