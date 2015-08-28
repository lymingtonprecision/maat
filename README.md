Maat
====

> Defining the fundamental order of things; distinguishing order from
> chaos.

Maat is our (non-Windows) infrastructure configuration management
system. It helps to keep things running in a sane, logical, and
ordered fashion. Nothing should happen but by Maats hand.

## Overview

Our (non-Windows) infrastructure is architected as a (small) swarm of
minimal Linux hosts running applications in
[Docker](https://www.docker.com/) containers. The primary goals are:

* Flexibility.

  It should be easy to re-organise the infrastructure, spawn new
  host machines, try new applications and host operating systems.

* Low overhead.

  The hosts should use as few resources as possible, passing on as
  much of their provisions to the application containers they run.

* Ease of management.

  Creating a new host should be a matter of a few clicks, adding new
  hosts to an existing application cluster as easy as tagging it with
  that role, validating and updating the entire infrastructure a
  single command.

This repository contains the configuration management scripts to make
this a reality.

Configuration management itself is handled by
[Ansible](http://docs.ansible.com/ansible/). There is a
[Vagrant](https://www.vagrantup.com/) file to help establish an
environment (an Ansible Control Machine) from which you can perform
configuration management tasks with a minimal amount of fuss.

To prepare your workstation to perform configuration management of our
infrastructure install Vagrant, open a command prompt in the directory
containing this file, and run `vagrant up` followed by `vagrant ssh`.

## Expected Operating Environment

* VMware vSphere with a vCenter server.
* Host Virtual Machines created and resource managed manually but
  stored within a single folder within vSphere.
* Access controlled via SSH keys, with an available collection of
  authorised public keys (ideally in the `authorized_keys` folder of
  this repository.)

#### Compatibility

Whilst the Ansible management scripts should work against any Linux
hosts the dynamic inventory script relies upon private vSphere APIs
and has only been tested against vCenter 5.5.0 and ESXI 5.5.0 hosts.

### <a id="create-vm-template">Creating a Virtual Machine Template</a>

Whilst the host virtual machines are expected to be created manually
and we are expressly _not_ defining their operating system beyond
"Linux, running Docker, and manageable via SSH" settling on and using
a standard template will make life much easier.

Our currently preferred option for the base operating system is
[VMware Photon](https://github.com/vmware/photon). To create a
suitable template within vSphere perform the following steps:

1. Follow our
   [instructions for creating an easily clonable Photon template][photon-vsphere-deploy]
   **but** don't power off the VM at the end (or convert it to a
   template just yet.)

2. Install the [`docker-py`][docker-py] library

   1. Download version 1.2.3 of `docker-py`:

      ```sh
      curl -o docker-py.tar.gz https://pypi.python.org/packages/source/d/docker-py/docker-py-1.2.3.tar.gz
      ```

      (Note: later versions of `docker-py` use an incompatible version
      of the Docker API to that used by the Ansible 1.9.2 Docker
      module.)

   2. Install `tar` and `setup.py`:

      ```sh
      sudo tdnf install tar
      sudo tdnf install python-setuptools
      ```

   3. Extract the library files:

      ```sh
      tar -zxf docker-py.tar.gz
      ```

   4. Build and install the library:

      ```sh
      cd docker-py-1.2.3
      python setup.py build
      sudo python setup.py install
      ```

   5. Clean up

      ```sh
      cd ..
      sudo rm -rf docker-py*
      sudo tdnf erase tar
      sudo tdnf erase python-setuptools
      ```

3. Install `sudo`:

   ```sh
   tdnf install sudo
   ```

4. Create an "admin" user account on the VM.

   Choose whatever you like for an account name, so long as it's the
   same across all the hosts.

   ```sh
   useradd -G sudo -m {username}
   ```

5. Add the admin user to the `sudoers` _without password
   authentication_:

   1. Run `visudo`
   2. Add a new entry at the end of the file for:

      ```
      {username} ALL=(ALL) NOPASSWD: ALL
      ```

6. Create a temporary SSH key to use when initialising new VMs and set
   it as an authorised key for the admin account you've created.

   This key does not _need_ to be secured by a pass-phrase as it will
   be removed from the VM when you initialise its configuration
   (being replaced with the set of authorised keys assigned to our IT
   admins.)

   **You will need to keep a copy of this key pair.**

   The easiest way to create a new key pair is:

   1. On the Ansible Control Machine:

      ```sh
      ssh-keygen -t rsa -b 4096 -f init.key
      ```

   2. Copy the resulting `init.key.pub` file to the template VM.

   3. On the template VM, add the key as an authorised key for the
      admin user:

      ```sh
      mkdir /home/{username}/.ssh
      cat {path/to/init.key.pub} > /home/{username}/.ssh/authorized_keys
      chmod 0700 /home/{username}/.ssh
      chmod 0600 /home/{username}/.ssh/authorized_keys
      chown -R {username} /home/{username}/.ssh
      ```

   4. Disable the admin users password:

      ```sh
      passwd -d {username}
      ```

7. Power off the VM.
8. Convert the VM to a template.

[photon-vsphere-deploy]: https://github.com/lymingtonprecision/photon-vsphere-deploy
[docker-py]: https://github.com/docker/docker-py

## Tasks and How To Accomplish Them

Unless stated otherwise all commands are run from the console of the
Ansible Control Machine in the `ansible` sub-directory of this
repository.

Any `ansible` invocation assumes two things:

1. That you've defined `ANSIBLE_REMOTE_USER` by setting it to the username
   Ansible should connect as.

   ```sh
   export ANSIBLE_REMOTE_USER={username}
   ```

2. That you've added an SSH private key to the SSH agent with which
   Ansible will be able to connect.

   ```sh
   ssh-add {path/to/private.key}
   ```

   (You can alternatively set `ANSIBLE_PRIVATE_KEY_FILE` to the path
   to your private key file.)

   If you are using the included Vagrant VM your `$HOME/.ssh`
   directory will be mounted at `/vagrant/.ssh` and if an `id_rsa`
   and/or `github_rsa` file exists within it will have automatically
   been added to the SSH agent--so you don't need to do anything!

### Managing SSH Keys

There are potentially _two_ private key files that you will need
access to:

1. The key file used in the VM template for the initialisation of new
   VMs.
2. Your own personal key file which will be used for all
   non-initialisation tasks.

In addition to those _private_ key files you will also need to
maintain a directory of _public_ key files for those users who you
wish to be able to use Maat. It is recommended that you store these
public keys inside this source repository under the top level
`authorized_keys` directory.

You should **never** store a private key file in this repository. Not
even the initialisation user's key file.

#### Creating a New Key Pair

1. Create a `.ssh` folder in your `$HOME` directory.

   On Windows this is typically `c:\users\{your username}`, but check
   the `HOME` `env`ironment variable.

2. Start the Vagrant VM included in this repository and `ssh` into it.

3. Use `ssh-keygen` to generate a new key pair:

   ```sh
   ssh-keygen -t rsa -b 4096 -f /vagrant/.ssh/id_rsa -C "your@email-address.com"
   ```

   It is **strongly** advised that you enter a _strong_ passphrase
   when prompted.

4. Copy your public key to the authorised keys directory:

   ```sh
   cp /vagrant/.ssh/id_rsa.pub /vagrant/authorized_keys/{unique name}.pub
   ```

   Note that you need to provide a unique name for your key,
   usernames/email addresses work best as they are easily uniquely
   identifiable.

(Note: this SSH key pair doesn't have to be single use! You can use it
anywhere you need to provide one: like Github for example.)

Make a _secure_ backup of both your private and public keys--somewhere
only you will be able to recover them from.

#### Adding a Key to the Authorised Keys of Existing Hosts

New hosts will pick up whichever set of keys is current at the time
they are initialised but existing hosts need to be explicitly told to
reset their authorised key lists.

With the new public key file added to the `authorized_keys` directory
in this repository you can update the authorized keys on all the
hosts:

1. Set the vSphere environment variables as per the
   [update everything](#update-all) procedure.
2. Instead of running the `site.yml` playbook run
   `authorized_keys.yml`:

   ```sh
   ansible-playbook authorized_keys.yml
   ```

(It should, perhaps, go without saying but you can't add _your own_
key. You'll need to give your public key to someone who already has
access for them to run the above update.)

#### Removing a Key from the Authorised Keys of Existing Hosts

This is the same as adding a key except instead of copying a new
public key into the `authorized_keys` directory just delete the one(s)
that need to be removed.

(Unlike adding a key you can _delete_ your _own_ key, so be careful
less you lock yourself out.)

### Creating a New Virtual Machine

1. Within vSphere, clone the Virtual Machine template (see
   [creating a virtual machine template](#create-vm-template) above)
   and power on the created VM.

2. Add the VMs IP address to the `/tmp/init.hosts` file:

   ```sh
   echo {vm ip} > /tmp/init.hosts
   ```

3. Run the `init.yml` playbook against the VM:

   ```sh
   ansible-playbook init.yml -i /tmp/init.hosts --private-key=init.key
   ```

   `init.key` should be the path to an authorised SSH private key with
   which Ansible can authenticate (this is an expected artifact when
   following the [template creation process](#create-vm-template).)

   For convenience the above command is provided as a shell alias:

   ```sh
   ansible-init-hosts
   ```

   (This assumes that the `init.key` and `init.yml` files exist in the
   `/vagrant/ansible` directory on the control machine VM and that
   you've populated `/tmp/init.hosts`.)

### Add or Remove a Role to/from a Virtual Machine

Within vSphere, add/remove the corresponding tag to/from the virtual
machine.

Re-run the site configuration playbook, see
[Updating the Configuration of All Virtual Machines](#update-all).

### <a id="update-all">Updating the Configuration of All Virtual Machines</a>

Set the vSphere environment variables:

* `VSPHERE_HOST` the FQDN of the vCenter server to connect to.
* `VSPHERE_USER` the user name to use when connecting to vCenter.
* `VSPHERE_PASSWORD` the password to use for authenticating with vCenter.
* `VSPHERE_PATH` the vSphere inventory path to the folder containing
  the VMs you wish to manage.

The default Ansible hosts file (`/etc/ansible/hosts`) is linked to the
included dynamic vSphere inventory script so all you need to do is
specify the playbook to run:

```sh
ansible-playbook site.yml
```

## Playbook Reference

### `init.yml`

Initialises a new host with the user accounts, SSH keys, and other
configuration settings required to run the other playbooks.

You **must** run this playbook on *all* new hosts before including
them in the runs of any other playbooks.

### `site.yml`

Configures all currently defined hosts to their tagged roles.

## Role Reference

The supported roles that can be added to VMs are:

### `consul`

Runs a [`consul`](https://www.consul.io/) server gent on the VM,
joined in a cluster with any other VMs with the same tag.

A [`registrator`](http://gliderlabs.com/registrator/) service is also
started on the host for automatic registration of other services
within the Consul service directory.

##### Domain

The Consul DNS interface will respond to queries under the
`consul.{{ ansible_domain }}` of the VM upon which it runs.

(E.g. if your VM's FQDN is `sr01.example.com` then queries will be
resolved under `consul.example.com`.)

This enables us to delegate the `consul` sub-domain to the Consul
hosts within our primary domain servers.

##### Ports

Exposes ports `8300-8302`, `8400`, `8500`, `8600` and `53` on the host.

`8500` is the Consul Web Interface port.

`53` and `8600` are the
[DNS interface](https://www.consul.io/docs/agent/dns.html) ports

##### Data

Stored under `/data/consul` on the host.

## License

Copyright © 2015 Lymington Precision Engineers Co. Ltd.

This project is licensed under the terms of the MIT license.
