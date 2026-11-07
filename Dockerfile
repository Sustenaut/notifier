# The notifier: `notifier run`, every two minutes, by the CronJob in k8s/notifier.yaml.
# Build from the repository's root:
#   podman build -t notifier .
# It holds no credentials: its BigQuery key, Slack token and storage token are mounted
# on the server. Its dependencies are installed from wheels alone, by hash, so no
# package's setup script runs; its own code is pure Python and is copied in.
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/opt/notifier
COPY requirements.lock /tmp/requirements.lock
RUN pip install --only-binary :all: --require-hashes -r /tmp/requirements.lock && rm /tmp/requirements.lock
COPY src/notifier/ /opt/notifier/notifier/
RUN printf '#!/bin/sh\nexec python -m notifier "$@"\n' > /usr/local/bin/notifier && chmod 755 /usr/local/bin/notifier
RUN useradd --create-home --uid 1000 app
USER app
CMD ["notifier", "run"]
