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

OUTPUT_FILE="$1"
# Define the duration in seconds (10 minutes = 600 seconds)
DURATION=${2:-600}

# Get the current timestamp for the output file name
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
# Define the output file with the current timestamp
OUTPUT_FILE=${OUTPUT_FILE:=capture_${TIMESTAMP}.csv}

# Check if the application is capturing
IS_CAPTURING=$(./ActiveProApi.py --id=-1 -q --is-capturing)

if [ "$IS_CAPTURING" == "YES" ]; then
    # We can not export to CSV when the session is capture,
    # but we can save the capture from a running session and
    # export from that capture.

    # Generate a temporary file name
    TEMP_ACTIVE="tmp$(date +%s).active"

    # Save the current capture to a temporary file
    ./ActiveProApi.py --id=-1 -q --not-capturing --save-capture "$TEMP_ACTIVE"

    # Start a new ActiveProDebugger.exe
    CMD /C 'C:\Program Files (x86)\Active-Pro Firmware Debugger\ActiveProDebugger.exe' &

    # Wait for the debugger to start
    sleep 5

    # Open the saved capture
    ./ActiveProApi.py --id=-1 -q --not-capturing --open-capture "$TEMP_ACTIVE"
fi

# Export the data between cursors to a CSV file
./ActiveProApi.py --id=-1 -q --set-cursor-x1 -${DURATION} --set-cursor-x2 -0.000000001 --export-between-cursors "$OUTPUT_FILE.tmp"

if [ "$IS_CAPTURING" == "YES" ]; then
    # Clean up the temporary file
    rm "$TEMP_ACTIVE"

    # Exit the ActiveProDebugger
    ./ActiveProApi.py --id=-1 -q --not-capturing
fi

# Process the exported data
#
# Next line does some filtering on the export to remove useless lines for the project
# Adapt to your needs.
#
grep -aivP '(From Modem RX|ANALOG|BATPERCENT|LOGIC|Batmv)' "$OUTPUT_FILE.tmp" | \
    perl -pe 's#\[([0-9A-Fa-f]{1,2})\]#my $i = hex($1); $i >= 0x20 && $i <= 0x7E ? ($i == 0x22 || $1 eq "34" ? q{""} : chr($i)) : $i == 0x0D ? "\\r" : $i == 0x0A ? "\\n" : sprintf("\\x%02X", $i)#ge; s/=EoP/\\n/;' \
    | sort -g \
    > "$OUTPUT_FILE"

# Clean up the temporary file
rm "$OUTPUT_FILE.tmp"
