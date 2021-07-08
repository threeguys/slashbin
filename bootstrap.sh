#!/bin/bash

ME="ray"

function usage() {
    echo "Usage: ${0} system|user"
    echo "Bootstraps system settings"
}

function bootstrapSystem() {
    sudo apt update
    sudo apt install -y screen
    sudo apt upgrade -y
    sudo addgroup ${ME}
    sudo adduser --ingroup ${ME} ${ME}
    sudo adduser ${ME} sudo
}

function bootstrapAccount() {
    wget -O ~/.screenrc https://raw.githubusercontent.com/threeguys/slashbin/main/screenrc
}

function bootstrapDocker() {
    curl -sSL https://get.docker.com | sh
    sudo adduser ${ME} docker
}

function bootstrapRtlSdr() {
    # Setup dependencies for build
    sudo apt-get remove rtl-sdr
    sudo apt install -y build-essential cmake usbutils libusb-1.0-0-dev git

    # Download the latest version of the drivers
    mkdir -p ${HOME}/software \
        && cd ${HOME}/software \
        && git clone https://github.com/osmocom/rtl-sdr.git

    # Build rtl-sdr drivers
    mkdir -p ${HOME}/software/rtl-sdr/build \
        && cd ${HOME}/software/rtl-sdr/build \
        && cmake-DINSTALL_UDEV_RULES=ON -DDETACH_KERNEL_DRIVER=ON .. \
        && make -j4 \
        && sudo make install \
        && sudo ldconfig

    # Blacklist kernel TV drivers
    DENYLIST_DRIVERS=$(cat <<EOF
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
blacklist dvb_usb_rtl2832u
blacklist dvb_usb_v2
blacklist dvb_core
EOF
)

    echo "${DENYLIST_DRIVERS}" | sudo tee /etc/modprobe.d/rtlsdr-blacklist.conf
    echo "You need to reboot for these changes to take effect."
    echo "You will still need to 'sudo' when running commands unless you change permission on the device."
}

function bootstrapOpenwebRx() {
    # docker pull jketterl/openwebrx-full
    docker pull jketterl/openwebrx:stable
    docker volume create openwebrx-settings
}

function runOpenwebRx() {
    docker run -d \
        --name openwebrx \
        --restart always \
        --device /dev/bus/usb \
        -p 0.0.0.0:80:8073/tcp \
        -v openwebrx-settings:/var/lib/openwebrx \
        jketterl/openwebrx:stable
}

function bootstrapCockpit() {
    sudo apt install -y cockpit cockpit-docker 
}

function bootstrap() {
    case "$1" in
        s|sys|system)
            bootstrapSystem()
        ;;
        u|usr|user)
            bootstrapAccount()
        ;;
        *)
        ;;
    esac
}