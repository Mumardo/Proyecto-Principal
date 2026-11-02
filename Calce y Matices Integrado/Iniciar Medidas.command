#!/bin/bash

PROJECT_DIRECTORY="$(cd "$(dirname "$0")" && pwd)"

open -a "Visual Studio Code" "$PROJECT_DIRECTORY"
cd "$PROJECT_DIRECTORY" || exit 1
python3 app.py
