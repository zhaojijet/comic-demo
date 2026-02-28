#!/bin/bash
# run.sh for comic-demo

export PYTHONPATH=$(pwd)/src:$PYTHONPATH
./.venv/bin/python3 main.py
