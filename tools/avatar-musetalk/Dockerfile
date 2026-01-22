FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Build context should be repo root so third_party is available.
COPY third_party/musetalk /app/third_party/musetalk
COPY tools/avatar-musetalk/requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

COPY tools/avatar-musetalk/app /app/app

ENV PYTHONUNBUFFERED=1
ENV MUSE_TALK_DIR=/app/third_party/musetalk

CMD ["python3", "-m", "uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "7800"]
