#!/usr/bin/env python2
# Copyright (C) 2015 - Lymington Precision Engineers Co. Ltd.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""vSphere Virtual Machine Ansible Inventory Lister

Generates a [dynamic Ansible inventory](http://docs.ansible.com/ansible/developing_inventory.html)
from VMWare vSphere.
"""

import os
import argparse
import getpass
import atexit

import urllib
import requests

from functools import partial
from itertools import chain
from xml.dom import minidom

from pyVim import connect
from pyVmomi import vmodl
from pyVmomi import vim
from pyVmomi.VmomiSupport import Object
from pyVmomi.SoapAdapter import SoapResponseDeserializer

try:
    import json
except ImportError:
    import simplejson as json

# use PyOpenSSL instead of plain ssl
import urllib3.contrib.pyopenssl
urllib3.contrib.pyopenssl.inject_into_urllib3()

#
# Environment Variable Parsing
#
class EnvArg(argparse.Action):
    def __init__(self, envvar, required=True, default=None, help="", **kwargs):
        if envvar in os.environ:
            default = os.environ[envvar]
        if required and default:
            required = False
        if envvar:
            help = help + ", overrides environment variable " + envvar

        super(EnvArg, self).__init__(
            default=default,
            required=required,
            help=help,
            **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


def helpEpilog():
    return '''
You will be prompted, interactively, for the password if it is not
provided.

## Using with Ansible

Rather than running the script and outputting the results to a file
which you then pass to Ansible you can instead specify this script as
the inventory file:

    ansible -i vsphere_inventory.py
    ansible-playbook <playbook.yml> -i vsphere_inventory.py

You will need to configure the script via environment variables when
using it directly with Ansible as there is no means of passing it
command line arguments.'''


def argparser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=helpEpilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter)

    # Ansible inventory arguments
    parser.add_argument(
        "--list",
        action="store_true",
        help="flag to output groups and hosts")
    parser.add_argument(
        "--host",
        default=None,
        help="restrict output to specified host")

    # vSphere connection arguments
    parser.add_argument(
        "-s", "--server",
        action=EnvArg, envvar="VSPHERE_SERVER",
        required=True,
        help="the vCenter server to connect to")
    parser.add_argument(
        "-u", "--user",
        action=EnvArg, envvar="VSPHERE_USER",
        required=True,
        help="the user to authenticate as")
    parser.add_argument(
        "--password",
        action=EnvArg, envvar="VSPHERE_PASSWORD",
        required=False,
        help="the password to authenticate with")
    parser.add_argument(
        "-p", "--path",
        action=EnvArg, envvar="VSPHERE_PATH",
        required=True,
        help="the vSphere path under which to search for VMs")

    return parser


#
# Connecting to the vSphere API
#

def vsphereConnect(server, user, password=None):
    '''
    Returns a (PyVmomi) vSphere connection to `server`, authenticated
    as `user` using `password`.

    If no `password` is provided it will be prompted for interactively.

    `exit`s the running process on connection failure.
    '''
    if not password:
        password = getpass.getpass("vCenter password for " + user + ": ")

    try:
        vsphere = connect.Connect(host=server, user=user, pwd=password)
        atexit.register(connect.Disconnect, vsphere)
    except Exception as err:
        print("\n* * *\n")
        print('Failed to connect to vSphere server ' + server + ' as ' + user)
        print("\n* * *\n")
        print(('Error: %s') % (err))
        exit(2)

    return vsphere


#
# Connecting to Vim
#
# **Note:**
# This is entirely reliant on private, undocumented, unsupported, APIs
# and has been backwards engineered from the vSphere PowerCLI tools.
#

def getSessionTicket(vsphere, serviceKey):
    '''
    Returns a Vim session ticket for the specified service under the
    provided `vsphere` session.
    '''
    sessionTicketReq = vsphere.content.sessionManager._stub.SerializeRequest(
        vsphere.content.sessionManager,
        info=Object(
            name="AcquireSessionTicket",
            version="vim.version.version1",
            wsdlName="AcquireSessionTicket",
            params=[Object(name="serviceKey", version="vim.version.version1",type="string")],
            result=None),
        args=[serviceKey])

    stub = vsphere.content.sessionManager._stub
    conn = stub.GetConnection()
    conn.request('POST', stub.path, sessionTicketReq,
                 {'Cookie': stub.cookie,
                  'SOAPAction': stub.versionId,
                  'Content-Type': 'text/xml; charset=utf-8'})
    r = conn.getresponse()
    rx = minidom.parse(r)

    return rx.getElementsByTagName('returnval')[0].firstChild.data


def xmlToEndPoint(returnValNode):
    '''
    Transforms an XML Vim service end point definition to an Object
    '''
    return Object(name=returnValNode.getElementsByTagName('instanceName')[0].firstChild.data,
                  uuid=returnValNode.getElementsByTagName('instanceUuid')[0].firstChild.data,
                  url=returnValNode.getElementsByTagName('url')[0].firstChild.data,
                  key=returnValNode.getElementsByTagName('key')[0].firstChild.data)


def isInventoryServiceEndpoint(endPoint):
    return endPoint.name.startswith('VSPHERE-INVENTORY-SERVICE/')


def getInventoryService(vsphere):
    '''
    Returns the Vim Inventory Service details from vsphere, as an Object
    '''
    req = vsphere.content.sessionManager._stub.SerializeRequest(
        'ServiceDirectory',
        info=Object(
            name="QueryServiceEndpointList",
            version="vim.version.version1",
            wsdlName="QueryServiceEndpointList",
            params=[],
            result=None),
        args=[])

    stub = vsphere.content.sessionManager._stub
    conn = stub.GetConnection()
    conn.request('POST', stub.path, req,
                 {'Cookie': stub.cookie,
                  'SOAPAction': stub.versionId,
                  'Content-Type': 'text/xml; charset=utf-8'})
    r = conn.getresponse()
    rx = minidom.parse(r)

    endPoints = map(xmlToEndPoint, rx.getElementsByTagName('returnval'))
    inventoryService = filter(isInventoryServiceEndpoint, endPoints)[0]

    return inventoryService


def vimLogin(vsphere):
    '''
    Returns a `urllib` Session that has been logged in to the Vim
    Inventory Service associated with the provided `vsphere` connection
    '''
    inventoryService = getInventoryService(vsphere)
    sessionTicket = getSessionTicket(vsphere, inventoryService.key)

    urlParams = urllib.urlencode({'action': 'loginByTicket', 'ticket': sessionTicket})
    url = inventoryService.url + "/login?" + urlParams

    s = requests.Session()
    s.verify = False
    s.baseUrl = inventoryService.url

    r = s.get(url)

    if r.status_code == 200:
        return s
    else:
        return null


def postVimQuery(vimSession, query):
    '''
    Sends an XQuery request to Vim and returns the (parsed) XML result set
    '''
    url = vimSession.baseUrl + "/secure/query"
    r = vimSession.post(url, data=query, stream=True)
    rx = minidom.parse(r.raw)

    return rx.getElementsByTagName('resultSet')[0].childNodes


#
# Retrieving VM tag details from Vim
#
# **Note:**
# This is entirely reliant on private, undocumented, unsupported, APIs
# and has been backwards engineered from the vSphere PowerCLI tools.
#

def xmlToTag(xml):
    '''
    Transforms an XML vSphere Tag definition to an Object
    '''
    return Object(name=xml.getElementsByTagName('name')[0].firstChild.data,
                  category=xml.getElementsByTagName('category')[0].firstChild.data)


def xmlToTaggedVm(xml):
    '''
    Transforms an XML vSphere VM definition--with tags--to an Object
    '''
    tags = map(xmlToTag, xml.getElementsByTagName('tag'))

    return Object(uuid=xml.getElementsByTagName('uuid')[0].firstChild.data,
                  name=xml.getElementsByTagName('name')[0].firstChild.data,
                  tags=tags)


def getAllVMTagAssignments(vimSession):
    '''
    Returns a list of Object representations of all tagged VMs
    returned by Vim, with their tags
    '''

    query = '''
    declare namespace qs = 'urn:vmware:queryservice';
    declare namespace is = 'urn:inventoryservice';
    declare namespace vim25='urn:vim25';
    declare default element namespace 'urn:vim25';
    declare namespace xlink='http://www.w3.org/1999/xlink';

    import module namespace tagging = 'urn:vmware:queryservice:tagging' at '/builtin-functions/tagging';

    let $vms := doc('.')/VirtualMachine[config/template = 'false']

    let $vmsWithTags :=
      for $vm in $vms
        let $tags := /is:InventoryServiceTag[@qs:id = tagging:tagsOnDoc($vm/@qs:id)]
        return
          if (count($tags) > 0) then (
            <vm id='{$vm/@qs:id}'>
              {$vm/config/uuid}
              {$vm/name}
              {$vm/parent}
              <tags>
              {for $tag in $tags
                let $category := /is:InventoryServiceCategory[@qs:id = $tag/is:category/@xlink:href]
                return
                  <tag id='{$tag/@qs:id}'>
                    <category id='{$category/@qs:id}'>{$category/is:info/is:name/text()}</category>
                    <name>{$tag/is:info/is:name/text()}</name>
                    <description>{$tag/is:info/is:description/text()}</description>
                  </tag>}
              </tags>
            </vm>)
          else (
            <vm/>)

    return $vmsWithTags[@id]
    '''

    vms = postVimQuery(vimSession, query)

    return map(xmlToTaggedVm, vms)


#
# Retrieving VM details from vSphere
#

def isTemplate(vm):
    return vm.config.template or vm.name.endswith('template')


def isVirtualMachine(vm):
    return isinstance(vm, vim.VirtualMachine) and not isTemplate(vm)


def vmIPAddresses(vm):
    vSphereNetworks = filter(lambda n: n.network is not None, vm.guest.net)
    return list(chain(*(map(lambda n: n.ipAddress, vSphereNetworks))))


def defaultIPv4Address(vm):
    def isIPv4Address(ip):
       return ip.find('.') >= 0

    ips = filter(isIPv4Address, vmIPAddresses(vm))
    return ips[0]


def vmToDictionary(vm):
    '''
    Transforms a vSphere VirtualMachine instance to a minimal
    dictionary representation.
    '''
    d = {'name': vm.name,
         'uuid': vm.summary.config.uuid,
         'status': vm.runtime.powerState,
         'hostname': vm.summary.guest.hostName or vm.name,
         'ipAddresses': vmIPAddresses(vm),
         'ansible_ssh_host': defaultIPv4Address(vm)}

    return d


def copyTagsToVM(taggedVms, vm):
    '''
    If `taggedVms` contains an entry matching the `uuid` of `vm` then
    a copy of `vm` is returned containing a list of the tag names
    from that entry (under a `tags` key.)

    Otherwise a copy of `vm` is returned with `tags` set to an empty
    list.
    '''
    mergedVm = vm.copy()
    taggedVm = next((taggedVm for taggedVm in taggedVms if taggedVm.uuid == vm['uuid']), None)

    if taggedVm:
        mergedVm.update({'tags': map(lambda t: t.name, taggedVm.tags)})
    else:
        mergedVm.update({'tags': []})

    return mergedVm


def vmMetaData(vms):
    '''
    Returns the Ansible `_meta`data dictionary for the given VMs.
    '''
    def addVmHostVar(meta, vm):
        meta[vm['hostname']] = vm
        return meta

    return {'_meta': {'hostvars': reduce(addVmHostVar, vms, {})}}


def vmDetails(vsphere, vmName):
    '''
    Returns a dictionary defining the VM `vmName` or `None` if no such
    VM exists.
    '''
    r = vsphere.content.searchIndex.FindByDnsName(None, vmName, True)

    if r:
        return vmToDictionary(r)
    else:
        return None


def vmsAtPath(vsphere, vim, path):
    '''
    Returns a list of dictionaries detailing the VMs under the
    specified path.
    '''
    si = vsphere.content.searchIndex
    vms = si.FindByInventoryPath(path)
    vmTags = getAllVMTagAssignments(vim)

    if vms is None:
        return []

    vms = filter(isVirtualMachine, vms.childEntity)
    vms = map(partial(copyTagsToVM, vmTags), map(vmToDictionary, vms))

    return vms


def groupVmsByTag(vms):
    def addVmToTagList(tags, vm):
        for tag in vm['tags']:
            if tag not in tags:
                tags[tag] = []
            tags[tag].append(vm['hostname'])
        return tags

    return reduce(addVmToTagList, vms, {})


#
#  Main
#

if __name__ == '__main__':
    parser = argparser()
    args = parser.parse_args()

    vsphere = vsphereConnect(args.server, args.user, args.password)
    vimSession = vimLogin(vsphere)

    if args.host is not None:
      vm = vmDetails(vsphere, args.host)
      print(json.dumps(vm or {}, indent=4))
    else:
      vms = vmsAtPath(vsphere, vimSession, args.path)
      groups = groupVmsByTag(vms)
      meta = vmMetaData(vms)
      vmList = meta.copy()
      vmList['all'] = map(lambda vm: vm['hostname'], vms)
      vmList.update(groups)
      print(json.dumps(vmList, indent=4))
