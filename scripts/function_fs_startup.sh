#!/bin/bash
modprobe libcomposite
cd "$(dirname "$(realpath "$0")")"/../

source venv/bin/activate
python scripts/function_fs_server.py