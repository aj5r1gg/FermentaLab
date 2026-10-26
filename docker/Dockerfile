FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/app:/workspace/upstream/software/src

WORKDIR /workspace

RUN python -m pip install --no-cache-dir \
    "hypothesis==6.170.11"

CMD ["python", "-c", "import platform; print('FermentaLab development environment'); print('Python:', platform.python_version()); print('Architecture:', platform.machine())"]
