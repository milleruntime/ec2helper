#! /usr/bin/env python
import boto.ec2

# needs credentials in ~/.aws/credentials
# http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html#cli-config-files
ec2 = boto.ec2.connect_to_region('us-east-1')

tags = {}

with open("tags") as file:
  for line in file:
    line = line.strip()
    if not line.startswith('#') and line.find('=') > -1:
      i = line.find('=')
      key = line[:i].strip()
      value = line[i+1:].strip()
      tags['tag:'+key] = value

for e in ec2.get_only_instances(filters=tags):
  print '=' * 65
  print "%12s: %s" % ("Instance ID", e.id)
  print "%12s: %s" % ("Public IP", e.ip_address)
  print "%12s: %s" % ("Private IP", e.private_ip_address)
  print "%12s: %s" % ("State", e.state)
  print "%12s: %s" % ("Type", e.instance_type)
  print "%12s: %s" % ("Launch Time", e.launch_time)
  print "%12s: %s" % ("Key", e.key_name)
  print "%12s: %s" % ("VPC", e.vpc_id)
  print "%12s: %s" % ("Subnet", e.subnet_id)
  print "%12s: %s (%s)" % ("Root Device", e.root_device_name, e.root_device_type)
  for name, device in e.block_device_mapping.items():
    print "%12s:" % (name)
    for vol in ec2.get_all_volumes([device.volume_id]):
      for k, v in vars(vol).items():
        print "%13s %s = %s" % ("", k, v)
