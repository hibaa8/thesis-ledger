FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY ledger ./ledger
RUN pip install --no-cache-dir . && useradd -m ledger && mkdir /data && chown ledger:ledger /data
USER ledger
ENV LEDGER_DATA_DIR=/data
EXPOSE 8000
CMD ["thesis-ledger", "--host", "0.0.0.0", "--port", "8000"]
