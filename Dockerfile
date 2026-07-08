FROM python:3.11-slim

WORKDIR /app

# Dépendances système pour OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

# PyTorch CPU d'abord : le VPS n'a pas de GPU, la pile CUDA (~4 Go)
# est inutile — image ~6 Go -> ~2 Go, builds et deploiements 3x plus rapides
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Modeles EasyOCR cuits dans l'image (~100 Mo) : sinon ils sont
# retelecharges au premier scan apres chaque deploiement
RUN python -c "import easyocr; easyocr.Reader(['en'], verbose=False)"

# Code source
COPY Application/backend/ ./Application/backend/
COPY Application/ml/ ./Application/ml/
COPY Application/dataset/data.yaml ./Application/dataset/data.yaml

# Modèles versionnés (metadata.json + best_vN.pt trackés dans git)
COPY Application/models/ ./Application/models/

EXPOSE 5000

ENV FLASK_APP=Application/backend/app.py
ENV PYTHONUNBUFFERED=1

CMD ["python", "Application/backend/app.py"]