#!/bin/bash
set -e

curl -s 10.0.0.10:3000/ta/ta.cer --output /share/ta/ta.cer
curl -s 10.0.0.10:3000/ta/ta.tal --output /share/ta/ta.tal

exit 0
