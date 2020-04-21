#!/bin/bash
modprobe libcomposite
python "$(dirname "$(realpath "$0")")"/function_fs_server.py