# ── MuseTalk Service Dockerfile ──────────────────────────────────
# Python 3.10 image — eliminates all setuptools/pkg_resources issues
FROM rocm/pytorch:rocm6.1_ubuntu22.04_py3.10_pytorch_2.4

ENV DEBIAN_FRONTEND=noninteractive
ENV HSA_OVERRIDE_GFX_VERSION=11.0.0

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git wget curl \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev \
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

# mmcv ecosystem — py3.10 wheels exist for these exact versions
RUN pip install --no-cache-dir setuptools wheel && \
    pip install --no-cache-dir mmengine && \
    pip install --no-cache-dir "mmcv-lite==2.1.0" && \
    pip install --no-cache-dir "mmdet==3.3.0" "mmpose==1.3.2"

# Re-pin ROCm PyTorch after mmdet/mmpose may have overwritten it
RUN pip install --no-cache-dir "torch==2.4.0" "torchvision==0.19.0" --index-url https://download.pytorch.org/whl/rocm6.1

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
