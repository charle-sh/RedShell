import os
import shutil
import time
import pty
import subprocess
import select
import sys
import ntpath
import pathlib
import pexpect
from datetime import datetime
import docker
from prompt_toolkit import prompt
from prompt_toolkit.completion import NestedCompleter
from redshell.methods import MethodBase
from redshell.rshcompleters import BuiltinCompleter
from redshell.database import db_session

class SMB(MethodBase):
    NAME = "smb"
    META = "Impacket's 'smbexec' run in Docker"
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
            "shell": None,
            "run": BuiltinCompleter(self),
            "get": None,
            "back": None,
            "exit": None,
        })

        # Setup command logging and file collection dirs
        self.cmd_path = f"{target.op_path}/cmd"
        self.collect_path = f"{target.op_path}/files"
        self.docker_path = os.path.join(target.op_path, f"docker/smb/{self.cred.username}_{self.cred.ctype}")

        paths = [self.cmd_path, self.collect_path, self.docker_path]
        for path in paths:
            if not os.path.exists(path):
                os.makedirs(path)

        self.docker_build()

    def connect(self, **_):
        self.container_name = self.name_generator()

        # Password
        if self.cred.ctype == 'password':
            command_line = f"python /usr/bin/smbexec.py {self.cred.username}:{self.cred.cred}@{self.ip_addr}"
        elif self.cred.ctype == "nthash":
            command_line = f"python /usr/bin/smbexec.py -hashes :{self.cred.cred} {self.cred.username}@{self.ip_addr}"

        # Set for proxychains
        if self.tunnel is not None:
            command_line = f"proxychains {command_line}"

        # Start container
        self.container = self.client.containers.run(
            self.docker_tag,
            command_line,
            detach=True,
            tty=True,
            stdin_open=True,
            remove=False,
            name=self.container_name,
            volumes={self.collect_path: {"bind": "/data", "mode": "rw"}},
        )

        # Check for container to be successful or not
        while True:
            time.sleep(1)
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

    def run_command(self, command: str, silent: bool=False, proxy=False) -> str:
        if self.connected is True:
            cmd_time = datetime.now().strftime("%Y%m%d-%H%M%S")
            # Password
            if self.cred.ctype == 'password':
                command_line = f"python /usr/bin/smbexec.py {self.cred.username}:{self.cred.cred}@{self.ip_addr}"
            elif self.cred.ctype == "nthash":
                command_line = f"python /usr/bin/smbexec.py -hashes :{self.cred.cred} {self.cred.username}@{self.ip_addr}"

            # Set for proxychains
            if self.tunnel is not None:
                command_line = f"proxychains {command_line}"
            
            smb_cmd = f"docker run --rm -it -v {self.collect_path}:/data {self.docker_tag} {command_line}"

            smb_docker = pexpect.spawn(smb_cmd)

            # Handle SFTP client commands
            smb_docker.expect("C:\\\\Windows\\\\system32>")
            smb_docker.sendline(f"{command}")
            smb_docker.expect("C:\\\\Windows\\\\system32>")
            smb_docker.isalive()
            smb_docker.close()

            # Write command output to file with command as title
            format_command = command.replace(" ", "_").replace(
                "/", "_"
            )  # replace spaces and /
            cmd_log = f"{self.cmd_path}/{format_command}_{cmd_time}"

            # Format output, get rid of command text
            output = smb_docker.before.decode().split("\n", 1)[1].strip()
            # Prevent extra newlines when written to file
            output = output.replace("\r\r", "")

            # Write command output to file
            with open(cmd_log, "w", encoding="utf-8") as f:
                f.write(output)

            # If used by shell() or builtin, just return output
            if silent is True:
                return output
            print(output)
            
        else:
            print("[!] Method is not connected")

    def shell(self, **kwargs):
        if self.connected is True:
            self.container.reload()
            # Get container running again if shell was used and exited
            if self.container.status != 'running':
                self.container.start()

            # Create pty to talk to container
            master, slave = pty.openpty()

            p = subprocess.Popen(['docker', 'attach', self.container_name], stdin=slave, stdout=slave, stderr=slave)

            input_from_your_terminal = '' # init variable
            while p.poll() is None:
                # Watch two files, STDIN of your Python process and the pseudo terminal
                r, _, _ = select.select([sys.stdin, master], [], [])
                if sys.stdin in r:
                    # Read STDIN to get command line input
                    input_from_your_terminal = os.read(sys.stdin.fileno(), 10240)
                    # Act as a shim to command line
                    if input_from_your_terminal.startswith(b"!run "):
                        command = input_from_your_terminal.decode().strip()[5:]
                        self.builtins(command)
                        input_from_your_terminal = b'\n' # brings prompt back
                    elif input_from_your_terminal.startswith(b"!get "):
                        command = input_from_your_terminal.decode().strip()[5:]
                        self.get_file(command)
                        input_from_your_terminal = b'\n' # brings prompt back
                    elif input_from_your_terminal == b"back\n":
                        break
                    elif input_from_your_terminal == b"exit\n":
                        print("[!] Are you sure you want to exit? Using 'back' will allow you to reconnect to the same session later.")
                        answer = input("Exit? (y/N) ")
                        if answer == 'y':
                            print('[*] Press enter again to exit')
                        else:
                            input_from_your_terminal = b'\n' # brings prompt back
                    # Send input to container command line
                    os.write(master, input_from_your_terminal)
                elif master in r:
                    output_from_docker = os.read(master, 10240)
                    # If just echoing input command, skip it
                    if type(input_from_your_terminal) == bytes:
                        if output_from_docker.decode().strip() == input_from_your_terminal.decode().strip():
                           continue
                    # Write container output to STDOUT
                    os.write(sys.stdout.fileno(), output_from_docker)
        else:
            print("[!] Method is not connected")

    def get_file(self, file_path, **_):
        if self.connected is True:
            #cmd_time = datetime.now().strftime("%Y%m%d-%H%M%S")
            # Split file path to get remote dir and file
            remote_dir, filename = ntpath.split(file_path)
            # Get drive letter and path
            drive, path = ntpath.splitdrive(file_path)
            # Change from Windows to Unix file path
            new_local_dir = pathlib.PureWindowsPath(remote_dir).as_posix()
            new_local_dir = new_local_dir.replace(":", "").lower()
            collect_file_path = f"{self.collect_path}/{new_local_dir}"
            # Create local dir for files to match target filesystem
            if not os.path.exists(collect_file_path):
                os.makedirs(collect_file_path)
            
            if self.cred.ctype == "password":
                command_line = f"python /usr/bin/smbclient.py {self.cred.username}:{self.cred.cred}@{self.ip_addr}"
            elif self.cred.ctype == "nthash":
                command_line = f"python /usr/bin/smbclient.py -hashes :{self.cred.cred} {self.cred.username}@{self.ip_addr}"

            # Set for proxychains
            if self.tunnel is not None:
                command_line = f"proxychains {command_line}"

            smb_cmd = f"docker run --rm -it -v {collect_file_path}:/data {self.docker_tag} {command_line}"

            smb_docker = pexpect.spawn(smb_cmd)

            # Handle SFTP client commands
            smb_docker.expect("# ")
            smb_docker.sendline(f"use {drive[:-1]}$")
            smb_docker.expect("# ")
            smb_docker.sendline(f"get {path[1:]}")
            # List of possible responses
            response = smb_docker.expect(["[-]", "# "])
            if response == 0:
                print("[!] Error")
                print(smb_docker.before.decode().strip()+smb_docker.after.decode().strip())
            elif response == 1:
                print(f"[+] Successfully downloaded {file_path}")
            smb_docker.isalive()
            smb_docker.close()

        else:
            print("[!] Method is not connected")
