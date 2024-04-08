#!/bin/bash
# This script installs the necessary packages for the project
apt install update
apt install build-essential
apt install python3
apt install python3-pip
python3 -m pip install --upgrade pip
python3 -m pip install grpcio
python3 -m pip install grpcio-tools
