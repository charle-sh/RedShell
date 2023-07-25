from redshell.methods.builtins import BuiltinBase

class EnableRDP(BuiltinBase):
    NAME = "enable_rdp"
    META = "Enable RDP on the target system through the registry"
    TARGET_OS = ["Windows"]
    OPTIONS = None

    def __init__(self, method) -> None:
        self.method = method

    def run(self, **_):
        command = 'reg add "HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f'
        self.method.run_command(command, silent=True)
        print("[+] RDP enabled")

class DisableRDP(BuiltinBase):
    NAME = "disable_rdp"
    META = "Disable RDP on the target system through the registry"
    TARGET_OS = ["Windows"]
    OPTIONS = None

    def __init__(self, method) -> None:
        self.method = method

    def run(self, **_):
        command = 'reg add "HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 1 /f'
        self.method.run_command(command, silent=True)
        print("[+] RDP disabled")
