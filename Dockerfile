ARG BASE_IMAGE=docker.io/luufqa/debian-cryptopro:latest
ARG BASE_PLATFORM=linux/amd64

FROM --platform=${BASE_PLATFORM} ${BASE_IMAGE}

WORKDIR /app

# Copy requirements separately for Docker layer caching.
COPY requirements.txt .
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org \
    --no-cache-dir -r requirements.txt
ENV PATH="/opt/venv/bin:$PATH"

# Copy the project source.
COPY . /app
RUN chmod +x /app/scripts/run-tests-and-keep-novnc.sh

CMD ["bash", "/app/scripts/run-tests-and-keep-novnc.sh"]
