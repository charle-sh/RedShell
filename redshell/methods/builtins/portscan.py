import re
from redshell.output_formatter import print_success, print_running, print_fail
from redshell.methods.builtins import BuiltinBase

class PortScan(BuiltinBase):
    NAME = "portscan"
    META = "Runs a PowerShell one liner that checks TCP connectivity to specified sockets"
    TARGET_OS = ["Windows"]
    OPTIONS = {"--ip": "IP of target to scan", "--port": "TCP port to be scanned (list can be provided with comma-separator, no spaces)"}

    def __init__(self, method) -> None:
        self.method = method

    def run(self, ip, port, **_):
        print_running(f"Scanning {ip}...")
        command = f'{port} | % {{echo ((new-object Net.Sockets.TcpClient).Connect("{ip}",$_)) "Port $_ is open"}}'# 2>$null'
        output = self.method.run_command(command, shell_type="powershell", silent=True)
        output_list = output.split("\n")
        #print(output_list)
        for line in output_list:
            if "Port" in line:
                print_success(line)
            elif "No connection could be made" in line:
                match = re.search(f"{ip}:[0-9]*", line)
                full_match = match.group().split(":")
                print_fail(f"Port {full_match[-1]} is closed")
