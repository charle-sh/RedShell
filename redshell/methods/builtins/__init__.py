import os
import traceback
from importlib import util

class BuiltinBase:
    """
    Basic resource class. Concrete resources will inherit from this one.
    """
    builtins = []

    # For every class that inherits from the current,
    # the class name will be added to builtins
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.builtins.append(cls)
    
    def write_to_file(self):
        # Write command output to file with command as title
        format_command = self.NAME.replace(" ", "_").replace(
            "/", "_"
        )  # replace spaces and /
        cmd_log = f"{self.method.cmd_path}/{format_command}_{self.cmd_time}"

        # Write output to cmd file
        with open(cmd_log, "w", encoding="utf-8") as f:
            f.write(self.output)

def load_module(module_path):
    """Utility to automatically load modules."""
    name = os.path.split(module_path)[-1]
    spec = util.spec_from_file_location(name, module_path)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Get current path
path = os.path.abspath(__file__)
dirpath = os.path.dirname(path)

for fname in os.listdir(dirpath):
    # Load only "real modules"
    if (
        not fname.startswith(".")
        and not fname.startswith("__")
        and fname.endswith(".py")
    ):
        try:
            load_module(os.path.join(dirpath, fname))
        except OSError:
            traceback.print_exc()
