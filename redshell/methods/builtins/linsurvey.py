from redshell.methods.builtins import BuiltinBase
from redshell.output_formatter import print_success, print_running, print_fail

class LinSurvey(BuiltinBase):
    """
    Redirects the contents of a local copy of linpeas.sh into an ssh session on a target system
    while minimizing artifacts.
    """

    NAME = "linsurvey"
    META = "Loads Python commands into remote interpreter process in-memory"
    TARGET_OS = ["Linux"]
    OPTIONS = None

    def __init__(self, method) -> None:
        self.method = method

    def run(self, **_) -> None:
        # Load linpeas.sh directly into the ssh session
        docker_command = f"sh -c 'ssh {self.method.host} < /linpeas.sh'"
        print_running(f"Remotely loading linpeas into memory and executing...\n")
        self.method.run_command(docker_command, raw=True)
