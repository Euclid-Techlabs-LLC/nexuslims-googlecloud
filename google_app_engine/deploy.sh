#!/bin/bash

set -e
git clone https://github.com/phylsix/nexuslims.git -b devgcp

gcloud app deploy
# gcloud app deploy cron.yaml

rm -rf nexuslims