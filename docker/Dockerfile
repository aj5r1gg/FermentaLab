FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/app:/workspace/upstream/software/src

WORKDIR /workspace

CMD ["python", "-c", "import platform; print('FermentaLab development environment'); print('Python:', platform.python_version()); print('Architecture:', platform.machine())"]
