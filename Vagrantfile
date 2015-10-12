# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure(2) do |config|
  config.vm.box = "ubuntu/trusty64"
  config.vm.hostname = "ansible"

  config.vm.synced_folder ".", "/vagrant", mount_options: ["dmode=775,fmode=700"]
  config.vm.synced_folder "~/.ssh", "/vagrant/.ssh", mount_options: ["dmode=775,fmode=600"]

  config.vm.provider "virtualbox" do |vb|
    vb.gui = false
    vb.memory = "1024"
  end

  config.vm.provision "file", source: "./motd_notice", destination: "~/motd_notice"
  config.vm.provision "shell", inline: <<-SHELL
    sudo mv /home/vagrant/motd_notice /etc/update-motd.d/62-maat-usage
    sudo chmod +x /etc/update-motd.d/62-maat-usage
    run-parts /etc/update-motd.d | sudo tee /var/run/motd.dynamic
  SHELL

  config.vm.provision "shell", inline: <<-SHELL
    # add ansible ppa
    sudo apt-get install -y software-properties-common
    sudo apt-add-repository ppa:ansible/ansible

    # update apt cache
    sudo apt-get update

    sudo apt-get install -y ansible
  SHELL

  config.vm.provision "shell", inline: <<-SHELL
    sudo apt-get install -y python-pip
    # install PyOpenSSL (https://urllib3.readthedocs.org/en/latest/security.html#pyopenssl)
    sudo pip install pyopenssl ndg-httpsclient pyasn1
    sudo pip install -U pyvmomi requests
  SHELL

  config.vm.provision "shell", inline: <<-SHELL
    echo "" > /home/vagrant/.profile
    echo "if [ -f ~/.bashrc ]; then" >> /home/vagrant/.profile
    echo "  . ~/.bashrc" >> /home/vagrant/.profile
    echo "fi" >> /home/vagrant/.profile
    echo "" >> /home/vagrant/.profile
    echo "# start ssh agent" >> /home/vagrant/.profile
    echo "eval \\$(ssh-agent)" >> /home/vagrant/.profile

    echo "" >> /home/vagrant/.profile
    echo "# if we have a private key add it to the agent" >> /home/vagrant/.profile
    echo "if [ -f /vagrant/.ssh/id_rsa ]; then" >> /home/vagrant/.profile
    echo "    ssh-add /vagrant/.ssh/id_rsa" >> /home/vagrant/.profile
    echo "fi" >> /home/vagrant/.profile
    echo "# if we have a github private key add it to the agent" >> /home/vagrant/.profile
    echo "if [ -f /vagrant/.ssh/github_rsa ]; then" >> /home/vagrant/.profile
    echo "    ssh-add /vagrant/.ssh/github_rsa" >> /home/vagrant/.profile
    echo "fi" >> /home/vagrant/.profile

    echo "" >> /home/vagrant/.profile
    echo "export PYTHONWARNINGS=\"ignore:Unverified HTTPS request\"" >> /home/vagrant/.profile

    echo "" >> /home/vagrant/.profile
    echo "# cd to ansible playbook directory" >> /home/vagrant/.profile
    echo "cd /vagrant/ansible" >> /home/vagrant/.profile
  SHELL

  config.vm.provision "shell", inline: <<-SHELL
    sudo rm -f /etc/ansible/hosts
    sudo ln -s /vagrant/ansible/vsphere_inventory.py /etc/ansible/hosts
  SHELL

  config.vm.provision "shell", inline: <<-SHELL
    echo "alias ansible-init-hosts='ansible-playbook init.yml -i /tmp/init.hosts --private-key=init.key'" > /home/vagrant/.bash_aliases
    echo "alias apb=ansible-playbook" >> /home/vagrant/.bash_aliases
    echo "alias ng='python /vagrant/ansible/name_generator.py'" >> /home/vagrant/.bash_aliases
  SHELL
end
