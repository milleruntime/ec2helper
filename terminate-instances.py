#! /usr/bin/env python
import boto.ec2

# needs credentials in ~/.aws/credentials
# http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html#cli-config-files
ec2 = boto.ec2.connect_to_region('us-east-1')

# kill instances BE VERY CAREFUL
ids = [e.id for e in ec2.get_only_instances(filters={'tag:boto-wrapper':'python-experimentation'})]

print "Terminating: " + str(ids)
# TODO add prompt

ec2.terminate_instances(ids)
