#!/usr/bin/env bash
# Regenerate InverterMonitor.xcodeproj from generate_project.rb.
set -euo pipefail
GEM_HOME="/opt/homebrew/Cellar/cocoapods/1.16.2_2/libexec" \
GEM_PATH="/opt/homebrew/Cellar/cocoapods/1.16.2_2/libexec" \
ruby "$(dirname "$0")/../generate_project.rb"
