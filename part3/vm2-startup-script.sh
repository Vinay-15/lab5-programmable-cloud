#!/bin/bash
# Startup script for VM-2
mkdir -p /opt/app
cd /opt/app

apt-get update
apt-get install -y python3 python3-pip git

if [ ! -d flask-tutorial ]; then
    git clone https://github.com/cu-csci-4253-datacenter/flask-tutorial
    cd flask-tutorial
    pip3 install -e .
    export FLASK_APP=flaskr
    flask init-db
else
    cd flask-tutorial
    export FLASK_APP=flaskr
fi

nohup flask run -h 0.0.0.0 > /opt/app/flask.log 2>&1 &
