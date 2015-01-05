#! /usr/bin/env python
import boto.ec2
import time
from boto.ec2.blockdevicemapping import BlockDeviceType
from boto.ec2.blockdevicemapping import BlockDeviceMapping

# needs credentials in ~/.aws/credentials
# http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html#cli-config-files
ec2 = boto.ec2.connect_to_region('us-east-1')

# verify with 'curl http://169.254.169.254/latest/user-data'
script = '''#! /usr/bin/env bash

yum install accumulo -y
'''

disks = BlockDeviceMapping()
# resize EBS root volume; not needed for F21 image, it's plenty big enough (12G);
# should use sda1 for some images
# disks['/dev/sda'] = BlockDeviceType(size=16, delete_on_termination=True, volume_type='standard')

# this gets put in /mnt by cloud-init, formatted ext3; probably want to unmount and reformat to ext4 or xfs in the user data
# the actual device may be named differently in the OS (like /dev/vdb, or /dev/xvdb)
disks['/dev/sdb'] = BlockDeviceType(ephemeral_name='ephemeral0')

# create an instance
reservation = ec2.run_instances(image_id='ami-164cd77e',  # Fedora 21 x86_64, EBS-backed
                                instance_type='m3.large',  # has 32 GB SSD for ephemeral
                                min_count=5, max_count=5,  # can only do one at a time if private IP specified
                                key_name="Christopher",
                                user_data=script,
                                block_device_map=disks,

                                # Networking stuff here
                                # security_group_ids=['sg-xxxxxxxx'],
                                # subnet_id='subnet-xxxxxxxx',
                                # can set the IP (must match subnet) or let it auto-assign
                                # private_ip_address='10.1.4.102',
                                )

# tag the instance created and all attached volumes and network interfaces
ids = []
for instance in reservation.instances:
    nic_ids = [e.id for e in instance.interfaces]
    volume_ids = []
    while not volume_ids:  # wait for the volume to be created and attached
        time.sleep(1)
        volume_ids = [e.id for e in ec2.get_all_volumes(filters={'attachment.instance-id':instance.id}) ]
    ids = ids + [instance.id] + nic_ids + volume_ids
    print instance.private_ip_address

# print "Tagging: " + str(ids)
ec2.create_tags(ids, {'boto-wrapper':'python-experimentation'})
