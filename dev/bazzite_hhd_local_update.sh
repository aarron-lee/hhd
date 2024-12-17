#!/bin/bash

cd $HOME/.local/bin/hhd

git pull

# disable hhd_dev if already running
sudo systemctl disable --now hhd_local.service
sudo systemctl disable --now hhd@$USER.service

./venv/bin/pip install -e .
./venv/bin/pip install git+https://github.com/aarron-lee/adjustor@plugin_check

# handle for SE linux
sudo chcon -u system_u -r object_r --type=bin_t /var/home/$(whoami)/.local/bin/hhd/venv/bin/hhd
sudo chcon -u system_u -r object_r --type=bin_t /var/home/$USER/.local/bin/hhd/venv/bin/adjustor

sudo systemctl daemon-reload
sudo systemctl enable --now hhd_local.service
