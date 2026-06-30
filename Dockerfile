FROM python:3.11-slim

WORKDIR /app

# Dépendances système pour OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY Application/backend/ ./Application/backend/
COPY Application/ml/ ./Application/ml/
COPY Application/data/data.yaml ./Application/data/data.yaml

# Modèle entraîné
COPY Application/ml/runs/baseline/train/weights/best.pt \
     ./Application/ml/runs/baseline/train/weights/best.pt

EXPOSE 5000

ENV FLASK_APP=Application/backend/app.py
ENV PYTHONUNBUFFERED=1

CMD ["python", "Application/backend/app.py"]