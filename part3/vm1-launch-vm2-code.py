#!/usr/bin/env python3
import os
import time

import googleapiclient.discovery
import google.oauth2.service_account as service_account

ZONE = 'us-west1-b'
VM2_NAME = 'lab5-part3-flask'
VM2_MACHINE_TYPE = 'e2-micro'
FIREWALL_NAME = 'allow-5000'
NETWORK_TAG = 'allow-5000'

credentials = service_account.Credentials.from_service_account_file(
    filename='service-credentials.json')
project = os.getenv('GOOGLE_CLOUD_PROJECT') or credentials.project_id
compute = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)


def wait_for_zone_operation(operation):
    while True:
        result = compute.zoneOperations().get(
            project=project, zone=ZONE, operation=operation['name']).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise RuntimeError(result['error'])
            return result
        time.sleep(1)


def wait_for_global_operation(operation):
    while True:
        result = compute.globalOperations().get(
            project=project, operation=operation['name']).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise RuntimeError(result['error'])
            return result
        time.sleep(1)


def ensure_firewall_rule():
    result = compute.firewalls().list(project=project).execute()
    if FIREWALL_NAME in [r['name'] for r in result.get('items', [])]:
        print(f"Firewall rule '{FIREWALL_NAME}' already exists.")
        return
    body = {
        'name': FIREWALL_NAME,
        'network': 'global/networks/default',
        'direction': 'INGRESS',
        'allowed': [{'IPProtocol': 'tcp', 'ports': ['5000']}],
        'sourceRanges': ['0.0.0.0/0'],
        'targetTags': [NETWORK_TAG],
    }
    wait_for_global_operation(
        compute.firewalls().insert(project=project, body=body).execute())
    print("Firewall rule created.")


def create_vm2():
    with open('vm2-startup-script.sh') as f:
        startup_script = f.read()

    image = compute.images().getFromFamily(
        project='ubuntu-os-cloud', family='ubuntu-2204-lts').execute()

    config = {
        'name': VM2_NAME,
        'machineType': f'zones/{ZONE}/machineTypes/{VM2_MACHINE_TYPE}',
        'disks': [{
            'boot': True,
            'autoDelete': True,
            'initializeParams': {'sourceImage': image['selfLink']},
        }],
        'networkInterfaces': [{
            'network': 'global/networks/default',
            'accessConfigs': [{'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}],
        }],
        # VM-2 only gets the flask startup script - NOT the credentials
        'metadata': {
            'items': [{'key': 'startup-script', 'value': startup_script}],
        },
    }
    print(f"Creating VM-2 '{VM2_NAME}'...")
    wait_for_zone_operation(compute.instances().insert(
        project=project, zone=ZONE, body=config).execute())


def tag_vm2():
    instance = compute.instances().get(
        project=project, zone=ZONE, instance=VM2_NAME).execute()
    tags = instance.get('tags', {})
    items = set(tags.get('items', []))
    items.add(NETWORK_TAG)
    body = {'items': sorted(items), 'fingerprint': tags['fingerprint']}
    wait_for_zone_operation(compute.instances().setTags(
        project=project, zone=ZONE, instance=VM2_NAME, body=body).execute())


def main():
    print(f"Project: {project}")
    ensure_firewall_rule()
    create_vm2()
    tag_vm2()
    instance = compute.instances().get(
        project=project, zone=ZONE, instance=VM2_NAME).execute()
    ip = instance['networkInterfaces'][0]['accessConfigs'][0]['natIP']
    print(f"VM-2 created. Flask app will be at http://{ip}:5000")


if __name__ == '__main__':
    main()
