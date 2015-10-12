import random
import re
import vsphere_inventory as vsphere

from os.path import join, dirname

try:
    import json
except ImportError:
    import simplejson as json

def readNamesFrom(filepath):
    with open(filepath) as f:
        return f.readlines()

def randomName(lefts, rights):
    left = random.choice(lefts).rstrip()
    right = random.choice(rights).rstrip()
    return left + '-' + right

def nodeExists(knownNames, name):
    matches = [n for n in knownNames if re.match(name + '(\.|$)', n)]
    return len(matches) > 0

def generateName(knownNames):
    leftSides = readNamesFrom(join(dirname(__file__), 'names', 'lefts.txt'))
    rightSides = readNamesFrom(join(dirname(__file__), 'names', 'rights.txt'))

    for i in range(10):
        name = randomName(leftSides, rightSides)
        if not nodeExists(knownNames, name):
            return name
    else:
        print('Failed to generate a new, unique, name after 10 attempts')
        exit(2)

if __name__ == '__main__':
    parser = vsphere.argparser()
    args = parser.parse_args()

    vs = vsphere.vsphereConnect(args.server, args.user, args.password)
    vimSession = vsphere.vimLogin(vs)
    vms = vsphere.vmsAtPath(vs, vimSession, args.path)

    vmList = [vm['hostname'] for vm in vms]
    newName = generateName(vmList)
    print(newName)
