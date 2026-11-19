FROM node:24-bookworm-slim AS node

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg libopus0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 soundcard \
    && useradd --uid 10001 --gid 10001 --no-create-home --no-log-init soundcard \
    && install -d -o soundcard -g soundcard -m 0700 /app/data

COPY --from=node /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY server.py ./
COPY deploy/start_cloud.py ./
COPY core/ core/
COPY static/ static/
COPY background/ background/

USER 10001:10001
EXPOSE 8000
CMD ["python", "start_cloud.py"]
