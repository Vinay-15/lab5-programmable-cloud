#!/usr/bin/env python3
import argparse
import time

import google.auth
import googleapiclient.discovery

ZONE = 'us-west1-b'
FIREWALL_NAME = 'allow-5000'
NETWORK_TAG = 'allow-5000'
IMAGE_PROJECT = 'ubuntu-os-cloud'
IMAGE_FAMILY = 'ubuntu-2204-lts'

STARTUP_SCRIPT = """#!/bin/bash
mkdir -p /opt/app
cd /opt/app

apt-get update
apt-get install -y python3 python3-pip git

# Only clone/install the first time (the script also runs on every reboot)
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

# -h 0.0.0.0 = listen on all interfaces; nohup = keep running after this script ends
nohup flask run -h 0.0.0.0 > /opt/app/flask.log 2>&1 &
"""



def wait_for_zone_operation(compute, project, zone, operation):
    """Instance operations are 'zonal' - poll until DONE."""
    while True:
        result = compute.zoneOperations().get(
            project=project, zone=zone, operation=operation['name']).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise RuntimeError(result['error'])
            return result
        time.sleep(1)


def wait_for_global_operation(compute, project, operation):
    """Firewall operations are 'global' - poll until DONE."""
    while True:
        result = compute.globalOperations().get(
            project=project, operation=operation['name']).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise RuntimeError(result['error'])
            return result
        time.sleep(1)


# firewall rule
def ensure_firewall_rule(compute, project):
    """Create the allow-5000 rule only if it does not already exist."""
    result = compute.firewalls().list(project=project).execute()
    existing = [rule['name'] for rule in result.get('items', [])]

    if FIREWALL_NAME in existing:
        print(f"Firewall rule '{FIREWALL_NAME}' already exists - skipping.")
        return

    print(f"Creating firewall rule '{FIREWALL_NAME}'...")
    body = {
        'name': FIREWALL_NAME,
        'network': 'global/networks/default',
        'direction': 'INGRESS',
        'allowed': [{'IPProtocol': 'tcp', 'ports': ['5000']}],
        'sourceRanges': ['0.0.0.0/0'],
        'targetTags': [NETWORK_TAG],   # only applies to VMs with this tag
    }
    operation = compute.firewalls().insert(project=project, body=body).execute()
    wait_for_global_operation(compute, project, operation)
    print("Firewall rule created.")


# create the VM
def create_instance(compute, project, zone, name, machine_type):
    # Use the image *family* so Google picks the latest Ubuntu 22.04 image
    image = compute.images().getFromFamily(
        project=IMAGE_PROJECT, family=IMAGE_FAMILY).execute()

    config = {
        'name': name,
        'machineType': f'zones/{zone}/machineTypes/{machine_type}',

        # Boot disk created from the Ubuntu image
        'disks': [{
            'boot': True,
            'autoDelete': True,
            'initializeParams': {'sourceImage': image['selfLink']},
        }],

        # Default network + an external IP (ONE_TO_ONE_NAT)
        'networkInterfaces': [{
            'network': 'global/networks/default',
            'accessConfigs': [{'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}],
        }],

        # The startup script is passed as instance metadata
        'metadata': {
            'items': [{'key': 'startup-script', 'value': STARTUP_SCRIPT}],
        },
    }

    print(f"Creating instance '{name}' ({machine_type}) in {zone}...")
    operation = compute.instances().insert(
        project=project, zone=zone, body=config).execute()
    wait_for_zone_operation(compute, project, zone, operation)
    print("Instance created.")


# tag the VM so the firewall rule applies to it
def add_network_tag(compute, project, zone, name):
    instance = compute.instances().get(
        project=project, zone=zone, instance=name).execute()

    # setTags needs the current fingerprint (prevents conflicting edits)
    tags = instance.get('tags', {})
    items = set(tags.get('items', []))
    items.add(NETWORK_TAG)
    body = {'items': sorted(items), 'fingerprint': tags['fingerprint']}

    print(f"Applying network tag '{NETWORK_TAG}'...")
    operation = compute.instances().setTags(
        project=project, zone=zone, instance=name, body=body).execute()
    wait_for_zone_operation(compute, project, zone, operation)
    print("Tag applied.")


# external IP
def get_external_ip(compute, project, zone, name):
    instance = compute.instances().get(
        project=project, zone=zone, instance=name).execute()
    return instance['networkInterfaces'][0]['accessConfigs'][0]['natIP']


def main():
    parser = argparse.ArgumentParser(description='Lab 5 Part 1')
    parser.add_argument('--name', default='lab5-part1', help='VM instance name')
    parser.add_argument('--machine-type', default='f1-micro',
                        help='e.g. f1-micro (final) or e2-medium (faster for testing)')
    parser.add_argument('--project', default=None,
                        help='GCP project id (defaults to your gcloud project)')
    args = parser.parse_args()

    credentials, default_project = google.auth.default()
    project = args.project or default_project
    if not project:
        raise SystemExit("No project found. Run 'gcloud config set project <ID>' "
                         "or pass --project <ID>.")

    compute = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

    ensure_firewall_rule(compute, project)
    create_instance(compute, project, ZONE, args.name, args.machine_type)
    add_network_tag(compute, project, ZONE, args.name)
    ip = get_external_ip(compute, project, ZONE, args.name)

    print()
    print("The Flask application will be available at:")
    print()
    print(f"    http://{ip}:5000")
    print()
    print("Give the startup script a few minutes to install everything "
          "before opening it.")


if __name__ == '__main__':
    main()
