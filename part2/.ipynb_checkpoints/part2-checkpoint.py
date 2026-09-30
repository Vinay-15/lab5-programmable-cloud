#!/usr/bin/env python3
import argparse
import time
import google.auth
import googleapiclient.discovery
from googleapiclient.errors import HttpError

ZONE = 'us-west1-b'
NETWORK_TAG = 'allow-5000'

STARTUP_SCRIPT = """#!/bin/bash
cd /opt/app/flask-tutorial
export FLASK_APP=flaskr
nohup flask run -h 0.0.0.0 > /opt/app/flask.log 2>&1 &
"""

def wait_for_zone_operation(compute, project, zone, operation):
    while True:
        result = compute.zoneOperations().get(
            project=project, zone=zone, operation=operation['name']).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise RuntimeError(result['error'])
            return result
        time.sleep(1)


def wait_for_global_operation(compute, project, operation):
    while True:
        result = compute.globalOperations().get(
            project=project, operation=operation['name']).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise RuntimeError(result['error'])
            return result
        time.sleep(1)


def exists(request):
    try:
        request.execute()
        return True
    except HttpError as e:
        if e.resp.status == 404:
            return False
        raise


# snapshot the boot disk of the Part 1 instance
def create_snapshot(compute, project, zone, instance_name):
    snapshot_name = f'base-snapshot-{instance_name}'

    if exists(compute.snapshots().get(project=project, snapshot=snapshot_name)):
        print(f"Snapshot '{snapshot_name}' already exists - skipping.")
        return snapshot_name

    instance = compute.instances().get(
        project=project, zone=zone, instance=instance_name).execute()
    boot_disk = next(d for d in instance['disks'] if d.get('boot'))
    disk_name = boot_disk['source'].split('/')[-1]

    print(f"Creating snapshot '{snapshot_name}' from disk '{disk_name}'...")
    operation = compute.disks().createSnapshot(
        project=project, zone=zone, disk=disk_name,
        body={'name': snapshot_name}).execute()
    wait_for_zone_operation(compute, project, zone, operation)
    print("Snapshot created.")
    return snapshot_name


# turn the snapshot into a reusable image
def create_image(compute, project, snapshot_name, instance_name):
    image_name = f'base-image-{instance_name}'

    if exists(compute.images().get(project=project, image=image_name)):
        print(f"Image '{image_name}' already exists - skipping.")
        return image_name

    print(f"Creating image '{image_name}' from snapshot...")
    body = {
        'name': image_name,
        'sourceSnapshot': f'global/snapshots/{snapshot_name}',
    }
    operation = compute.images().insert(project=project, body=body).execute()
    wait_for_global_operation(compute, project, operation)
    print("Image created.")
    return image_name


# create a VM from the image and time it
def create_instance_from_image(compute, project, zone, name, image_name, machine_type):
    config = {
        'name': name,
        'machineType': f'zones/{zone}/machineTypes/{machine_type}',
        'disks': [{
            'boot': True,
            'autoDelete': True,
            'initializeParams': {'sourceImage': f'global/images/{image_name}'},
        }],
        'networkInterfaces': [{
            'network': 'global/networks/default',
            'accessConfigs': [{'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}],
        }],
        'tags': {'items': [NETWORK_TAG]},
        'metadata': {
            'items': [{'key': 'startup-script', 'value': STARTUP_SCRIPT}],
        },
    }

    start = time.time()
    operation = compute.instances().insert(
        project=project, zone=zone, body=config).execute()
    wait_for_zone_operation(compute, project, zone, operation)
    elapsed = time.time() - start

    instance = compute.instances().get(
        project=project, zone=zone, instance=name).execute()
    ip = instance['networkInterfaces'][0]['accessConfigs'][0]['natIP']
    return elapsed, ip


def write_timing_file(results, machine_type, path='TIMING.md'):
    with open(path, 'w') as f:
        f.write('# Part 2 - Instance Creation Timing\n\n')
        f.write(f'Instances created from a custom image (from the Part 1 snapshot), '
                f'machine type `{machine_type}`, zone `{ZONE}`.\n\n')
        f.write('Time is measured from the `instances.insert` call until the '
                'operation reports `DONE`.\n\n')
        f.write('| Instance | Time (seconds) |\n')
        f.write('|---|---|\n')
        for name, elapsed, _ in results:
            f.write(f'| {name} | {elapsed:.2f} |\n')
        avg = sum(r[1] for r in results) / len(results)
        f.write(f'| **Average** | **{avg:.2f}** |\n')
    print(f"Timings written to {path}")


def main():
    parser = argparse.ArgumentParser(description='Lab 5 Part 2')
    parser.add_argument('--instance', default='lab5-part1',
                        help='name of the Part 1 instance to clone')
    parser.add_argument('--machine-type', default='e2-micro')
    parser.add_argument('--project', default=None)
    args = parser.parse_args()

    credentials, default_project = google.auth.default()
    project = args.project or default_project
    if not project:
        raise SystemExit("No project found. Run 'gcloud config set project <ID>' "
                         "or pass --project <ID>.")
    compute = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

    snapshot_name = create_snapshot(compute, project, ZONE, args.instance)
    image_name = create_image(compute, project, snapshot_name, args.instance)

    results = []
    for i in range(1, 4):
        name = f'{args.instance}-clone-{i}'
        print(f"Creating '{name}'...")
        elapsed, ip = create_instance_from_image(
            compute, project, ZONE, name, image_name, args.machine_type)
        print(f"  created in {elapsed:.2f} s  ->  http://{ip}:5000")
        results.append((name, elapsed, ip))

    write_timing_file(results, args.machine_type)


if __name__ == '__main__':
    main()
