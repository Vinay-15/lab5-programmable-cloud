#!/bin/bash
# Startup script for VM-1 (the "launcher").
mkdir -p /srv
cd /srv

MD=http://metadata/computeMetadata/v1/instance/attributes
curl -s "$MD/vm2-startup-script"   -H "Metadata-Flavor: Google" > vm2-startup-script.sh
curl -s "$MD/service-credentials"  -H "Metadata-Flavor: Google" > service-credentials.json
curl -s "$MD/vm1-launch-vm2-code"  -H "Metadata-Flavor: Google" > vm1-launch-vm2-code.py
chmod 600 service-credentials.json

export GOOGLE_CLOUD_PROJECT=$(curl -s "$MD/project" -H "Metadata-Flavor: Google")

apt-get update
apt-get install -y python3 python3-pip
pip3 install --upgrade google-api-python-client google-auth

python3 vm1-launch-vm2-code.py > /srv/launch.log 2>&1
