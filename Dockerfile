FROM python:3-slim

# BMC Redfish Simulator
# Based on DMTF Redfish-Mockup-Server
# Copyright (c) Microsoft Corporation. Licensed under the MIT License.

LABEL maintainer="Microsoft Corporation"
LABEL description="Redfish Dev Server - Redfish API simulator for BMC development"
LABEL version="2.2.0"

# For healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install python requirements
COPY requirements.txt /tmp/
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Copy project files
COPY servers/ /usr/src/app/servers/
COPY scripts/rfSsdpServer.py /usr/src/app/scripts/
COPY src/ /usr/src/app/src/

# Optional: copy mockup data if present (users can also volume-mount their own)
# Mount your mockup at runtime: -v /path/to/mockup:/usr/src/app/mockup
# Or pass -D flag: docker run ... -D /usr/src/app/mockup

# Env settings
EXPOSE 8000
HEALTHCHECK CMD curl --fail http://127.0.0.1:8000/redfish/v1 || exit 1
WORKDIR /usr/src/app
ENTRYPOINT ["python", "/usr/src/app/servers/redfishMockupServer_modular.py", "-H", "0.0.0.0"]
