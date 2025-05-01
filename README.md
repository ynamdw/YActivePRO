# YActiveProApi

A set of tools by Ynamics for the Active-PRO Debugger API

## ActiveProApi.py

This script provides a command-line interface (CLI) to access the
Active-PRO application API. It allows you to control the Active-PRO
application through simple string commands over a TCP socket.

### Features

- Connect to the Active-PRO application.
- Send commands to control the Active-PRO application.
- Receive responses from the Active-PRO application.
- Run demonstration code to test the API.

### Usage

To use the script, simply run it from the command line with the desired
command-line arguments.

The `ActiveProApi.py` script has a help option, and provides a
bash-completion script as well.

### Example Scripts

Note: The scripts suppose that `ActiveProApi.py` is present in the working
directory.

#### Export the last 10 minutes of a capture

The `exportActive10min.sh` bash script demonstrates how to export the last
10 minutes of a capture.

#### Export a range of captured data

The `exportAfterLoadAndZoom.sh` bash script demonstrates how to export a
specific range of captured data, after start the debugger and zooming.

## Disclaimer

This project is shared as a courtesy. Pull requests are accepted, but
support will be limited.

## Affiliation

Ynamics is not affiliated with Active Firmware Tools. This repository is
not an endorsement of Active Firmware Tools nor its products.

## NOTICE

https://www.ynamics.com

This product includes software developed by
[Ynamics](https://wwW.ynamics.com) - 50 rue de Pontoise - 95870 BEZONS -
France.

Licensed under the Apache License, Version 2.0 (the "License"); you may not
use this file except in compliance with the License. You may obtain a copy
of the License at

https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
License for the specific language governing permissions and limitations
under the License.
