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

# pylint: disable=too-many-lines,invalid-name

import argparse
import logging
import os
import socket
import subprocess
import sys

# Set up the logger in the root of the script
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ActiveProAPI")


class ActiveProAPI:  # pylint: disable=too-many-public-methods
    """
    A class to interact with the Active-PRO application API.
    """

    def __init__(self, host="localhost", port=37800):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.verbose = True

    def connect(self):
        """
        Connect to the Active-PRO application.
        """
        self.socket.connect((self.host, self.port))

    def disconnect(self):
        """
        Disconnect from the Active-PRO application.
        """
        self.socket.close()

    def send_command(self, command):
        """
        Send a command to the Active-PRO application.

        Args:
            command (str): The command to send.

        Returns:
            str: The response from the application.
        """
        logger.info("Command: %s", command)
        self.socket.sendall((command + "\n").encode())
        response = self.socket.recv(4096).decode().strip()
        logger.info("Response: %s", response)
        return response

    def hello(self):
        """
        Send a hello command to the Active-PRO application.

        Returns:
            str: The response from the application.
        """
        return self.send_command("Hello")

    def is_connected(self):
        """
        Check if the application is connected.

        Returns:
            str: The response from the application.
        """
        return self.send_command("isConnected")

    def start_capture(self):
        """
        Start capturing data.

        Returns:
            str: The response from the application.
        """
        return self.send_command("StartCapture")

    def stop_capture(self):
        """
        Stop capturing data.

        Returns:
            str: The response from the application.
        """
        return self.send_command("StopCapture")

    def is_capturing(self):
        """
        Check if the application is capturing data.

        Returns:
            str: The response from the application.
        """
        return self.send_command("isCapturing")

    def get_capture_size(self):
        """
        Get the size of the captured data.

        Returns:
            str: The response from the application.
        """
        return self.send_command("GetCaptureSize")

    def get_capture_time(self):
        """
        Get the capture time.

        Returns:
            str: The response from the application.
        """
        return self.send_command("GetCaptureTime")

    def get_logic(self):
        """
        Get the logic state.

        Returns:
            str: The response from the application.
        """
        return self.send_command("GetLogic")

    def get_ch1(self):
        """
        Get the state of channel 1.

        Returns:
            str: The response from the application.
        """
        return self.send_command("GetCH1")

    def get_ch2(self):
        """
        Get the state of channel 2.

        Returns:
            str: The response from the application.
        """
        return self.send_command("GetCH2")

    def get_ch3(self):
        """
        Get the state of channel 3.

        Returns:
            str: The response from the application.
        """
        return self.send_command("GetCH3")

    def set_d0_mode(self, param):
        """
        Set the mode of D0.

        Args:
            param (int): The mode to set.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"SetD0Mode {param}")

    def set_d0_pwm(self, percent):
        """
        Set the PWM of D0.

        Args:
            percent (int): The PWM percentage to set.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"SetD0PWM {percent}")

    def set_d1_mode(self, param):
        """
        Set the mode of D1.

        Args:
            param (int): The mode to set.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"SetD1Mode {param}")

    def set_d1_pwm(self, percent):
        """
        Set the PWM of D1.

        Args:
            percent (int): The PWM percentage to set.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"SetD1PWM {percent}")

    def set_a0_mode(self, param):
        """
        Set the mode of A0.

        Args:
            param (int): The mode to set.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"SetA0Mode {param}")

    def set_a0_dc_level(self, volts):
        """
        Set the DC level of A0.

        Args:
            volts (float): The voltage level to set.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"SetA0DCLEVEL {volts}")

    def set_a1_mode(self, param):
        """
        Set the mode of A1.

        Args:
            param (int): The mode to set.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"SetA1Mode {param}")

    def set_a1_dc_level(self, volts):
        """
        Set the DC level of A1.

        Args:
            volts (float): The voltage level to set.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"SetA1DCLEVEL {volts}")

    def set_a1_minimum(self, volts):
        """
        Set the minimum voltage of A1.

        Args:
            volts (float): The minimum voltage to set.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"SetA1MINIMUM {volts}")

    def set_a1_maximum(self, volts):
        """
        Set the maximum voltage of A1.

        Args:
            volts (float): The maximum voltage to set.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"SetA1MAXIMUM {volts}")

    def set_a1_steps(self, steps):
        """
        Set the steps of A1.

        Args:
            steps (int): The number of steps to set.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"SetA1Steps {steps}")

    def clear_note(self):
        """
        Clear the note.

        Returns:
            str: The response from the application.
        """
        return self.send_command("ClearNote")

    def append_note(self, string):
        """
        Append a note.

        Args:
            string (str): The note to append.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"AppendNote {string}")

    def set_cursor_current(self, time):
        """
        Set the current cursor position.

        Args:
            time (float): The time to set the cursor to.

        Returns:
            str: The response from the application.
        """
        if time < 0:
            capture_time = float(self.get_capture_time())
            time = capture_time + time
        return self.send_command(f"SetCursorCurrent {time}")

    def set_cursor_x1(self, time):
        """
        Set the X1 cursor position.

        Args:
            time (float): The time to set the cursor to.

        Returns:
            str: The response from the application.
        """
        if time < 0:
            capture_time = float(self.get_capture_time())
            time = capture_time + time
        return self.send_command(f"SetCursorX1 {time}")

    def set_cursor_x2(self, time):
        """
        Set the X2 cursor position.

        Args:
            time (float): The time to set the cursor to.

        Returns:
            str: The response from the application.
        """
        if time < 0:
            capture_time = float(self.get_capture_time())
            time = capture_time + time
        return self.send_command(f"SetCursorX2 {time}")

    def zoom_all(self):
        """
        Zoom to show all data.

        Returns:
            str: The response from the application.
        """
        return self.send_command("ZoomAll")

    def zoom_from(self, start, end):
        """
        Zoom from a start time to an end time.

        Args:
            start (float): The start time.
            end (float): The end time.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"ZoomFrom {start} {end}")

    def search(self, string):
        """
        Search for a string in the data.

        Args:
            string (str): The string to search for.

        Returns:
            str: The response from the application.
        """
        return self.send_command(f"Search {string}")

    def show_inputs(self):
        """
        Show the inputs.

        Returns:
            str: The response from the application.
        """
        return self.send_command("ShowInputs")

    def show_outputs(self):
        """
        Show the outputs.

        Returns:
            str: The response from the application.
        """
        return self.send_command("ShowOutputs")

    def show_list(self):
        """
        Show the list.

        Returns:
            str: The response from the application.
        """
        return self.send_command("ShowList")

    def show_settings(self):
        """
        Show the settings.

        Returns:
            str: The response from the application.
        """
        return self.send_command("ShowSettings")

    def show_notes(self):
        """
        Show the notes.

        Returns:
            str: The response from the application.
        """
        return self.send_command("ShowNotes")

    def close_tabs(self):
        """
        Close the tabs.

        Returns:
            str: The response from the application.
        """
        return self.send_command("CloseTabs")

    def new_capture(self):
        """
        Start a new capture.

        Returns:
            str: The response from the application.
        """
        return self.send_command("NewCapture")

    def open_capture(self, filename):
        """
        Open a capture file.

        Args:
            filename (str): The name of the capture file.

        Returns:
            str: The response from the application.
        """
        return self.send_command(
            f'OpenCapture {self.get_absolute_path(filename, ".active")}'
        )

    def save_capture(self, filename):
        """
        Save the capture to a file.

        Args:
            filename (str): The name of the file to save to.

        Returns:
            str: The response from the application.
        """
        return self.send_command(
            f'SaveCapture {self.get_absolute_path(filename, ".active")}'
        )

    def save_between_cursors(self, filename):
        """
        Save the data between the cursors to a file.

        Args:
            filename (str): The name of the file to save to.

        Returns:
            str: The response from the application.
        """
        return self.send_command(
            f'SaveBetweenCursors {self.get_absolute_path(filename, ".active")}'
        )

    def open_configuration(self, filename):
        """
        Open a configuration file.

        Args:
            filename (str): The name of the configuration file.

        Returns:
            str: The response from the application.
        """
        return self.send_command(
            f'OpenConfiguration {self.get_absolute_path(filename, ".active")}'
        )

    def save_configuration(self, filename):
        """
        Save the configuration to a file.

        Args:
            filename (str): The name of the file to save to.

        Returns:
            str: The response from the application.
        """
        return self.send_command(
            f'SaveConfiguration {self.get_absolute_path(filename, ".active")}'
        )

    def export_between_cursors(self, filename):
        """
        Export the data between the cursors to a file.

        Args:
            filename (str): The name of the file to export to.

        Returns:
            str: The response from the application.
        """
        return self.send_command(
            f'ExportBetweenCursors {self.get_absolute_path(filename, ".csv")}'
        )

    def save_screenshot(self, filename):
        """
        Save a screenshot to a file.

        Args:
            filename (str): The name of the file to save to.

        Returns:
            str: The response from the application.
        """
        return self.send_command(
            f'SaveScreenshot {self.get_absolute_path(filename, ".png")}'
        )

    def exit(self):
        """
        Exit the application.

        Returns:
            str: The response from the application.
        """
        return self.send_command("Exit")

    def get_absolute_path(self, path, default_extension=""):
        """
        Get the absolute path of a file.

        Args:
            path (str): The path to the file.
            default_extension (str): The default file extension.

        Returns:
            str: The absolute path of the file.
        """
        if default_extension and not os.path.splitext(path)[1]:
            path += default_extension
        if os.name == "nt":
            return os.path.abspath(path)
        if "CYGWIN" in os.environ:
            result = subprocess.run(
                ["cygpath", "-w", os.path.abspath(path)],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        if "WSL_DISTRO_NAME" in os.environ:
            result = subprocess.run(
                ["wslpath", "-w", os.path.abspath(path)],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        return os.path.abspath(path)


def run_demo(api_instance):  # pylint: disable=too-many-statements
    """
    Run a demonstration of the API.

    Args:
        api_instance (ActiveProAPI): An instance of the ActiveProAPI class.
    """
    api_instance.hello()
    api_instance.is_connected()
    api_instance.show_inputs()
    api_instance.show_list()
    api_instance.show_settings()
    api_instance.show_notes()
    api_instance.show_outputs()
    api_instance.close_tabs()
    api_instance.set_d0_mode(0)
    api_instance.set_d0_mode(1)
    api_instance.set_d0_mode(2)
    api_instance.set_d0_mode(3)
    api_instance.set_d0_pwm(25)
    api_instance.set_d0_pwm(75)
    api_instance.set_d1_mode(0)
    api_instance.set_d1_mode(1)
    api_instance.set_d1_mode(2)
    api_instance.set_d1_mode(3)
    api_instance.set_d1_pwm(25)
    api_instance.set_d1_pwm(75)
    api_instance.set_a0_mode(0)
    api_instance.set_a0_mode(1)
    api_instance.set_a0_mode(2)
    api_instance.set_a0_mode(3)
    api_instance.set_a0_mode(4)
    api_instance.set_a0_mode(5)
    api_instance.set_a0_mode(6)
    api_instance.set_a0_dc_level(0.5)
    api_instance.set_a0_dc_level(1.5)
    api_instance.set_a0_dc_level(2.5)
    api_instance.set_a1_mode(1)
    api_instance.set_a1_mode(2)
    api_instance.set_a1_mode(3)
    api_instance.set_a1_mode(4)
    api_instance.set_a1_mode(6)
    api_instance.set_a1_dc_level(0.5)
    api_instance.set_a1_dc_level(1.5)
    api_instance.set_a1_mode(7)
    api_instance.set_a1_minimum(0.5)
    api_instance.set_a1_maximum(2.5)
    api_instance.set_a1_mode(8)
    api_instance.set_a1_mode(9)
    api_instance.set_a1_mode(10)
    api_instance.set_a1_steps(4000)
    api_instance.set_a1_steps(500)
    api_instance.is_capturing()
    api_instance.start_capture()
    api_instance.get_logic()
    api_instance.get_ch1()
    api_instance.get_ch2()
    api_instance.get_ch3()
    api_instance.stop_capture()
    api_instance.get_capture_size()
    api_instance.get_capture_time()
    api_instance.show_notes()
    api_instance.clear_note()
    api_instance.append_note("Sent to the Active-Pro Application.")
    api_instance.append_note("")
    api_instance.append_note("And here is more data.")
    api_instance.zoom_all()
    api_instance.zoom_from(1.0, 2.0)
    api_instance.set_cursor_current(1)
    api_instance.search("mon")
    api_instance.search("booga")
    api_instance.set_cursor_current(3)
    api_instance.set_cursor_x1(0)
    api_instance.set_cursor_x2(5.0)
    api_instance.export_between_cursors("test")
    api_instance.save_capture("testsave")
    api_instance.save_between_cursors("testsavebetweencursors")
    api_instance.save_configuration("testsaveconfig")
    api_instance.open_configuration("testsaveconfig")
    api_instance.save_screenshot("testclosed")
    api_instance.new_capture()
    api_instance.open_capture("testsave")
    api_instance.exit()


def generate_bash_completion(argparser):
    """
    Generate a bash completion script for the API.
    """
    script_name = os.path.basename(__file__)
    script_path = os.path.abspath(__file__)

    commands = []
    file_commands = []

    for action in argparser._actions:  # pylint: disable=protected-access
        if action.option_strings:
            command = " ".join(action.option_strings)
            if action.nargs == 0:
                commands.append(command)
            elif action.nargs == 1:
                commands.append(f"{command} VALUE")
            elif action.nargs == 2:
                commands.append(f"{command} VALUE1 VALUE2")
            if (
                action.metavar
                and isinstance(action.metavar, str)
                and action.metavar.endswith("FILE")
            ):
                file_commands.append(command)

    completion_script = f"""
_active_pro_api_completion() {{
    local cur prev words cword
    _init_completion || return

    local commands=(
        {" ".join(commands)}
    )

    local file_commands=(
        {" ".join(file_commands)}
    )

    if [[ ${{#words[@]}} -eq 2 ]]; then
        COMPREPLY=( $(compgen -W "${{commands[*]}}" -- ${{cur}}) )
        return 0
    elif [[ ${{#words[@]}} -eq 3 ]]; then
        prev=${{words[1]}}
        if [[ " ${{file_commands[*]}} " =~ " ${{prev}} " ]]; then
            _filedir
            return 0
        fi
    elif [[ ${{#words[@]}} -eq 4 ]]; then
        prev=${{words[1]}}
        if [[ " ${{commands[*]}} " =~ " ${{prev}} " ]]; then
            COMPREPLY=( $(compgen -W "VALUE1 VALUE2" -- ${{cur}}) )
            return 0
        fi
    fi

    COMPREPLY=( $(compgen -W "${{commands[*]}}" -- ${{cur}}) )
    return 0
}}

complete -F _active_pro_api_completion {script_name}
complete -F _active_pro_api_completion ./{script_name}
complete -F _active_pro_api_completion {script_path}
"""
    print(completion_script)


# Demonstration code
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ActivePro API Client")
    parser.add_argument(
        "--demo", action="store_true", help="Run the demonstration code"
    )
    parser.add_argument(
        "--export-between-cursors",
        metavar="FILE",
        help="Export data between cursors to a file",
    )
    parser.add_argument(
        "--save-capture", metavar="FILE", help="Save capture to a file"
    )
    parser.add_argument(
        "--save-between-cursors",
        metavar="FILE",
        help="Save data between cursors to a file",
    )
    parser.add_argument(
        "--open-configuration",
        metavar="FILE",
        help="Open configuration from a file",
    )
    parser.add_argument(
        "--save-configuration",
        metavar="FILE",
        help="Save configuration to a file",
    )
    parser.add_argument(
        "--save-screenshot", metavar="FILE", help="Save screenshot to a file"
    )
    parser.add_argument(
        "--open-capture", metavar="FILE", help="Open capture from a file"
    )
    parser.add_argument(
        "--generate-bash-completion",
        action="store_true",
        help=f"Generate bash completion script. To use, source the output of "
        f"this command in your shell: source <({sys.argv[0]} "
        "--generate-bash-completion)",
    )
    parser.add_argument(
        "--set-d0-mode", metavar="PARAM", type=int, help="Set D0 mode"
    )
    parser.add_argument(
        "--set-d0-pwm", metavar="PERCENT", type=int, help="Set D0 PWM"
    )
    parser.add_argument(
        "--set-d1-mode", metavar="PARAM", type=int, help="Set D1 mode"
    )
    parser.add_argument(
        "--set-d1-pwm", metavar="PERCENT", type=int, help="Set D1 PWM"
    )
    parser.add_argument(
        "--set-a0-mode", metavar="PARAM", type=int, help="Set A0 mode"
    )
    parser.add_argument(
        "--set-a0-dc-level",
        metavar="VOLTS",
        type=float,
        help="Set A0 DC level",
    )
    parser.add_argument(
        "--set-a1-mode", metavar="PARAM", type=int, help="Set A1 mode"
    )
    parser.add_argument(
        "--set-a1-dc-level",
        metavar="VOLTS",
        type=float,
        help="Set A1 DC level",
    )
    parser.add_argument(
        "--set-a1-minimum", metavar="VOLTS", type=float, help="Set A1 minimum"
    )
    parser.add_argument(
        "--set-a1-maximum", metavar="VOLTS", type=float, help="Set A1 maximum"
    )
    parser.add_argument(
        "--set-a1-steps", metavar="STEPS", type=int, help="Set A1 steps"
    )
    parser.add_argument("--append-note", metavar="STRING", help="Append note")
    parser.add_argument(
        "--set-cursor-current",
        metavar="TIME",
        type=float,
        help="Set cursor current",
    )
    parser.add_argument(
        "--set-cursor-x1", metavar="TIME", type=float, help="Set cursor X1"
    )
    parser.add_argument(
        "--set-cursor-x2", metavar="TIME", type=float, help="Set cursor X2"
    )
    parser.add_argument(
        "--zoom-from",
        metavar=("START", "END"),
        type=float,
        nargs=2,
        help="Zoom from start to end",
    )
    parser.add_argument("--search", metavar="STRING", help="Search")
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Disable verbosity"
    )
    parser.add_argument(
        "--get-capture-size", action="store_true", help="Get capture size"
    )
    parser.add_argument(
        "--get-capture-time", action="store_true", help="Get capture time"
    )
    parser.add_argument("--get-logic", action="store_true", help="Get logic")
    parser.add_argument("--get-ch1", action="store_true", help="Get channel 1")
    parser.add_argument("--get-ch2", action="store_true", help="Get channel 2")
    parser.add_argument("--get-ch3", action="store_true", help="Get channel 3")
    parser.add_argument(
        "--hello", action="store_true", help="Send hello command"
    )
    parser.add_argument(
        "--is-connected", action="store_true", help="Check if connected"
    )
    parser.add_argument(
        "--start-capture", action="store_true", help="Start capture"
    )
    parser.add_argument(
        "--stop-capture", action="store_true", help="Stop capture"
    )
    parser.add_argument(
        "--is-capturing", action="store_true", help="Check if capturing"
    )
    parser.add_argument("--clear-note", action="store_true", help="Clear note")
    parser.add_argument("--zoom-all", action="store_true", help="Zoom all")
    parser.add_argument(
        "--show-inputs", action="store_true", help="Show inputs"
    )
    parser.add_argument(
        "--show-outputs", action="store_true", help="Show outputs"
    )
    parser.add_argument("--show-list", action="store_true", help="Show list")
    parser.add_argument(
        "--show-settings", action="store_true", help="Show settings"
    )
    parser.add_argument("--show-notes", action="store_true", help="Show notes")
    parser.add_argument("--close-tabs", action="store_true", help="Close tabs")
    parser.add_argument(
        "--new-capture", action="store_true", help="New capture"
    )
    parser.add_argument("--exit", action="store_true", help="Exit")
    args = parser.parse_args()

    if args.generate_bash_completion:
        generate_bash_completion(parser)
        sys.exit(0)

    # Check if at least one argument is provided
    if len(sys.argv) == 1:
        parser.print_help()
        logger.error("\nAt least one argument is needed")
        sys.exit(1)

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

        if args.hello:
            api.hello()

        if args.is_connected:
            api.is_connected()

        if args.start_capture:
            api.start_capture()

        if args.stop_capture:
            api.stop_capture()

        if args.is_capturing:
            api.is_capturing()

        if args.clear_note:
            api.clear_note()

        if args.zoom_all:
            api.zoom_all()

        if args.show_inputs:
            api.show_inputs()

        if args.show_outputs:
            api.show_outputs()

        if args.show_list:
            api.show_list()

        if args.show_settings:
            api.show_settings()

        if args.show_notes:
            api.show_notes()

        if args.close_tabs:
            api.close_tabs()

        if args.new_capture:
            api.new_capture()

        if args.exit:
            api.exit()

        api.disconnect()
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("\nException: %s", e)
        sys.exit(1)
