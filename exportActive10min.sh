#!/bin/bash
# ===============================================================================
# NOTICE
# ===============================================================================
# This product includes software developed by Ynamics (https://www.ynamics.com/).
# 
# Copyright 2025 Ynamics - 50 rue de Pontoise - 95870 BEZONS - France - https://www.ynamics.com
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
# https://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# Define the duration in seconds (10 minutes = 600 seconds)
DURATION=600

# Get the current timestamp for the output file name
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Define the output file with the current timestamp
OUTPUT_FILE="capture_${TIMESTAMP}.csv"

./ActiveProApi.py --set-cursor-x1 -${DURATION} --set-cursor-x2 -0.000000001 --export-between-cursors $OUTPUT_FILE.tmp
# Next line does some filtering on the export to remove useless lines for the project
# Adapt to your needs.
grep -ivP '(From Modem RX|LOGIC|Batmv)' $OUTPUT_FILE.tmp > $OUTPUT_FILE
rm $OUTPUT_FILE.tmp
