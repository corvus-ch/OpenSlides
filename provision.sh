#!/bin/bash

apt-get -y update

apt-get -y install nginx-full uwsgi uwsgi-plugin-python python-pip python python-reportlab python-imaging

pip install django==1.4.5 django-mptt

cat << 'EOF' > /etc/nginx/sites-available/default
server {
  listen          80;
  server_name     _;

  location / {
    uwsgi_pass      unix:///run/uwsgi/app/openslides/socket;
    include         uwsgi_params;
  }

  location /static {
    alias   /vagrant/site-static/;
    expires 30d;
  }

}
EOF

# virtualenv=/home/vagrant/.virtualenvs/projectenv

cat << 'EOF' > /etc/uwsgi/apps-available/openslides.ini
[uwsgi]
uid = vagrant
gid = vagrant
chmod-socket = 777
chown-socket = vagrant
thread = 3
master = 1
env = DJANGO_SETTINGS_MODULE=settings
module = django.core.handlers.wsgi:WSGIHandler()
chdir = /vagrant
socket = /run/uwsgi/app/openslides/socket
vhost = true
EOF

if [ -f /etc/uwsgi/apps-enabled/openslides.ini ];
then
  rm /etc/uwsgi/apps-enabled/openslides.ini
fi
ln -s /etc/uwsgi/apps-available/openslides.ini /etc/uwsgi/apps-enabled/openslides.ini

sudo service nginx restart
sudo service uwsgi restart

sudo apt-get -y install vim w3m

# python /vagrant/manage.py syncdb