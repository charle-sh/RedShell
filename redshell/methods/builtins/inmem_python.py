import shutil
import os
from typing import Union
from redshell.methods.builtins import BuiltinBase

class InMemPython(BuiltinBase):
    """
    Redirects the contents of a local Python script into a remote Python interpreter process
    while minimizing artifacts. 
    
    Automatically discovers a Python interpreter binary on the target
    host, prevents .pyc/.pyo files from being created on module import, and stops commands from
    being written in the Python interpreter terminal history file.
    """

    NAME = "inmem-python"
    META = "Loads Python commands into remote interpreter process in-memory"
    TARGET_OS = ["Linux"]
    OPTIONS = {"--script": "Location of script to load"}

    def __init__(self, method) -> None:
        self.method = method

    def run(self, script: Union[str, os.PathLike], **_) -> None:
        # Work out script location
        full_script_path = os.path.abspath(script)
        script_filename = os.path.basename(full_script_path)
        rsh_script_path = f"{self.method.script_path}/{script_filename}"
        docker_filename = f"/scripts/{script_filename}"
        
        # Find remote interpreter binary
        python_interpreter = self._find_interpreter()

        # If found, load script
        if python_interpreter != None:
            print(f"[+] Found {python_interpreter} binary on target")
            
            # Put copy of script into path that Docker container can see
            shutil.copy(full_script_path, rsh_script_path)

            # PYTHONSTARTUP='/dev/null' will prevent commands from appearing in interpreter
            # terminal history
            # -B option will prevent Python from writing .pyc/.pyo files when source modules are
            # imported for the first time
            docker_command = f"sh -c 'ssh {self.method.ip_addr} PYTHONSTARTUP='/dev/null' {python_interpreter} -B < {docker_filename}'"
            print(f"[*] Remotely loading {script_filename} into interpreter...\n")
            self.method.run_command(docker_command, raw=True, record=False)
        else:
            print("[!] No Python interpreters found on target")

    def _find_interpreter(self) -> Union[str, os.PathLike]:
        # List of interpreters to look for
        interpreters = [
            "python",
            "python3",
        ]

        # Run 'which' commands on target to look for binary
        for interpreter in interpreters:
            output = self.method.run_command(f"which {interpreter}", silent=True)
            if output != '':
                return output
