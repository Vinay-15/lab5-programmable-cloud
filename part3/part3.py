#!/usr/bin/env python3
import os
import time

import googleapiclient.discovery
import google.oauth2.service_account as service_account
from googleapiclient.errors import HttpError

ZONE = 'us-west1-b'
VM1_NAME = 'lab5-part3-launcher'
VM1_MACHINE_TYPE = 'e2-micro'
VM2_NAME = 'lab5-part3-flask'   # must match the name in vm1-launch-vm2-code.py

# Use Google Service Account - See https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.service_account.html#module-google.oauth2.service_account
credentials = service_account.Credentials.from_service_account_file(
    filename='service-credentials.json')
project = os.getenv('GOOGLE_CLOUD_PROJECT') or credentials.project_id
service = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)


def read_file(path):
    with open(path) as f:
        return f.read()


def wait_for_zone_operation(compute, project, zone, operation):
    while True:
        result = compute.zoneOperations().get(
            project=project, zone=zone, operation=operation['name']).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise RuntimeError(result['error'])
            return result
        time.sleep(1)


def create_vm1(compute, project, zone):
    image = compute.images().getFromFamily(
        project='ubuntu-os-cloud', family='ubuntu-2204-lts').execute()

    config = {
        'name': VM1_NAME,
        'machineType': f'zones/{zone}/machineTypes/{VM1_MACHINE_TYPE}',
        'disks': [{
            'boot': True,
            'autoDelete': True,
            'initializeParams': {'sourceImage': image['selfLink']},
        }],
        # External IP so VM-1 can reach the internet (apt, pip, Google APIs)
        'networkInterfaces': [{
            'network': 'global/networks/default',
            'accessConfigs': [{'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}],
        }],
        'metadata': {
            'items': [
                {'key': 'startup-script', 'value': read_file('vm1-startup-script.sh')},
                {'key': 'vm1-launch-vm2-code', 'value': read_file('vm1-launch-vm2-code.py')},
                {'key': 'vm2-startup-script', 'value': read_file('vm2-startup-script.sh')},
                {'key': 'service-credentials', 'value': read_file('service-credentials.json')},
                {'key': 'project', 'value': project},]},}

    print(f"Creating VM-1 '{VM1_NAME}' in {zone}...")
    operation = compute.instances().insert(
        project=project, zone=zone, body=config).execute()
    wait_for_zone_operation(compute, project, zone, operation)
    print("VM-1 created. It is now installing libraries and will create VM-2.")


def wait_for_vm2(compute, project, zone, timeout=900):
    """Poll until VM-1 has created VM-2, then return VM-2's external IP."""
    print(f"Waiting for VM-1 to create '{VM2_NAME}' (usually 2-5 minutes)...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            inst = compute.instances().get(
                project=project, zone=zone, instance=VM2_NAME).execute()
            access = inst['networkInterfaces'][0].get('accessConfigs', [{}])[0]
            if inst['status'] == 'RUNNING' and 'natIP' in access:
                return access['natIP']
        except HttpError as e:
            if e.resp.status != 404:
                raise
        time.sleep(15)
    return None


def main():
    print(f"Project: {project}")
    create_vm1(service, project, ZONE)
    ip = wait_for_vm2(service, project, ZONE)
    if ip:
        print()
        print("VM-1 created VM-2. The Flask application will be available at:")
        print()
        print(f"    http://{ip}:5000")
        print()
        print("Give VM-2 a few minutes to install flask before opening it.")
    else:
        print("VM-2 did not appear in time. SSH into VM-1 and check /srv/launch.log")


if __name__ == '__main__':
    main()
