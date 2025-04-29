#!/usr/bin/env python3
"""
Provides a CLI to access the Active-PRO application API

@copyright Copyright (c) 2025-2025 Ynamics SARL - France
@license Apache License, Version 2.0
@link https://www.ynamics.com/
@author MDW / YNAMICS

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import socket
import argparse
import os
import logging
import subprocess
import sys

# Set up the logger in the root of the script
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('ActiveProAPI')

class ActiveProAPI:
    def __init__(self, host='localhost', port=37800):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.verbose = True

    def connect(self):
        self.socket.connect((self.host, self.port))

    def disconnect(self):
        self.socket.close()

    def send_command(self, command):
        logger.info(f"Command: {command}")
        self.socket.sendall((command + '\n').encode())
        response = self.socket.recv(4096).decode().strip()
        logger.info(f"Response: {response}")
        return response

    def hello(self):
        return self.send_command('Hello')

    def is_connected(self):
        return self.send_command('isConnected')

    def start_capture(self):
        return self.send_command('StartCapture')

    def stop_capture(self):
        return self.send_command('StopCapture')

    def is_capturing(self):
        return self.send_command('isCapturing')

    def get_capture_size(self):
        return self.send_command('GetCaptureSize')

    def get_capture_time(self):
        return self.send_command('GetCaptureTime')

    def get_logic(self):
        return self.send_command('GetLogic')

    def get_ch1(self):
        return self.send_command('GetCH1')

    def get_ch2(self):
        return self.send_command('GetCH2')

    def get_ch3(self):
        return self.send_command('GetCH3')

    def set_d0_mode(self, param):
        return self.send_command(f'SetD0Mode {param}')

    def set_d0_pwm(self, percent):
        return self.send_command(f'SetD0PWM {percent}')

    def set_d1_mode(self, param):
        return self.send_command(f'SetD1Mode {param}')

    def set_d1_pwm(self, percent):
        return self.send_command(f'SetD1PWM {percent}')

    def set_a0_mode(self, param):
        return self.send_command(f'SetA0Mode {param}')

    def set_a0_dc_level(self, volts):
        return self.send_command(f'SetA0DCLEVEL {volts}')

    def set_a1_mode(self, param):
        return self.send_command(f'SetA1Mode {param}')

    def set_a1_dc_level(self, volts):
        return self.send_command(f'SetA1DCLEVEL {volts}')

    def set_a1_minimum(self, volts):
        return self.send_command(f'SetA1MINIMUM {volts}')

    def set_a1_maximum(self, volts):
        return self.send_command(f'SetA1MAXIMUM {volts}')

    def set_a1_steps(self, steps):
        return self.send_command(f'SetA1Steps {steps}')

    def clear_note(self):
        return self.send_command('ClearNote')

    def append_note(self, string):
        return self.send_command(f'AppendNote {string}')

    def set_cursor_current(self, time):
        if time < 0:
            capture_time = float(self.get_capture_time())
            time = capture_time + time
        return self.send_command(f'SetCursorCurrent {time}')

    def set_cursor_x1(self, time):
        if time < 0:
            capture_time = float(self.get_capture_time())
            time = capture_time + time
        return self.send_command(f'SetCursorX1 {time}')

    def set_cursor_x2(self, time):
        if time < 0:
            capture_time = float(self.get_capture_time())
            time = capture_time + time
        return self.send_command(f'SetCursorX2 {time}')

    def zoom_all(self):
        return self.send_command('ZoomAll')

    def zoom_from(self, start, end):
        return self.send_command(f'ZoomFrom {start} {end}')

    def search(self, string):
        return self.send_command(f'Search {string}')

    def show_inputs(self):
        return self.send_command('ShowInputs')

    def show_outputs(self):
        return self.send_command('ShowOutputs')

    def show_list(self):
        return self.send_command('ShowList')

    def show_settings(self):
        return self.send_command('ShowSettings')

    def show_notes(self):
        return self.send_command('ShowNotes')

    def close_tabs(self):
        return self.send_command('CloseTabs')

    def new_capture(self):
        return self.send_command('NewCapture')

    def open_capture(self, filename):
        return self.send_command(f'OpenCapture {self.get_absolute_path(filename, ".active")}')

    def save_capture(self, filename):
        return self.send_command(f'SaveCapture {self.get_absolute_path(filename, ".active")}')

    def save_between_cursors(self, filename):
        return self.send_command(f'SaveBetweenCursors {self.get_absolute_path(filename, ".active")}')

    def open_configuration(self, filename):
        return self.send_command(f'OpenConfiguration {self.get_absolute_path(filename, ".active")}')

    def save_configuration(self, filename):
        return self.send_command(f'SaveConfiguration {self.get_absolute_path(filename, ".active")}')

    def export_between_cursors(self, filename):
        return self.send_command(f'ExportBetweenCursors {self.get_absolute_path(filename, ".csv")}')

    def save_screenshot(self, filename):
        return self.send_command(f'SaveScreenshot {self.get_absolute_path(filename, ".png")}')

    def exit(self):
        return self.send_command('Exit')

    def get_absolute_path(self, path, default_extension=''):
        if default_extension and not os.path.splitext(path)[1]:
            path += default_extension
        if os.name == 'nt':
            return os.path.abspath(path)
        elif 'CYGWIN' in os.environ:
            result = subprocess.run(['cygpath', '-w', os.path.abspath(path)], capture_output=True, text=True)
            return result.stdout.strip()
        elif 'WSL_DISTRO_NAME' in os.environ:
            result = subprocess.run(['wslpath', '-w', os.path.abspath(path)], capture_output=True, text=True)
            return result.stdout.strip()
        else:
            return os.path.abspath(path)

def run_demo(api):
    api.hello()
    api.is_connected()
    api.show_inputs()
    api.show_list()
    api.show_settings()
    api.show_notes()
    api.show_outputs()
    api.close_tabs()
    api.set_d0_mode(0)
    api.set_d0_mode(1)
    api.set_d0_mode(2)
    api.set_d0_mode(3)
    api.set_d0_pwm(25)
    api.set_d0_pwm(75)
    api.set_d1_mode(0)
    api.set_d1_mode(1)
    api.set_d1_mode(2)
    api.set_d1_mode(3)
    api.set_d1_pwm(25)
    api.set_d1_pwm(75)
    api.set_a0_mode(0)
    api.set_a0_mode(1)
    api.set_a0_mode(2)
    api.set_a0_mode(3)
    api.set_a0_mode(4)
    api.set_a0_mode(5)
    api.set_a0_mode(6)
    api.set_a0_dc_level(0.5)
    api.set_a0_dc_level(1.5)
    api.set_a0_dc_level(2.5)
    api.set_a1_mode(1)
    api.set_a1_mode(2)
    api.set_a1_mode(3)
    api.set_a1_mode(4)
    api.set_a1_mode(6)
    api.set_a1_dc_level(0.5)
    api.set_a1_dc_level(1.5)
    api.set_a1_mode(7)
    api.set_a1_minimum(0.5)
    api.set_a1_maximum(2.5)
    api.set_a1_mode(8)
    api.set_a1_mode(9)
    api.set_a1_mode(10)
    api.set_a1_steps(4000)
    api.set_a1_steps(500)
    api.is_capturing()
    api.start_capture()
    api.get_logic()
    api.get_ch1()
    api.get_ch2()
    api.get_ch3()
    api.stop_capture()
    api.get_capture_size()
    api.get_capture_time()
    api.show_notes()
    api.clear_note()
    api.append_note('Sent to the Active-Pro Application.')
    api.append_note('')
    api.append_note('And here is more data.')
    api.zoom_all()
    api.zoom_from(1.0, 2.0)
    api.set_cursor_current(1)
    api.search('mon')
    api.search('booga')
    api.set_cursor_current(3)
    api.set_cursor_x1(0)
    api.set_cursor_x2(5.0)
    api.export_between_cursors('test')
    api.save_capture('testsave')
    api.save_between_cursors('testsavebetweencursors')
    api.save_configuration('testsaveconfig')
    api.open_configuration('testsaveconfig')
    api.save_screenshot('testclosed')
    api.new_capture()
    api.open_capture('testsave')
    api.exit()

def generate_bash_completion():
    completion_script = '''
_active_pro_api_completion() {
    local cur prev words cword
    _init_completion || return

    local commands=(
        --hello --is-connected --start-capture --stop-capture --is-capturing --get-capture-size --get-capture-time
        --get-logic --get-ch1 --get-ch2 --get-ch3 --set-d0-mode --set-d0-pwm --set-d1-mode --set-d1-pwm --set-a0-mode
        --set-a0-dc-level --set-a1-mode --set-a1-dc-level --set-a1-minimum --set-a1-maximum --set-a1-steps
        --clear-note --append-note --set-cursor-current --set-cursor-x1 --set-cursor-x2 --zoom-all --zoom-from
        --search --show-inputs --show-outputs --show-list --show-settings --show-notes --close-tabs --new-capture
        --open-capture --save-capture --save-between-cursors --open-configuration --save-configuration
        --export-between-cursors --save-screenshot --exit --generate-bash-completion --quiet -q
    )

    local file_commands=(
        --open-capture --save-capture --save-between-cursors --open-configuration --save-configuration
        --export-between-cursors --save-screenshot
    )

    if [[ ${#words[@]} -eq 2 ]]; then
        COMPREPLY=( $(compgen -W "${commands[*]}" -- ${cur}) )
        return 0
    elif [[ ${#words[@]} -eq 3 ]]; then
        prev=${words[1]}
        if [[ " ${file_commands[*]} " =~ " ${prev} " ]]; then
            _filedir
            return 0
        fi
    fi

    COMPREPLY=( $(compgen -W "${commands[*]}" -- ${cur}) )
    return 0
}

complete -F _active_pro_api_completion ActiveProApi.py
complete -F _active_pro_api_completion ./ActiveProApi.py
'''
    print(completion_script)

# Demonstration code
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ActivePro API Client')
    parser.add_argument('--demo', action='store_true', help='Run the demonstration code')
    parser.add_argument('--export-between-cursors', metavar='FILE', help='Export data between cursors to a file')
    parser.add_argument('--save-capture', metavar='FILE', help='Save capture to a file')
    parser.add_argument('--save-between-cursors', metavar='FILE', help='Save data between cursors to a file')
    parser.add_argument('--open-configuration', metavar='FILE', help='Open configuration from a file')
    parser.add_argument('--save-configuration', metavar='FILE', help='Save configuration to a file')
    parser.add_argument('--save-screenshot', metavar='FILE', help='Save screenshot to a file')
    parser.add_argument('--open-capture', metavar='FILE', help='Open capture from a file')
    parser.add_argument('--generate-bash-completion', action='store_true', help='Generate bash completion script.  To use, source the output of this command in your shell: source <(ActiveProApi.py --generate-bash-completion)')
    parser.add_argument('--set-d0-mode', metavar='PARAM', type=int, help='Set D0 mode')
    parser.add_argument('--set-d0-pwm', metavar='PERCENT', type=int, help='Set D0 PWM')
    parser.add_argument('--set-d1-mode', metavar='PARAM', type=int, help='Set D1 mode')
    parser.add_argument('--set-d1-pwm', metavar='PERCENT', type=int, help='Set D1 PWM')
    parser.add_argument('--set-a0-mode', metavar='PARAM', type=int, help='Set A0 mode')
    parser.add_argument('--set-a0-dc-level', metavar='VOLTS', type=float, help='Set A0 DC level')
    parser.add_argument('--set-a1-mode', metavar='PARAM', type=int, help='Set A1 mode')
    parser.add_argument('--set-a1-dc-level', metavar='VOLTS', type=float, help='Set A1 DC level')
    parser.add_argument('--set-a1-minimum', metavar='VOLTS', type=float, help='Set A1 minimum')
    parser.add_argument('--set-a1-maximum', metavar='VOLTS', type=float, help='Set A1 maximum')
    parser.add_argument('--set-a1-steps', metavar='STEPS', type=int, help='Set A1 steps')
    parser.add_argument('--append-note', metavar='STRING', help='Append note')
    parser.add_argument('--set-cursor-current', metavar='TIME', type=float, help='Set cursor current')
    parser.add_argument('--set-cursor-x1', metavar='TIME', type=float, help='Set cursor X1')
    parser.add_argument('--set-cursor-x2', metavar='TIME', type=float, help='Set cursor X2')
    parser.add_argument('--zoom-from', metavar=('START', 'END'), type=float, nargs=2, help='Zoom from start to end')
    parser.add_argument('--search', metavar='STRING', help='Search')
    parser.add_argument('--quiet', '-q', action='store_true', help='Disable verbosity')
    parser.add_argument('--get-capture-size', action='store_true', help='Get capture size')
    parser.add_argument('--get-capture-time', action='store_true', help='Get capture time')
    parser.add_argument('--get-logic', action='store_true', help='Get logic')
    parser.add_argument('--get-ch1', action='store_true', help='Get channel 1')
    parser.add_argument('--get-ch2', action='store_true', help='Get channel 2')
    parser.add_argument('--get-ch3', action='store_true', help='Get channel 3')
    args = parser.parse_args()

    if args.generate_bash_completion:
        generate_bash_completion()
        exit(0)

    # Check if at least one argument is provided
    if len(sys.argv) == 1:
        parser.print_help()
        logger.error("\nAt least one argument is needed")
        exit(1)

    try:

        api = ActiveProAPI()
        api.connect()

        if args.demo:
            run_demo(api)

        # Save old configuration first before loading configurations
        if args.save_configuration:
            api.save_configuration(args.save_configuration)

        # Arguments that impact configuration

        if args.append_note is not None:
            api.append_note(args.append_note)

        if args.set_cursor_current is not None:
            api.set_cursor_current(args.set_cursor_current)

        if args.set_cursor_x1 is not None:
            api.set_cursor_x1(args.set_cursor_x1)

        if args.set_cursor_x2 is not None:
            api.set_cursor_x2(args.set_cursor_x2)

        if args.zoom_from is not None:
            api.zoom_from(args.zoom_from[0], args.zoom_from[1])

        if args.search is not None:
            api.search(args.search)

        if args.get_capture_size:
            api.get_capture_size()

        if args.get_capture_time:
            api.get_capture_time()

        if args.get_logic:
            api.get_logic()

        if args.get_ch1:
            api.get_ch1()

        if args.get_ch2:
            api.get_ch2()

        if args.get_ch3:
            api.get_ch3()

        # Save operations first before loading configurations
        if args.save_capture:
            api.save_capture(args.save_capture)

        if args.save_between_cursors:
            api.save_between_cursors(args.save_between_cursors)

        if args.save_configuration:
            api.save_configuration(args.save_configuration)

        if args.save_screenshot:
            api.save_screenshot(args.save_screenshot)

        # Save our capture before restarting

        if args.save_capture:
            api.save_capture(args.save_capture)

        if args.save_between_cursors:
            api.save_between_cursors(args.save_between_cursors)

        if args.save_screenshot:
            api.save_screenshot(args.save_screenshot)

        if args.export_between_cursors:
            api.export_between_cursors(args.export_between_cursors)

        # Read/Open operations next
        if args.open_configuration:
            api.open_configuration(args.open_configuration)

        if args.open_capture:
            api.open_capture(args.open_capture)

        # Configuration operations
        if args.set_d0_mode is not None:
            api.set_d0_mode(args.set_d0_mode)

        if args.set_d0_pwm is not None:
            api.set_d0_pwm(args.set_d0_pwm)

        if args.set_d1_mode is not None:
            api.set_d1_mode(args.set_d1_mode)

        if args.set_d1_pwm is not None:
            api.set_d1_pwm(args.set_d1_pwm)

        if args.set_a0_mode is not None:
            api.set_a0_mode(args.set_a0_mode)

        if args.set_a0_dc_level is not None:
            api.set_a0_dc_level(args.set_a0_dc_level)

        if args.set_a1_mode is not None:
            api.set_a1_mode(args.set_a1_mode)

        if args.set_a1_dc_level is not None:
            api.set_a1_dc_level(args.set_a1_dc_level)

        if args.set_a1_minimum is not None:
            api.set_a1_minimum(args.set_a1_minimum)

        if args.set_a1_maximum is not None:
            api.set_a1_maximum(args.set_a1_maximum)

        if args.set_a1_steps is not None:
            api.set_a1_steps(args.set_a1_steps)

        api.disconnect()
    except Exception as e:
        logger.error(f"\nException: {e}")
        exit(1)
