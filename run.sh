#!/bin/bash
cd /srv/app/stroke-detection-app;
python3 -m venv ~/.venvs/mi-proyecto
source ~/.venvs/mi-proyecto/bin/activate;
python3 main.py
