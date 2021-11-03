#!/bin/bash
set -e

git clone https://github.com/phylsix/nexuslims.git -b devgcp

gcloud functions deploy <FUNCTION NAME> \
--entry-point=generate_image_thumbnail_metafile \
--runtime python39 \
--memory 2048MB \
--max-instances=2 \
--timeout=540s \
--trigger-bucket <RAW DATA BUCKET>

rm -rf nexuslims