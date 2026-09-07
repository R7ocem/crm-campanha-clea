FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8765
ENV DATA_DIR=/data

WORKDIR /app

COPY app.py /app/app.py
COPY static /app/static

RUN mkdir -p /data

VOLUME ["/data"]
EXPOSE 8765

CMD ["python", "app.py"]
