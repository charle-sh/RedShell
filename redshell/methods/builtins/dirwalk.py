import os
import ntpath
import signal
from prompt_toolkit import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import ProgressBar
from prompt_toolkit.shortcuts.progress_bar import formatters
from prompt_toolkit.styles import Style
from redshell import config
from redshell.output_formatter import print_success, print_running, print_fail
from redshell.methods.builtins import BuiltinBase

class DirWalk(BuiltinBase):
    NAME = "dirwalk"
    META = "Performs recursive dir walk starting at target directory"
    TARGET_OS = ["Windows", "Linux"]
    OPTIONS = {"--target_dir": "Directory to act as root for dirwalk. USE FULL PATH!", "--depth": "Depth of directories to search"}

    def __init__(self, method) -> None:
        self.method = method

    def run(self, target_dir, depth, **_):
        filesystem = self.method.run_command("pwd", silent=True, record=False)
        if filesystem.startswith("/"):
            if not target_dir.endswith("/"):
                target_dir += "/"
            self._linux_dir_handler(target_dir, int(depth))
        else:
            self._windows_dir_handler(target_dir, int(depth))

    def _linux_dir_handler(self, target_dir, depth: int):
        current_depth = 0
        to_be_dirred = {}
        next_depth_dir = {}
        to_be_dirred[target_dir] = 0

        with patch_stdout():
            with ProgressBar(
                style=style,
                key_bindings=kb,
                title=f"Dirwalking {target_dir} {str(depth)} levels deep...",
                bottom_toolbar=bottom_toolbar
                ) as pb:
                while current_depth < depth:
                    for line, line_depth in pb(
                        to_be_dirred.items(),
                        label=f"Dirring depth {str(current_depth)}",
                        ):
                        # Stop when the cancel flag has been set.
                        if cancel[0]:
                            break
                        # Print current directory being listed
                        if status[0]:
                            print(f"Status: Currently getting {line}")
                            status[0] = False
                        if line_depth == current_depth:
                            #print(f"about to dir: {line}")
                            contents = self._linux_dir_getter(line)
                            #print(f"dir contents: {contents}")
                            self._linux_dir_writer(contents)
                            # Add results to next list
                            for item in contents:
                                if not item.endswith("/"):
                                    continue
                                next_depth_dir[item] = line_depth + 1
                    #print("outside of loop")
                    current_depth += 1
                    to_be_dirred = {}
                    # Move items to other list for next iteration
                    for line, line_depth in next_depth_dir.items():
                        to_be_dirred[line] = line_depth
                    #print(f"to_be_dirred: {to_be_dirred}")

    def _linux_dir_getter(self, target_dir: str) -> list:
        command = f"ls -Ap {target_dir}"
        output = self.method.run_command(command, silent=True, verbose=False)
        
        output_list = output.split("\n")
        for i, line in enumerate(output_list):
            output_list[i] = f"{target_dir}{line}"
        
        return output_list
    
    def _linux_dir_writer(self, contents):
        configuration = config.read_config()
        op_path = configuration["op_path"]
        file_tracker = f"{op_path}{self.method.host}/filesystem.txt"
        if not os.path.exists(file_tracker):
            os.mknod(file_tracker)
        with open(file_tracker, "r+") as file:
            original_file = file.read()
            for line in contents:
                if line not in original_file and not line.endswith("Permission denied"):
                    #print(f"Writing {line}")
                    file.write(f"{line}\n")

    def _windows_dir_handler(self, target_dir, depth):
        current_depth = 0
        to_be_dirred = {}
        next_depth_dir = {}
        to_be_dirred[target_dir] = 0

        with patch_stdout():
            with ProgressBar(
                style=style,
                key_bindings=kb,
                title=f"Dirwalking {target_dir} {str(depth)} levels deep...",
                bottom_toolbar=bottom_toolbar,
                ) as pb:
                while current_depth < depth:
                    for line, line_depth in pb(
                        to_be_dirred.items(),
                        label=f"Dirring depth {str(current_depth)}",
                        ):
                        # Stop when the cancel flag has been set.
                        if cancel[0]:
                            break
                        # Print current directory being listed
                        if status[0]:
                            print(f"Status: Currently getting {line}")
                            status[0] = False
                        if line_depth == current_depth:
                            #print(f"about to dir: {line}")
                            contents = self._windows_dir_getter(line)
                            #print(contents)
                            #print(f"dir contents: {contents}")
                            self._windows_dir_writer(contents)
                            # Add results to next list
                            for item in contents:
                                if not item.endswith("\\"):
                                    continue
                                next_depth_dir[item] = line_depth + 1
                    #print("outside of loop")
                    current_depth += 1
                    to_be_dirred = {}
                    # Move items to other list for next iteration
                    for line, line_depth in next_depth_dir.items():
                        to_be_dirred[line] = line_depth
                    #print(f"to_be_dirred: {to_be_dirred}")

    def _windows_dir_getter(self, target_dir):
        # Use quotes around path to account for any spaces
        target_dir = f'"{target_dir}"'
        #print(target_dir)
        command = f"dir {target_dir}"
        output = self.method.run_command(command, silent=True)
        #print(output)
        output_list = output.split("\n")

        record = False
        results = []
        for line in output_list:
            if record is False:
                if line.strip().startswith("Directory of"):
                    #print('starting record')
                    record = True
            elif record is True:
                if line.startswith("               "):
                    record = False
                elif line.strip() == '':
                    continue
                else:
                    results.append(line.strip())

        result_list = []

        for result in results:
            result_split = result.split()
            #file_date = result_split[:3]
            dir_or_size = result_split[3]
            filename = ' '.join(result_split[4:])
            # Filter out "." and ".." files
            if filename == "." or filename == "..":
                continue
            # Add \ to directories
            if dir_or_size == "<DIR>":
                filename = f"{filename}\\"
            # Do nothing for filenames
            full_path = ntpath.join(target_dir[1:-1], filename)
            result_list.append(full_path)

        return result_list
    
    def _windows_dir_writer(self, contents):
        configuration = config.read_config()
        op_path = configuration["op_path"]
        file_tracker = f"{op_path}{self.method.host}/filesystem.txt"
        if not os.path.exists(file_tracker):
            os.mknod(file_tracker)
        with open(file_tracker, "r+") as file:
            original_file = file.read()
            for line in contents:
                if line not in original_file and not line.endswith("denied."):
                    #print(f"Writing {line}")
                    file.write(f"{line}\n")

# Create custom key bindings first.
kb = KeyBindings()
cancel = [False]
status = [False]

@kb.add("f")
def _(event):
    print("You pressed `f`.")

@kb.add("s")
def _(event):
    status[0] = True

@kb.add("q")
def _(event):
    "Quit by setting cancel flag."
    cancel[0] = True

style = Style.from_dict(
    {
        "label": "ansiblue",
        "percentage": "bg:#448844 #000000",
        "current": "ansigreen",
        "bar": "",
    }
)

bottom_toolbar = HTML(
    ' <b>[f]</b> Print "f" <b>[s]</b> Status <b>[q]</b> Abort'
)
