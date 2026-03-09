FROM python:3-slim

# BMC Redfish Simulator
# Based on DMTF Redfish-Mockup-Server

LABEL maintainer="BMC Simulator Development Team"
LABEL description="BMC Redfish Simulator - Enhanced Redfish mockup server for BMC development"
LABEL version="2.0.0"

# For healthcheck
RUN apt-get update && apt-get install curl -y

# Install python requirements
COPY requirements.txt /tmp/
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Copy server files
COPY rfSsdpServer.py redfishMockupServer_modular.py /usr/src/app/
COPY src /usr/src/app/src
ADD public-rackmount1 /usr/src/app/public-rackmount1

# Env settings
EXPOSE 8000
HEALTHCHECK CMD curl --fail http://127.0.0.1:8000/redfish/v1 || exit 1
WORKDIR /usr/src/app
ENTRYPOINT ["python", "/usr/src/app/redfishMockupServer_modular.py", "-H", "0.0.0.0"]
