#!/bin/bash
#
# Example of a script that:
#
# 1. Starts the Active-PRO Debugger
# 2. Loads captured data
# 3. Zooms to a range
# 4. Selects and exports the range as CSV and PNG files.
# 5. Converts the CSV data to a HEX representation.
# 6. Closes the Active-PRO Debugger
#
# Repeats the above for another copy of the capture.
#
# Compresses to a 7-zip archive
#
CAPTURE1=capture1.active
CAPTURE2=capture2.active
CSV1=capture1.csv
HEX1=capture1.hex
SC1=capture1.png
CSV2=capture2.csv
HEX2=capture2.hex
SC2=capture2.png

#
# Load and export CAPTURE1
#
CMD /C 'C:\Program Files (x86)\Active-Pro Firmware Debugger\ActiveProDebugger.exe' &

sleep 3
./ActiveProApi.py --open-capture "$CAPTURE1"
sleep 2
OFFSET1=176.78445
OFFSET2=176.78455
./ActiveProApi.py --zoom-from $OFFSET1 $OFFSET2
./ActiveProApi.py --set-cursor-x1 $OFFSET1 --set-cursor-x2 $OFFSET2 --export-between-cursors "$CSV1" --save-screenshot "${SC1}"
xxd "$CSV1" > "$HEX1"
./ActiveProApi.py --exit

#
# Load and export CAPTURE2
#
CMD /C 'C:\Program Files (x86)\Active-Pro Firmware Debugger\ActiveProDebugger.exe' &

sleep 3
./ActiveProApi.py --open-capture "$CAPTURE2"
sleep 1
OFFSET1=176.7844
OFFSET2=176.7846
./ActiveProApi.py --zoom-from $OFFSET1 $OFFSET2
./ActiveProApi.py --set-cursor-x1 $OFFSET1 --set-cursor-x2 $OFFSET2 --export-between-cursors "$CSV2" --save-screenshot "${SC2}"
sleep 1
xxd "$CSV2" > "$HEX2"
./ActiveProApi.py --exit

# Compress to archive (if condition to disable this step)
# shellcheck disable=2050
if [ 1 -eq 1 ] ; then
    7z a -t7z -m0=lzma2 -mx=9 -myx=9 -mqs=on -ms=on \
        archive.7z \
        "$(basename "$0")" \
        "${CAPTURE1}" "${CSV1}" "${HEX1}" "${SC1}" \
        "${CAPTURE2}" "${CSV2}" "${HEX2}" "${SC2}"
fi
