from datetime import datetime
from redshell.models import Target
from redshell.database import db_session
from redshell.methods.builtins import BuiltinBase

class WindowsSurvey(BuiltinBase):
    NAME = "winsurvey"
    META = "Enumerates the target Windows host"
    TARGET_OS = ["Windows"]
    OPTIONS = None

    def __init__(self, method) -> None:
        self.method = method
        self.target_db = db_session.query(Target).filter(Target.ip_addr == self.method.ip_addr).one()
        self.output = ''

    def run(self, **_):
        self._user_enum()
        self._system_enum()
        self._network_enum()
    
    def _user_enum(self):
        # List of commands to run
        commands = [
            "whoami /all",
            "net users",
            "net localgroup",
            "net localgroup Administrators",
            "qwinsta",
            "cmdkey /list",
        ]
        
        for command in commands:
            self.output = self.method.run_command(command, silent=True)

    def _system_enum(self):
        commands = [
            "systeminfo",
            "tasklist",
            "tasklist /svc",
            "wmic qfe",
            "set",
            "net user",
        ]

        for command in commands:
            self.output = self.method.run_command(command, silent=True)
            output_split = self.output.split('\n')
            if command == 'tasklist':
                _tasklist_parser(output_split)
            elif command == 'systeminfo':
                _systeminfo_parser(output_split, self.target_db)
            elif command == "set":
                _set_parser(output_split, self.target_db)

    def _network_enum(self):
        commands = [
            "ipconfig /all",
            "route print",
            "arp -a",
            "netstat -ano",
            "powershell -c \"Get-NetFirewallRule -Direction Inbound -Enabled True\"",
        ]

        for command in commands:
            self.output = self.method.run_command(command, silent=True)

        files = [
            "C:\WINDOWS\System32\drivers\etc\hosts",
        ]

        for file in files:
            self.method.get_file(file)

def _tasklist_parser(output: list):
    for line in output:
        # AV/EDR detection
        if line.startswith('MsMpEng.exe'):
            print('[!] Windows Antimalware Service Executable (Windows Defender) detected')
            print(line)

def _systeminfo_parser(output: list, target_db):
    # Virtual machines names
    vm_names = ["VirtualBox"]

    # Build dict from list
    output_dict = {}
    for line in output:
        key = line.split(":")[0].strip()
        output_dict[key] = line.split(":")[-1].strip()

    for key, value in output_dict.items():
        # Correct target hostname if wanted
        if key == "Host Name" and target_db.hostname != value:
            print(f"[!] Discovered hostname '{value}' does not match stored hostname '{target_db.hostname}'")
            update = input("Update? (y/N) ")
            if update == "y":
                target_db.hostname = value
                db_session.commit()

        # Get target OS info
        elif key == "OS Name":
            target_db.os_name = value
            db_session.commit()
        elif key == "OS Version":
            target_db.os_version = value
            db_session.commit()

        # Check for target VM info
        elif key == "System Model":
            if value in vm_names:
                vm_value = value
            else:
                vm_value = "No"
            target_db.virtual_machine = vm_value
            db_session.commit()

def _set_parser(output: list, target_db):
    # Build dict from list
    output_dict = {}
    for line in output:
        key = line.split("=")[0].strip()
        output_dict[key] = line.split("=")[-1].strip()

    for key, value in output_dict.items():
        # Get processor info
        if key == "PROCESSOR_ARCHITECTURE":
            target_db.arch = value
            db_session.commit()