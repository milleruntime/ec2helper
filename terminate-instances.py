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

# kill instances BE VERY CAREFUL
ids = [e.id for e in ec2.get_only_instances(filters=tags)]

print "Terminating: " + str(ids)
line = raw_input("Are you sure (type 'yes')? ")
if "yes" == line.lower():
  ec2.terminate_instances(ids)
