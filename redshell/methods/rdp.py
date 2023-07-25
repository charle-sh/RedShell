import os
import shutil
import time
import subprocess
import docker
from docker import errors
from prompt_toolkit.completion import NestedCompleter
from redshell.methods import MethodBase
from redshell.database import db_session
from redshell.rshcompleters import BuiltinCompleter

class RDP(MethodBase):
    NAME = "rdp"
    META = "xFreeRDP client run in Docker through X11"
    TARGET_OS = ["Windows"]

    def __init__(self, target, cred, tunnel, table_instance) -> None:
        self.target = target
        self.ip_addr = target.ip_addr
        self.hostname = target.hostname
        self.cred = cred
        self.tunnel = tunnel
        self.table_instance = table_instance
        self.container = None
        self.connected = False

        self.actions = NestedCompleter.from_nested_dict({
            "show": {
                "targets": {
                    "--full",
                },
                "settings": None,
                "tunnels": None,
            },
            "connect": None,
            "back": None,
            "exit": None,
        })

        # Setup command logging and file collection dirs
        self.cmd_path = f"{target.op_path}/cmd"
        self.collect_path = f"{target.op_path}/files"
        self.docker_path = os.path.join(target.op_path, f"docker/rdp/{self.cred.username}_{self.cred.ctype}")

        paths = [self.cmd_path, self.collect_path, self.docker_path]
        for path in paths:
            if not os.path.exists(path):
                os.makedirs(path)

        self.docker_build()

    def connect(self, **_):
        self.container_name = self.name_generator()
        # Password
        if self.cred.ctype == 'password':
            command_line = f"xfreerdp /v:{self.ip_addr} /u:{self.cred.username} /p:{self.cred.cred} +clipboard /cert:ignore /log-level:DEBUG /dynamic-resolution"
        elif self.cred.ctype == "nthash":
            command_line = f"xfreerdp /v:{self.ip_addr} /u:{self.cred.username} /pth:{self.cred.cred} +clipboard /cert:ignore /log-level:DEBUG /dynamic-resolution"

        # Set for proxychains
        if self.tunnel is not None:
            command_line = f"proxychains {command_line}"

        # Set X11 access rules
        xhost_set_output = subprocess.run(["xhost", "+si:localuser:root"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        # Start container
        self.container = self.client.containers.run(
            self.docker_tag,
            f"{command_line}",
            detach=True,
            remove=False,
            name=self.container_name,
            network_mode="host",
            volumes={self.collect_path: {"bind": "/data", "mode": "rw"}, "/tmp/.X11-unix": {"bind": "/tmp/.X11-unix", "mode": "rw"}},
        )

        # Check for container to be successful or not
        while True:
            time.sleep(1)
            # Unset X11 access rules
            xhost_unset_output = subprocess.run(["xhost", "-si:localuser:root"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            # Check container status
            self.container.reload()
            if self.container.status == "exited":
                fail_log = self.container.logs().decode("utf-8").split("\n")
                fail_log_message = fail_log[1:-1]
                print("[!] Failed to connect:")
                for line in fail_log_message:
                    print(line.strip())
                self.table_instance.status = "Failed"
                db_session.commit()
                self.disconnect()
                break
            elif self.container.status == "running":
                self.connected = True
                self.table_instance.status = "Success"
                db_session.commit()
                break

    def run_command(self, command: str, silent: bool=False, raw: bool=False, record: bool=True):
        pass

    def get_file(self, file_path, **_):
        pass
