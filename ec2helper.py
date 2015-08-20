#! /usr/bin/env python
from __future__ import print_function
import os
import sys
import inspect
import argparse
import boto.ec2
import time
import StringIO
import gzip
from ConfigParser import SafeConfigParser
from ConfigParser import MissingSectionHeaderError
from ConfigParser import NoSectionError
from ConfigParser import NoOptionError
from boto.ec2.blockdevicemapping import BlockDeviceType
from boto.ec2.blockdevicemapping import BlockDeviceMapping
from boto.ec2.connection import EC2Connection
from boto.exception import NoAuthHandlerFound

class EC2Helper():
  """
  A helper utility to launch, terminate, and find instances in EC2. This utility
  wraps the boto python library.
  """

  def __init__(self, config = None, connect = True):
    """
    :type config: str
    :param config: An alternative configuration directory.
      The default is ./ec2helper.ini, relative to the script's directory.
    """
    if config is not None:
      conffile = config
    else:
      conffile = os.path.join(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))), 'ec2helper.ini')

    self.config = SafeConfigParser()
    try:
      self.config.read(conffile)
    except MissingSectionHeaderError:
      sys.exit('Malformed configuration file: %s' % conffile)

    aws_conf = self.get_conf('aws', required = False)
    if 'region' in aws_conf:
      aws_conf['region'] = boto.ec2.get_region(aws_conf['region'])

    if connect:
      try:
        self.ec2 = EC2Connection(**aws_conf)
      except NoAuthHandlerFound:
        sys.exit('Missing \'aws_access_key_id\' or \'aws_secret_access_key\'')

  def get_conf(self, section, required = True):
    """
    Retrieve a named [section] from the configuration and returns it as a
    dictionary.

    :type section: str
    :param section: The name of the [section]

    :type required: bool
    :param required: If set to False and the section does not exist, this method
      returns an empty dictionary. The default is True.
    """
    try:
      return dict(self.config.items(section))
    except NoSectionError:
      if required:
        sys.exit('Missing required configuration section: %s' % section)
    return {}

  def tags_to_filters(self):
    """
    Converts the contents of the tags configuration file to filters for EC2
    instance listing.
    """
    return dict([('tag:%s' % k, v) for k, v in self.get_conf('tags').items()])

  def get_instances(self, instances = None, filters = None):
    """
    Retrieves the instances which match the tags in the configuration, or the
    specified optional filters.
    """
    if filters is not None:
      f = {}
      for item in self.make_list(filters):
        i = item.split('=', 1)
        k = i[0].strip()
        if len(i) == 2:
          v = i[1].strip()
        else:
          if k.startswith('tag:'):
            v = k[4:].strip()
            k = 'tag-key'
          else:
            sys.exit('Invalid filter: %s' % k)
        f[k] = v
    else:
      f = self.tags_to_filters()
    if instances is not None:
      i = self.make_list(instances)
    else:
      i = None
    return self.ec2.get_only_instances(instance_ids = i, filters = f)

  def make_list(self, s, list_delim = ','):
    """
    Creates a list from a string, using the specified delimiter.
    """
    return [x.strip() for x in s.split(list_delim) if x.strip() != '']

  def list_instances(self, show_terminated = False, instances = None, filters = None):
    """
    Lists existing instances, which match the tags in the configuration.
    """
    for e in self.get_instances(instances = instances, filters = filters):
      if e.state in ['terminated'] and not show_terminated:
        continue
      print('=' * 65)
      options = [ 'id', 'ip_address', 'private_ip_address', 'state',
        'instance_type', 'launch_time', 'key_name', 'vpc_id', 'subnet_id',
        'root_device_name', 'root_device_type' ]
      maxlen = 0
      for x in options:
        maxlen = max(maxlen, len(x))
      padding = '%%%ss:' % str(maxlen + 2)
      for x in options:
        print(('%s %%s' % padding) % (x, getattr(e, x)))
      for name, device in e.block_device_mapping.items():
        print(padding % (name))
        for vol in self.ec2.get_all_volumes([device.volume_id]):
          for k, v in vars(vol).items():
            print(('%s  %%s = %%s' % padding[:-1]) % ('', k, v))

  def update_block_devices(self, instance_conf):
    """
    Update the configuration by converting the block_device_map property into an
    actual block device map object.
    """
    b = 'block_device_map'
    if b in instance_conf:
      disks = BlockDeviceMapping()
      for device in self.make_list(instance_conf[b]):
        device_args = self.get_conf('device:%s' % device)
        disks[device] = BlockDeviceType(**device_args)
      instance_conf.update({ b : disks })

  def update_list_properties(self, instance_conf, keys = ['security_group_ids']):
    """
    Update the configuration by converting the specified properties into lists.
    """
    for k in keys:
      if k in instance_conf:
        instance_conf[k] = self.make_list(instance_conf[k])

  def compress_user_data(self, instance_conf):
    """
    Update the user_data script contained in the config.
    """
    k = 'user_data'
    if k in instance_conf:
      out = StringIO.StringIO()
      # won't work with python 2.6
      #with gzip.GzipFile(fileobj = out, mode = 'wb') as f:
      #  f.write(instance_conf[k])
      f = gzip.GzipFile(fileobj = out, mode = 'wb')
      f.write(instance_conf[k])
      f.close()
      instance_conf[k] = out.getvalue()

  def run_instances(self):
    """
    Launches new instances, tagged with the tags in the configuration, and
    configured using the configuration files.
    """
    instance_conf = self.get_conf('instance')
    self.update_block_devices(instance_conf)
    self.update_list_properties(instance_conf)
    self.compress_user_data(instance_conf)

    # create an instance
    reservation = self.ec2.run_instances(**instance_conf)

    # tag the instance created and all attached volumes and network interfaces
    ids = []
    for instance in reservation.instances:
      print('Starting %s' % instance.id)
      while instance.update() in ['pending']:
        time.sleep(1)
      if instance.state != 'running':
        continue
      nic_ids = [e.id for e in instance.interfaces]
      volume_ids = [e.id for e in self.ec2.get_all_volumes(filters = {'attachment.instance-id':instance.id}) ]
      ids = ids + [instance.id] + nic_ids + volume_ids
    self.add_tags(ids)

  def add_tags(self, ids):
    """
    Add tags to the given resources.
    """
    self.ec2.create_tags(ids, self.get_conf('tags'))

  def terminate_instances(self, instances = None, filters = None):
    """
    Terminates existing instances, which match the tags in the configuration.
    """
    # kill instances BE VERY CAREFUL
    term_states = ['terminated', 'shutting-down']
    ids = [e.id for e in self.get_instances(instances = instances, filters = filters) if e.state not in term_states]
    if len(ids) == 0:
      print('No matching instances')
    else:
      print('Terminating: %s' % str(ids))
      line = raw_input('Are you sure (type \'yes\')? ')
      if 'yes' == line.lower():
        self.ec2.terminate_instances(ids)

# End of EC2Helper class

def print_dict(dict, format = '%s = %s'):
  [print(format % (k, v)) for k, v in dict.items()]

def main(args = []):
  """
  Execute with --help for details on available options.
  """
  parser = argparse.ArgumentParser(description = 'A convenience wrapper for managing instances in Amazon EC2')
  parser.add_argument('-c', '--config', help = 'an alternate configuration file')
  parser.add_argument('-a', '--all', help = 'include all matching instances, even terminated ones', action = 'store_true')
  parser.add_argument('-i', '--instances', help = 'comma-separated list of specific instances to terminate or list')
  parser.add_argument('-f', '--filters', help = 'comma-separated list of filters for list or terminate')
  parser.add_argument('command', help = 'commands are: help, list, run, terminate, tags')
  argp = parser.parse_args(args = args)
  if argp.command == 'list':
    bw = EC2Helper(argp.config)
    bw.list_instances(show_terminated = argp.all, instances = argp.instances, filters = argp.filters)
  elif argp.command == 'run':
    bw = EC2Helper(argp.config)
    bw.run_instances()
  elif argp.command == 'terminate':
    bw = EC2Helper(argp.config)
    bw.terminate_instances(instances = argp.instances, filters = argp.filters)
  elif argp.command == 'tags':
    bw = EC2Helper(argp.config, connect = False)
    print_dict(bw.get_conf('tags'))
  elif argp.command == 'help':
    parser.print_help()
  else:
    sys.exit('Unrecognized command, \'%s\'. Try \'help\' instead.' % argp.command)

if __name__ == '__main__':
  try:
    main(sys.argv[1:])
  except KeyboardInterrupt:
    sys.exit('Operation aborted and left in an unknown state.')
