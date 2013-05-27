#!/bin/bash
# This script make sure all dependencies for running OpensSlides on a Ubuntu
# with nginx and uwsgi so that sites-static can be used to serve customized
# styles and images.
#
# After a fress installation the following two commands must be executed. Make
# sure you are in the apps directory.
#
# $ python extras/scripts/create_local_settings.py
# $ python manage.py syncdb
#
# The script is targeted for shell provisioning of a vagrant manage virtualbox
# vm. If run on a production machine the following two variables need to be
# changed.
#
# The user the uwsgi process should run with.
#
# On production this needs to be set to www-data.

user=vagrant

# The apps path
#
# On production set to /srv/www/openslides

dir=/vagrant

apt-get -y update

apt-get -y install nginx-full uwsgi uwsgi-plugin-python python-pip python python-reportlab python-imaging

pip install django==1.4.5 django-mptt

cat << EOF > /etc/nginx/sites-available/default
server {
  listen 80;
  server_name _;

  location / {
    uwsgi_pass unix:///run/uwsgi/app/openslides/socket;
    include uwsgi_params;
  }

  location /static {
    alias $dir/site-static/;
  }

}
EOF

# virtualenv=/home/vagrant/.virtualenvs/projectenv

cat << EOF > /etc/uwsgi/apps-available/openslides.ini
[uwsgi]
uid = $user
gid = $user
chmod-socket = 777
chown-socket = $user
thread = 3
master = 1
env = DJANGO_SETTINGS_MODULE=settings
module = django.core.handlers.wsgi:WSGIHandler()
chdir = $dir
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
