FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY .streamlit ./.streamlit
COPY app.py ./
RUN useradd --uid 10001 --create-home appuser
USER 10001

EXPOSE 8501
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health').status==200 else 1)"
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0", "--server.fileWatcherType", "none"]
