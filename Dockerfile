
FROM python:3.10-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential        \
        git                    \
        curl                   \
        libgl1-mesa-dev        \
        libgeos-dev            \
        libxrender1            \
        libxext6               \
        libsm6                 \
        libglib2.0-0           \
        python3-tk             \
        scrot                  \
    && rm -rf /var/lib/apt/lists/*


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY . .


CMD ["python", "main.py"]
