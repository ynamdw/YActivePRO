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
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum


class VerboseLevel(Enum):
    """
    Enum for verbose levels.
    """

    NONE = 0
    RESULT = 1
    INFO = 2


class CustomFormatter(logging.Formatter):
    """
    Custom formatter for logging messages.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def format(self, record):
        # Access to a protected member _fmt of a client class
        # pylint: disable=protected-access
        if record.levelno == logging.INFO:
            self._style._fmt = "%(message)s"
        else:
            self._style._fmt = "%(levelname)s: %(message)s"

        return super().format(record)


# Set up the logger in the root of the script
logger = logging.getLogger("ActiveProAPI")
logger.setLevel(logging.INFO)

# Create a console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# Create the custom formatter
formatter = CustomFormatter()

# Set the formatter for the handler
ch.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(ch)


class ActiveProAPI:  # pylint: disable=too-many-public-methods
    """
    A class to interact with the Active-PRO application API.
    """

    def __init__(
        self, host="localhost", port=37800, verbose=VerboseLevel.INFO
    ):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.verbose = verbose

    def connect(self):
        """
        Connect to the Active-PRO application.
        """
        if self.verbose == VerboseLevel.INFO:
            api_id = self.port - 37800 + 1
            logger.info(
                "Connecting to ID: %d - %s:%d", api_id, self.host, self.port
            )
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
        if self.verbose == VerboseLevel.INFO:
            logger.info("Command: '%s'", command)

        self.socket.sendall((command + "\n").encode())
        response = self.socket.recv(4096).decode().strip()

        if self.verbose == VerboseLevel.INFO:
            logger.info("Response: '%s'", response)
        elif self.verbose == VerboseLevel.RESULT:
            print(f"{response}{os.linesep}")
        return response

    def find_available_ports(self):
        """
        Find available ports in the range 37800 to 37810.

        Returns:
            dict: A dictionary with keys as IDs and values as port numbers.
        """
        available_ports_dict = {}

        def check_port(available_port):
            try:
                logger.log(
                    logging.DEBUG, "Try %s:%d", self.host, available_port
                )
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.050)
                    if s.connect_ex((self.host, available_port)) == 0:
                        return available_port
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.log(logging.ERROR, "Exception: %s", e)
            return None

        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(check_port, available_port): available_port
                for available_port in range(37800, 37811)
            }
            for future in as_completed(futures):
                available_port = future.result()
                if available_port:
                    available_id = available_port - 37800 + 1
                    available_ports_dict[available_id] = available_port

        return available_ports_dict

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
            bool: True if capturing, False otherwise.
        """
        response = self.send_command("isCapturing")
        return response.lower() != "yes"

    def is_not_capturing(self):
        """
        Check if the application is not capturing data.

        Returns:
            bool: True if not capturing, False otherwise.
        """
        response = self.send_command("isCapturing")
        return response.lower() == "no"

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
            time = max(capture_time + time, 0)
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
            time = max(capture_time + time, 0)
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
            time = max(capture_time + time, 0)
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
        start = float(start)
        end = float(end)
        if start < 0 or end < 0:
            capture_time = float(self.get_capture_time())
            if start < 0:
                start = max(capture_time + start, 0)
            if end < 0:
                end = max(capture_time + end, 0)
        if end < start:
            (start, end) = (end, start)
        if start == end:
            if start == 0:
                capture_time = float(self.get_capture_time())
                end = min(0.001, capture_time)
            else:
                start = max(end - 0.001, 0)
        return self.send_command(f"ZoomFrom {start} {end}")

    def zoom_cursors(self):
        """
        Zoom between the X1 and X2 cursors.
        (Wishful thinking, not implemented)

        Returns:
            str: The response from the application (zoom_from).
        """
        x1 = self.send_command("GetCursorX1")
        if x1.startswith("ERROR"):
            logger.log(logging.ERROR, "Error: %s", x1)
            return x1
        x1 = float(x1)
        x2 = self.send_command("GetCursorX2")
        if x2.startswith("ERROR"):
            logger.log(logging.ERROR, "Error: %s", x2)
            return x2
        x2 = float(x2)
        return self.zoom_from(x1, x2)

    def search(self, string):
        """
        Search for a string in the data.

        Args:
            string (str): The string to search for.

        Returns:
            str: The timestamp of the search result or "NOTFOUND".
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
        if self.is_capturing():
            self.stop_capture()
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
            str: The response from the application ("NOTSTOPPED", FILENAME).
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

    def convert_a0_mode(self, a0_mode):
        """
        Convert textual A0 mode to numerical value.

        Args:
            a0_mode (str or int): The mode to convert.

        Returns:
            int: The numerical value of the mode.
        """
        mode_map = {
            "tristate": 0,
            "0v": 1,
            "1v": 2,
            "2v": 3,
            "3v": 4,
            "3.3v": 5,
            "dc": 6,
        }
        if isinstance(a0_mode, str):
            a0_mode = a0_mode.lower()
            if a0_mode in mode_map:
                return mode_map[a0_mode]
            raise ValueError(f"Invalid A0 mode: {a0_mode}")
        return a0_mode

    def convert_a1_mode(self, a1_mode):
        """
        Convert textual A1 mode to numerical value.

        Args:
            a1_mode (str or int): The mode to convert.

        Returns:
            int: The numerical value of the mode.
        """
        mode_map = {
            "tristate": 0,
            "0v": 1,
            "1v": 2,
            "2v": 3,
            "3v": 4,
            "3.3v": 5,
            "dc": 6,
            "ramp": 7,
            "sine": 8,
            "square": 9,
            "triangle": 10,
        }
        if isinstance(a1_mode, str):
            a1_mode = a1_mode.lower()
            if a1_mode in mode_map:
                return mode_map[a1_mode]
            raise ValueError(f"Invalid A1 mode: {a1_mode}")
        return a1_mode

    def convert_d0_mode(self, d0_mode):
        """
        Convert textual D0 mode to numerical value.

        Args:
            d0_mode (str or int): The mode to convert.

        Returns:
            int: The numerical value of the mode.
        """
        mode_map = {"tristate": 0, "0v": 1, "3.3v": 2, "pwm": 3}
        if isinstance(d0_mode, str):
            d0_mode = d0_mode.lower()
            if d0_mode in mode_map:
                return mode_map[d0_mode]
            raise ValueError(f"Invalid D0 mode: {d0_mode}")
        return d0_mode

    def convert_d1_mode(self, d1_mode):
        """
        Convert textual D1 mode to numerical value.

        Args:
            d1_mode (str or int): The mode to convert.

        Returns:
            int: The numerical value of the mode.
        """
        mode_map = {"tristate": 0, "0v": 1, "3.3v": 2, "pwm": 3}
        if isinstance(d1_mode, str):
            d1_mode = d1_mode.lower()
            if d1_mode in mode_map:
                return mode_map[d1_mode]
            raise ValueError(f"Invalid D1 mode: {d1_mode}")
        return d1_mode


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


# pylint: disable=too-many-branches,too-many-locals
def generate_bash_completion(argparser):
    """
    Generate a bash completion script for the API.
    """
    script_name = os.path.basename(__file__)
    script_path = os.path.abspath(__file__)

    commands = []
    one_arg_commands = []
    two_arg_commands = []
    file_commands = {}
    choice_commands = {}

    for action in argparser._actions:  # pylint: disable=protected-access
        if action.option_strings:
            command = " ".join(action.option_strings)

            # For debug:
            # if command == "--host":
            #    print(f"# {command}-{action}")

            # Determine nargs based on the given conditions
            if action.nargs is not None:
                nargs = action.nargs
            elif action.metavar is None:
                if action.type is not None:
                    nargs = 1
                else:
                    nargs = 0
            elif isinstance(action.metavar, str):
                nargs = 1
            elif isinstance(action.metavar, list):
                nargs = len(action.metavar)
            else:
                nargs = 0  # Default case if none of the conditions match

            if nargs == 0:
                commands.append(command)
            elif nargs == 1 or (
                isinstance(action.metavar, str)
                and not action.metavar.endswith("FILE")
            ):
                one_arg_commands.append(f"{command}")
            elif nargs == 2:
                two_arg_commands.append(f"{command}")

            if (
                action.metavar
                and isinstance(action.metavar, str)
                and action.metavar.endswith("FILE")
            ):
                file_commands[command] = action.metavar

            if action.choices:
                choice_commands[command] = action.choices

    MAP_OPT_TO_EXTENSION = {
        "--export-between-cursors": "csv",
        "--save-capture": "active",
        "--save-between-cursors": "active",
        "--open-configuration": "active",
        "--save-configuration": "active",
        "--save-screenshot": "png",
        "--open-capture": "active",
    }

    file_commands = {
        cmd: MAP_OPT_TO_EXTENSION.get(cmd, "") for cmd in file_commands
    }

    extension_cases = " ".join(
        [f"{cmd} ) ext={ext} ;;\n" for cmd, ext in file_commands.items()]
    )

    possible_ports = " ".join([str(port) for port in range(37800, 37810)])

    # Generate the code for the options with choices
    choice_commands_str = "\n".join(
        [
            f'{cmd}) COMPREPLY=( $(compgen -W "'
            f"{' '.join(choices)}"
            '" -- ${{cur}}) );;'
            for cmd, choices in choice_commands.items()
        ]
    )

    completion_script = f"""
_active_pro_api_completion() {{
    local cur prev words cword
    _init_completion || return

    local commands=(
        {" ".join(commands)}
        {" ".join(one_arg_commands)}
        {" ".join(two_arg_commands)}
    )

    local one_arg_commands=(
        {" ".join(one_arg_commands)}
    )

    local two_arg_commands=(
        {" ".join(two_arg_commands)}
    )

    local file_commands=(
        {" ".join(file_commands.keys())}
    )

    local choice_commands=(
        {" ".join(choice_commands.keys())}
    )

    if [[ ${{#words[@]}} -ge 4 ]]; then
        prev=${{words[-3]}}
        if [[ " ${{two_arg_commands[*]}} " =~ " ${{prev}} " ]]; then
            # COMPREPLY=( "Enter VALUE2" )
            return 0
        fi
    fi
    if [[ ${{#words[@]}} -ge 3 ]]; then
        prev=${{words[-2]}}

        case "$prev" in
            {choice_commands_str}
        esac

        if [[ " ${{file_commands[*]}} " =~ " ${{prev}} " ]]; then
            local ext
            case ${{prev}} in
                {extension_cases}
            esac
            _filedir '@('${{ext}}')'
            return 0
        fi
        if [[ " ${{one_arg_commands[*]}} " =~ " ${{prev}} " ]]; then
            if [[ " ${{prev}} " == " --id " ]]; then
                COMPREPLY=( $(compgen -W "-1 1 2 3 4 5 6 7 8 9" -- ${{cur}}) )
                return 0
            elif [[ " ${{prev}} " == " --port " ]]; then
                COMPREPLY=( $(compgen -W "{possible_ports}" -- ${{cur}}) )
                return 0
            elif [[ " ${{prev}} " == " --host " ]]; then
                _known_hosts_real -- "${{cur}}"
                return 0
            else
                # COMPREPLY=( "Enter VALUE" )
                return 0
            fi
        fi
        if [[ " ${{two_arg_commands[*]}} " =~ " ${{prev}} " ]]; then
            # COMPREPLY=( "Enter VALUE1" )
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
        "--set-d0-mode",
        metavar="PARAM",
        type=str.upper,  # Convert input to uppercase
        choices=["0", "1", "2", "3", "TRISTATE", "0V", "3.3V", "PWM"],
        help="Set D0 mode (0=TRISTATE, 1=0V, 2=3.3V, 3=PWM)",
    )
    parser.add_argument(
        "--set-d0-pwm", metavar="PERCENT", type=int, help="Set D0 PWM"
    )
    parser.add_argument(
        "--set-d1-mode",
        metavar="PARAM",
        type=str.upper,  # Convert input to uppercase
        choices=["0", "1", "2", "3", "TRISTATE", "0V", "3.3V", "PWM"],
        help="Set D1 mode (0=TRISTATE, 1=0V, 2=3.3V, 3=PWM)",
    )
    parser.add_argument(
        "--set-d1-pwm", metavar="PERCENT", type=int, help="Set D1 PWM"
    )
    parser.add_argument(
        "--set-a0-mode",
        metavar="PARAM",
        type=str,
        choices=[
            "0",
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "TRISTATE",
            "0V",
            "1V",
            "2V",
            "3V",
            "3.3V",
            "DC",
        ],
        help="Set A0 mode (0=TRISTATE, 1=0V, 2=1V, 3=2V, 4=3V, 5=3.3V, 6=DC)",
    )
    parser.add_argument(
        "--set-a0-dc-level",
        metavar="VOLTS",
        type=float,
        help="Set A0 DC level",
    )
    parser.add_argument(
        "--set-a1-mode",
        metavar="PARAM",
        type=str,
        choices=[
            "0",
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "9",
            "10",
            "TRISTATE",
            "0V",
            "1V",
            "2V",
            "3V",
            "3.3V",
            "DC",
            "RAMP",
            "SINE",
            "SQUARE",
            "TRIANGLE",
        ],
        help=(
            "Set A1 mode (0=TRISTATE, 1=0V, 2=1V, 3=2V, 4=3V, 5=3.3V, 6=DC, "
            "7=RAMP, 8=SINE, 9=SQUARE, 10=TRIANGLE)"
        ),
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
    parser.add_argument(
        "--zoom-range",
        metavar=("START", "END"),
        type=float,
        nargs=2,
        help="Zoom from start to end (same as --zoom-from)",
    )
    # Not implemented, so commented
    # parser.add_argument(
    #    "--zoom-cursors",
    #    action="store_true",
    #    help="Zoom between the X1 and X2 cursors",
    # )
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
    parser.add_argument(
        "--not-capturing",
        action="store_true",
        help="Exit immediately if the session is capturing",
    )
    parser.add_argument("--port", type=int, help="Set the port number")
    parser.add_argument(
        "--id",
        type=int,
        help="Select ActiveProDebugger based on 'id'. Use -1 to auto-detect.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Set the host address (default is 'localhost')",
    )
    parsed_args = parser.parse_args()

    if parsed_args.generate_bash_completion:
        generate_bash_completion(parser)
        sys.exit(0)

    # Check if at least one argument is provided
    if len(sys.argv) == 1:
        parser.print_help()
        logger.log(logging.ERROR, "At least one argument is needed")
        sys.exit(1)

    try:
        # Instantiate api outside of the conditional blocks
        api = ActiveProAPI(
            host=parsed_args.host,
            verbose=(
                VerboseLevel.RESULT if parsed_args.quiet else VerboseLevel.INFO
            ),
        )

        if parsed_args.id is not None and parsed_args.port is not None:
            logger.log(
                logging.ERROR,
                "Error: --id and --port cannot be used simultaneously.",
            )
            sys.exit(1)

        if parsed_args.id is not None:
            if parsed_args.id == -1:
                available_ports = api.find_available_ports()
                if not available_ports:
                    logger.log(
                        logging.ERROR, "Error: No available ports found."
                    )
                    sys.exit(1)
                selected_port = max(available_ports.values())
                api = ActiveProAPI(
                    host=parsed_args.host,
                    port=selected_port,
                    verbose=(
                        VerboseLevel.RESULT
                        if parsed_args.quiet
                        else VerboseLevel.INFO
                    ),
                )
            else:
                selected_port = 37800 + parsed_args.id - 1
                api = ActiveProAPI(
                    host=parsed_args.host,
                    port=selected_port,
                    verbose=(
                        VerboseLevel.RESULT
                        if parsed_args.quiet
                        else VerboseLevel.INFO
                    ),
                )
        elif parsed_args.port is not None:
            api = ActiveProAPI(
                host=parsed_args.host,
                port=parsed_args.port,
                verbose=(
                    VerboseLevel.RESULT
                    if parsed_args.quiet
                    else VerboseLevel.INFO
                ),
            )

        api.connect()

        if parsed_args.not_capturing:
            if api.is_capturing():
                logger.log(logging.INFO, "Session is capturing. Exiting.")
                sys.exit(0)

        if parsed_args.demo:
            run_demo(api)

        # Save old configuration first before loading configurations
        if parsed_args.save_configuration:
            api.save_configuration(parsed_args.save_configuration)

        # Arguments that impact configuration

        if parsed_args.append_note is not None:
            api.append_note(parsed_args.append_note)

        if parsed_args.set_cursor_current is not None:
            api.set_cursor_current(parsed_args.set_cursor_current)

        if parsed_args.set_cursor_x1 is not None:
            api.set_cursor_x1(parsed_args.set_cursor_x1)

        if parsed_args.set_cursor_x2 is not None:
            api.set_cursor_x2(parsed_args.set_cursor_x2)

        if parsed_args.zoom_from is not None:
            api.zoom_from(parsed_args.zoom_from[0], parsed_args.zoom_from[1])

        if parsed_args.zoom_range is not None:
            api.zoom_from(parsed_args.zoom_range[0], parsed_args.zoom_range[1])

        # Can't read position of cursors, so can't zoom to cursors
        # if parsed_args.zoom_cursors:
        #     api.zoom_cursors()

        if parsed_args.search is not None:
            api.search(parsed_args.search)

        if parsed_args.get_capture_size:
            api.get_capture_size()

        if parsed_args.get_capture_time:
            api.get_capture_time()

        if parsed_args.get_logic:
            api.get_logic()

        if parsed_args.get_ch1:
            api.get_ch1()

        if parsed_args.get_ch2:
            api.get_ch2()

        if parsed_args.get_ch3:
            api.get_ch3()

        # Save operations first before loading configurations or restart
        if parsed_args.save_capture:
            api.save_capture(parsed_args.save_capture)

        if parsed_args.save_between_cursors:
            api.save_between_cursors(parsed_args.save_between_cursors)

        if parsed_args.export_between_cursors:
            api.export_between_cursors(parsed_args.export_between_cursors)

        if parsed_args.save_configuration:
            api.save_configuration(parsed_args.save_configuration)

        if parsed_args.save_screenshot:
            api.save_screenshot(parsed_args.save_screenshot)

        # Read/Open operations next
        if parsed_args.open_configuration:
            api.open_configuration(parsed_args.open_configuration)

        if parsed_args.open_capture:
            api.open_capture(parsed_args.open_capture)

        # Configuration operations
        if parsed_args.set_d0_mode is not None:
            try:
                mode = api.convert_d0_mode(parsed_args.set_d0_mode)
                api.set_d0_mode(mode)
            except ValueError as e:
                logger.log(logging.ERROR, str(e))
                sys.exit(1)

        if parsed_args.set_d0_pwm is not None:
            api.set_d0_pwm(parsed_args.set_d0_pwm)

        if parsed_args.set_d1_mode is not None:
            try:
                mode = api.convert_d1_mode(parsed_args.set_d1_mode)
                api.set_d1_mode(mode)
            except ValueError as e:
                logger.log(logging.ERROR, str(e))
                sys.exit(1)

        if parsed_args.set_d1_pwm is not None:
            api.set_d1_pwm(parsed_args.set_d1_pwm)

        if parsed_args.set_a0_mode is not None:
            try:
                mode = api.convert_a0_mode(parsed_args.set_a0_mode)
                api.set_a0_mode(mode)
            except ValueError as e:
                logger.log(logging.ERROR, str(e))
                sys.exit(1)

        if parsed_args.set_a0_dc_level is not None:
            api.set_a0_dc_level(parsed_args.set_a0_dc_level)

        if parsed_args.set_a1_mode is not None:
            try:
                mode = api.convert_a1_mode(parsed_args.set_a1_mode)
                api.set_a1_mode(mode)
            except ValueError as e:
                logger.log(logging.ERROR, str(e))
                sys.exit(1)

        if parsed_args.set_a1_dc_level is not None:
            api.set_a1_dc_level(parsed_args.set_a1_dc_level)

        if parsed_args.set_a1_minimum is not None:
            api.set_a1_minimum(parsed_args.set_a1_minimum)

        if parsed_args.set_a1_maximum is not None:
            api.set_a1_maximum(parsed_args.set_a1_maximum)

        if parsed_args.set_a1_steps is not None:
            api.set_a1_steps(parsed_args.set_a1_steps)

        if parsed_args.hello:
            api.hello()

        if parsed_args.is_connected:
            api.is_connected()

        if parsed_args.start_capture:
            api.start_capture()

        if parsed_args.stop_capture:
            api.stop_capture()

        if parsed_args.is_capturing:
            api.is_capturing()

        if parsed_args.clear_note:
            api.clear_note()

        if parsed_args.zoom_all:
            api.zoom_all()

        if parsed_args.show_inputs:
            api.show_inputs()

        if parsed_args.show_outputs:
            api.show_outputs()

        if parsed_args.show_list:
            api.show_list()

        if parsed_args.show_settings:
            api.show_settings()

        if parsed_args.show_notes:
            api.show_notes()

        if parsed_args.close_tabs:
            api.close_tabs()

        if parsed_args.new_capture:
            api.new_capture()

        if parsed_args.exit:
            api.exit()

        api.disconnect()
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.log(logging.ERROR, "Exception: %s", e)
        sys.exit(1)
