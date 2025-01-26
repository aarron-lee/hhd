#!/bin/bash

if [ "$EUID" -eq 0 ]; then
    echo "This script must be not be run as root, don't use sudo" >&2
    exit 1
fi

# horipad steam controller: 
# edit ~/.steam/steam/config/config.vdf
# add to SDL_GamepadBind
# 060000000d0f00009601000000000000,Steam Controller (HHD),a:b0,b:b1,x:b2,y:b3,back:b6,guide:b8,start:b7,leftstick:b9,rightstick:b10,leftshoulder:b4,rightshoulder:b5,dpup:h0.1,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,leftx:a0,lefty:a1,rightx:a3,righty:a4,lefttrigger:a2,righttrigger:a5,paddle1:b13,paddle2:b12,paddle3:b15,paddle4:b14,misc2:b11,misc3:b16,misc4:b17,crc:ea35,

# disable built in bazzite service
sudo systemctl disable --now hhd@$USER.service
# disable built-in hhd on reboots
sudo systemctl mask hhd@$USER.service

sudo systemctl disable --now hhd_local.service

cd ~/.local/bin

sudo rm -rf ./hhd

git clone https://github.com/aarron-lee/hhd.git && cd hhd

git checkout local_install

sudo rm -rf venv

python -m venv --system-site-packages venv

source ./venv/bin/activate

./venv/bin/pip install -e .

./venv/bin/pip install git+https://github.com/aarron-lee/adjustor@plugin_check

# cannot directly cat into /etc/systemd/system/ (probably due to se linux)
cat << EOF > "./hhd_local.service"
[Unit]
Description=hhd local service

[Service]
Type=simple
Nice = -15
Restart=always
RestartSec=5
WorkingDirectory=/home/$USER/.local/bin/hhd/venv/bin
ExecStart=/home/$USER/.local/bin/hhd/venv/bin/hhd --user $USER
Environment="HHD_HORI_STEAM=1"
Environment="HHD_PPD_MASK=0"
Environment="HHD_GS_STANDBY=0"
Environment="HHD_GS_STEAMUI_HALFHZ=0"
Environment="HHD_GS_DPMS=0"

[Install]
WantedBy=default.target
EOF

sudo cp ./hhd_local.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now hhd_local.service

