import os
import time
import shutil
import sys
import pty
import select
import subprocess
from datetime import datetime
import docker
from docker import errors
import pexpect
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.completion import NestedCompleter, FuzzyCompleter
from redshell.output_formatter import print_success, print_running, print_fail
from redshell.methods import MethodBase
from redshell.database import db_session
from redshell.rshcompleters import BuiltinCompleter, FilesystemCompleter


class SSH(MethodBase):
    NAME = "ssh"
    META = "SSH client run in Docker"
    TARGET_OS = ["Linux"]

    def __init__(self, target, cred, tunnel, table_instance) -> None:
        self.target = target
        self.hostname = target.hostname
        self.ip_addr = target.ip_addr
        if self.hostname:
            self.host = self.hostname
        elif self.ip_addr:
            self.host = self.ip_addr
        self.cred = cred
        self.tunnel = tunnel
        self.table_instance = table_instance

        self.actions = NestedCompleter.from_nested_dict({
            "show": {
                "targets": {
                    "--full",
                },
                "options": None,
                "settings": None,
                "tunnels": None,
            },
            "connect": None,
            "shell": {
                "--full",
                "--lowvis",
                "--stealth",
            },
            "run": BuiltinCompleter(self),
            "get": FilesystemCompleter(self),
            "tunnel": {
                "dynamic": {
                    "--port",
                },
                "local": None,
                "remote": None,
            },
            "back": None,
            "exit": None,
        })

        # Setup command logging and file collection dirs
        self.cmd_path = f"{target.op_path}/cmd"
        self.collect_path = f"{target.op_path}/files"
        self.docker_path = os.path.join(target.op_path, f"docker/ssh/{self.cred.username}_{self.cred.ctype}")
        self.script_path = f"{target.op_path}/scripts"

        paths = [self.cmd_path, self.collect_path, self.docker_path, self.script_path]
        for path in paths:
            if not os.path.exists(path):
                os.makedirs(path)

        # Shell
        self._pwd = ""

        # Docker setup
        self.container = None
        self.cmd = b""
        self.client = None
        self.docker_tag = None

        # For outside container
        self.control_socket = f"/dev/shm/ssh/control_{self.host}_{self.cred.username}_{self.cred.ctype}"
        # For inside container
        self.docker_control_socket = f"/dev/shm/control_{self.host}_{self.cred.username}_{self.cred.ctype}"

        self.ssh_config_builder()
        self.docker_build()

    def ssh_config_builder(self):
        for file in os.listdir("./images"):
            full_path = os.path.abspath(f"./images/{file}")
            shutil.copy(full_path, self.docker_path)
        ssh_config_path = os.path.join(self.docker_path, "config")
        ssh_config = {
            "Host" : self.host,
            "User" : self.cred.username,
            "Port" : "22",
            "StrictHostKeyChecking" : "no",
            "UserKnownHostsFile" : "/dev/null",
            "ControlMaster" : "auto",
            "ControlPath" : self.docker_control_socket,
        }

        # Write ssh config file
        with open(ssh_config_path, "w", encoding="utf-8") as config_file:
            for key in ssh_config.keys():
                if key == "Host":
                    config_file.write(f"{key} {ssh_config[key]}\n")
                else:
                    config_file.write(f"    {key} {ssh_config[key]}\n")

    def docker_build(self):
        if self.tunnel:
            self.proxychains_build()
        self.docker_tag = f"rsh_ssh_{self.cred.username}_{self.cred.ctype}"
        self.client = docker.from_env()
        self.client.images.build(path=self.docker_path, tag=self.docker_tag)
        #print("[+] Build successful")

    # Check for control socket to see if connected
    @property
    def connected(self) -> bool:
        if os.path.exists(self.control_socket):
            return True
        else:
            return False

    def connect(self, **_):
        master_name = self.name_generator()

        command_line = f"sshpass -p {self.cred.cred} ssh -N {self.host}"

        self.container = self.client.containers.run(
            self.docker_tag,
            command_line,
            detach=True,
            remove=False,
            name=master_name,
            volumes={"/dev/shm/ssh": {"bind": "/dev/shm", "mode": "rw"}},
        )

        # Check for container to be successful or not
        while True:
            time.sleep(1)
            self.container.reload()
            if self.container.status == "exited":
                fail_log = self.container.logs().decode("utf-8").split("\n")
                fail_log_message = fail_log[1:-1]
                print_fail("Failed to connect:")
                for line in fail_log_message:
                    print(line.strip())
                self.table_instance.status = "Failed"
                db_session.commit()
                self.disconnect()
                break
            elif self.container.status == "running" and os.path.exists(self.control_socket):
                self.table_instance.status = "Success"
                db_session.commit()
                break

    # Fix run_command to not write output to disk if wanted
    def run_command(self, command: str, silent: bool=False, raw: bool=False, record: bool=True, verbose=True) -> str:
        if self.connected is True:
            cmd_time = datetime.now().strftime("%Y%m%d-%H%M%S")

            # Allow direct control of command line
            if raw is True:
                docker_command = command
            elif verbose:
                docker_command = f"ssh -vx {self.host} {command}"
            else:
                docker_command = f"ssh -x {self.host} {command}"

            try:
                output = self.client.containers.run(
                    self.docker_tag,
                    docker_command,
                    remove=True,
                    volumes={
                        "/dev/shm/ssh": {"bind": "/dev/shm", "mode": "rw"},
                        self.collect_path: {"bind": "/data", "mode": "rw"},
                        self.script_path: {"bind": "/scripts", "mode": "ro"},
                    },
                )
            except errors.ContainerError as err:
                output = err.stderr

            # Add to filesystem tracker, if relevant
            #if "ls" in command:
            #    self.record_filesystem(output)

            # Commit to database
            self.write_command_to_db(command, output.decode())

            # Write command output to file with command as title
            format_command = command.replace(" ", "_").replace(
                "/", "_"
            )  # replace spaces and /
            cmd_log = f"{self.cmd_path}/{format_command}_{cmd_time}"

            if record is True:
                with open(cmd_log, "w", encoding="utf-8") as f:
                    f.write(output.decode())

            # If used by shell(), just return output
            if silent is True:
                return output.decode().strip()
            print(output.decode().strip())
        else:
            print_fail("Method is not connected")

    def shell(self, mode="stealth", **_):
        """
        Mode options: stealth, lowvis, full
        """

        # Needed because argparse in cli.py sends None if no flag is given
        if mode is None:
            mode = "stealth"
        self.shell_style = Style.from_dict(
            {
                # User input (default text).
                # "": "#ff0066",
                # Prompt.
                "method": "#00aa00",
                "close_paren": "#00aa00",
                "at": "#00aa00",
                "colon": "#0000aa",
                # "pound": "#00aa00",
                "host": "ansiblue",
                "cwd": "ansicyan",
            }
        )

        self.shell_options = NestedCompleter.from_nested_dict({
            "!run": BuiltinCompleter(self),
            "!get": FilesystemCompleter(self),
            #"!tunnel": {
            #    "dynamic": {
            #        "--port",
            #    },
            #    "local": None,
            #    "remote": None,
            #},
            "back": None,
            "exit": None,
        })

        if self.connected is True:
            if mode == "full":
                self._full_shell()
            if mode == "lowvis":
                self._lowvis_shell()
            if mode == "stealth":
                self._stealth_shell()
        else:
            print_fail("Method is not connected")

    def _full_shell(self):
        print_running(
            "Enter the below command into your Linux shell. This will SSH into the target using the already present control socket. No commands will be logged."
            )
        print(f"sudo ssh -xv -S {self.control_socket} {self.host}")

    def _lowvis_shell(self):
        print_running("This passes /bin/sh to the target. The session will be logged, but the shell has fewer features.")
        # Create pty to talk to container
        master, slave = pty.openpty()

        cmd = f"docker run -it -v /dev/shm/ssh:/dev/shm {self.docker_tag} ssh -xv {self.host} /bin/sh".split()

        p = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave)

        input_from_your_terminal = '' # init variable
        i = 0
        while p.poll() is None:
            # Watch two files, STDIN of your Python process and the pseudo terminal
            r, _, _ = select.select([sys.stdin, master], [], [])
            if sys.stdin in r:
                # Read STDIN to get command line input
                input_from_your_terminal = os.read(sys.stdin.fileno(), 10240)
                # If first command, run unsets to avoid logging to history files
                if i == 0:
                    input_from_your_terminal = input_from_your_terminal[:-1] + b"; unset HISTFILE HISTFILESIZE HISTSIZE PROMPTCOMMAND\n"
                    i += 1
                # Act as a shim to command
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
                        #command = output_from_docker.decode().strip()
                        continue
                # Write command output to file with command as title
                cmd_time = datetime.now().strftime("%Y%m%d-%H%M%S")
                unformatted_command = str(input_from_your_terminal)[2:-3]
                format_command = unformatted_command.replace(" ", "_").replace(
                    "/", "_"
                )  # replace spaces and /

                # Only write to file if output from command, not just starting up
                if format_command != "":
                    cmd_log = f"{self.cmd_path}/{format_command}_{cmd_time}"
                    output_to_file = output_from_docker.decode().replace("\r\r", "").replace(
                        "\r\nC:\\>", ""
                    )
                    # output comes out in chunks, so need to find way to group them together
                    with open(cmd_log, "a", encoding="utf-8") as f:
                        f.write(output_to_file)
                    # When the prompt comes back, we now have full command output
                    # Write full output to database
                    if output_from_docker.endswith(b"\r\nC:\\>"):
                        with open(cmd_log, "r", encoding="utf-8") as f:
                            full_output = f.read()
                        # Commit to database
                        self.write_command_to_db(unformatted_command, full_output)

                # Write container output to STDOUT
                os.write(sys.stdout.fileno(), output_from_docker)

    def _stealth_shell(self):
        print_running("This is a non-interactive shell, be careful what you run. Use full paths whenever possible!")
        session = PromptSession()
        i = 0
        while True:
            try:
                # Get PWD on first loop
                if i == 0:
                    self._pwd = self.run_command("echo $PWD", silent=True, record=False)
                    i = 1

                # Build prompt
                message = [
                    ("class:method", "ssh("),
                    ("class:host", f"{self.hostname}/{self.ip_addr}"),
                    ("class:close_paren", "):"),
                    ("class:cwd", f"{self._pwd}"),
                    ("class:pound", "# "),
                ]
                cmd = session.prompt(
                    message,
                    style=self.shell_style,
                    completer=FuzzyCompleter(
                        self.shell_options,
                        #WORD=True, # works well with filesystem but doesn't show options until correct letter typed
                        ),
                    complete_while_typing=True,
                    )
                if cmd.lower() == "exit" or cmd.lower() == "back":
                    print_running("Exiting shell...\n")
                    break
                # CWD tracking, seems to be working ok
                if cmd.startswith("cd"):
                    output = self.run_command(cmd + "; pwd", silent=True, record=False)
                    if output != "":
                        self._pwd = output
                    continue
                # Handle "ls" with the non-interactive shell's CWD tracking
                if cmd.startswith("ls") or cmd.startswith("ll"):
                    cmd_split = cmd.split()
                    # ls
                    if len(cmd_split) == 1:
                        cmd_new = f"{cmd} {self._pwd}"
                    # ls -las relative_dir OR ls relative_dir
                    elif not cmd_split[-1].startswith("-") and "/" not in cmd_split[-1]:
                        cmd_new = f"{' '.join(cmd_split[:-1])} {self._pwd}/{cmd_split[-1]}"
                    # ls -las
                    elif cmd_split[-1].startswith("-"):
                        cmd_new = f"{cmd} {self._pwd}"
                    # ls -las /etc OR ls /etc
                    else:
                        cmd_new = cmd
                    self.run_command(cmd_new)
                    continue
                if cmd.startswith("!run "):
                    self.builtins(cmd)
                elif cmd.startswith("!get "):
                    file_path = cmd.split()[-1]
                    if " " not in file_path:
                        file_path = file_path[1:-1]
                    self.get_file(file_path)
                else:
                    self.run_command(cmd)
            #except errors.ContainerError as err:
            #    print(err.stderr.decode())
            except KeyboardInterrupt:
                print_running("Exiting shell...")
                break

    def get_file(self, file_path, **_):
        print_running(f"Getting {file_path} from target...")

        # Split file_path to get remote dir and file
        remote_dir, filename = os.path.split(file_path)

        # Create local dir for files to match target filesystem
        if not os.path.exists(f"{self.collect_path}/{remote_dir}"):
            os.makedirs(f"{self.collect_path}/{remote_dir}")
            
        # Start SFTP Docker container
        sftp_cmd = f"docker run --rm -it -v /dev/shm/ssh:/dev/shm -v {self.collect_path}:/data {self.docker_tag} sftp {self.host}"
        sftp_docker = pexpect.spawn(sftp_cmd)
        try:
            # Handle SFTP client commands
            sftp_docker.expect("sftp>")
            sftp_docker.sendline(f"cd {remote_dir}")
            sftp_docker.expect("sftp>")
            sftp_docker.sendline(f"get -ap {filename} /data/{remote_dir}")
            # List of possible responses
            response = sftp_docker.expect(["Permission denied", "100%"])
            if response == 0:
                print_fail("Permission denied")
            elif response == 1:
                print_success(f"Successfully downloaded {file_path}")
            sftp_docker.isalive()
            sftp_docker.close()
        except pexpect.EOF:
            print("SFTP file transfer failed due to premature end of file.")
        except pexpect.TIMEOUT:
            print("SFTP file transfer failed due to timeout.")

    def build_tunnel(self, tunnel_type, local_port, **_):
        if tunnel_type == "dynamic":
            self._build_dynamic_tunnel(local_port)

    def _build_local_tunnel(self, local_port, remote_ip, remote_port):
        tunnel_commad = f"{self.host} -L *:{local_port}:{remote_ip}:{remote_port}"
        self.run_command(tunnel_commad, silent=True, record=False)

    def _build_dynamic_tunnel(self, local_port):
        if self.connected is not True:
            print_fail("Method is not connected")
            return
        tunnel_command = f"ssh {self.host} -N -D *:{local_port}"
        tunnel_name = f"{self.host}_ssh_tunnel_{local_port}"

        self.tunnel_container = self.client.containers.run(
            self.docker_tag,
            tunnel_command,
            detach=True,
            remove=True,
            name=tunnel_name,
            volumes={"/dev/shm/ssh": {"bind": "/dev/shm", "mode": "rw"}},
        )

        #container = self.client.containers.get(self.container.id)
        tunnel_ip_addr = self.container.attrs['NetworkSettings']['IPAddress']

        self.target.tunnels.append(ip_addr=tunnel_ip_addr, port=local_port, tunnel_type="dynamic")

        print_success(f"Tunnel listening on {tunnel_ip_addr}:{local_port}")

    def disconnect(self):
        if self.container == None:
            return
        try:
            print_running("Removing containers...")
            self.container.stop()
            self.container.remove()
        except errors.NotFound:
            pass
