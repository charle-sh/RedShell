import argparse
import docker
from prompt_toolkit import prompt, PromptSession
from redshell.rsh import RSH
from prettytable import PrettyTable
from prompt_toolkit.styles import Style
from prompt_toolkit.completion import FuzzyCompleter
from redshell.output_formatter import print_success, print_running, print_fail
from redshell.models import Target, Credential, Method, Tunnel
from redshell.database import db_session

class ExitPrompt(Exception):
    pass

class CLI:
    def __init__(self, rsh_instance, interactive: bool=True) -> None:
        self.rsh = rsh_instance

        self.target = None
        self.credential = None
        self.method = None
        self.tunnel = None
        self.interactive = interactive
        self.next_parser = ''

        if self.interactive is True:
            self.base_rsh_prompt()

    # 'show' commands
    def show_targets(self, full: bool=False, **_) -> None:
        database = db_session.query(Target).all()
        if full is False:
            columns = [
                'ID',
                'IP',
                'Hostname',
                "OS Name"
            ]
            tab = PrettyTable(columns)
            for i, target in enumerate(database):
                row = [
                    str(i),
                    target.ip_addr,
                    target.hostname,
                    target.os_name
                ]
                tab.add_row(row)
            print(tab)
        elif full is True:
            columns = [
                'ID',
                'IP',
                'Hostname',
                "OS Name",
                "OS Version",
                "Arch",
                "VM"
            ]
            tab = PrettyTable(columns)
            for i, target in enumerate(database):
                row = [
                    str(i),
                    target.ip_addr,
                    target.hostname,
                    target.os_name,
                    target.os_version,
                    target.arch,
                    target.virtual_machine
                ]
                tab.add_row(row)
            print(tab)

    def show_credentials(self, **_) -> None:
        columns = ['ID', 'Username', 'Type', 'Cred', "Domain", "Origin"]
        tab = PrettyTable(columns)
        # Update list before pulling results
        self.target.credentials.update()
        for i, cred in enumerate(self.target.credentials):
            row = [i, cred.username, cred.ctype, cred.cred, cred.domain, cred.origin]
            tab.add_row(row)
        print(tab)

    def show_methods(self, **_) -> None:
        columns = ['ID', "Method", 'IP', 'Hostname', 'Username', 'Type', 'Cred', 'Tunnel-IP', 'Tunnel-Port', 'Tunnel-Type', 'Status']
        tab = PrettyTable(columns)
        methods = db_session.query(Method).filter(Method.target_id==self.target.id).all()
        for i, method in enumerate(methods):
            # Handle if no tunnel set
            if method.tunnel is not None:
                row = [
                    i, 
                    method.method_type, 
                    method.target.ip_addr, 
                    method.target.hostname, 
                    method.credential.username, 
                    method.credential.ctype, 
                    method.credential.cred,
                    method.tunnel.ip_addr,
                    method.tunnel.port,
                    method.tunnel.tunnel_type,
                    method.status,
                ]
            else:
                row = [
                    i, 
                    method.method_type, 
                    method.target.ip_addr, 
                    method.target.hostname, 
                    method.credential.username, 
                    method.credential.ctype, 
                    method.credential.cred,
                    "None",
                    "None",
                    "None",
                    method.status,
                ]
            tab.add_row(row)
        print(tab)

    def show_tunnels(self, **_) -> None:
        columns = ["ID", "IP", "Port", "Type"]
        tab = PrettyTable(columns)
        # Update list before pulling results
        self.target.tunnels.update()
        for i, tunnel in enumerate(self.target.tunnels):
            row = [i, tunnel.ip_addr, tunnel.port, tunnel.tunnel_type]
            tab.add_row(row)
        print(tab)

    def show_containers(self, **_) -> None:
        """
        Shows table of existing containers running on the system spawned by RedShell.
        """

        columns = ["ID", "Target IP", "Container Name", "Status"]
        tab = PrettyTable(columns)

        for i, item in enumerate(self.rsh.containers.items()):
            method, container = item
            row = [i, method.ip_addr, container.name, container.status]
            tab.add_row(row)
        print(tab)

    def show_settings(self, **kwargs) -> None:
        settings = {
            "Target": self.target.ip_addr,
        }
        if self.credential:
            settings["Credential - Username"] = self.credential.username
            settings["Credential - Type"] = self.credential.ctype
            settings["Credential - Cred"] = self.credential.cred
        else:
            settings["Credential - Username"] = "None"
            settings["Credential - Type"] = "None"
            settings["Credential - Cred"] = "None"
        if self.tunnel:
            settings["Tunnel"] = f"{self.tunnel.ip_addr}:{self.tunnel.port}"
        else:
            settings["Tunnel"] = "None"
        if self.method:
            settings["Method"] = self.method.NAME
        else:
            settings["Method"] = "None"

        for setting in settings.keys():
            print(f"{setting}: {settings[setting]}")

    # option parsing
    def rsh_parser_handler(self, command_line):
        if command_line == "exit":
            try:
                for item in self.rsh.containers.items():
                    method, _ = item
                    method.disconnect()
            # Handle no method set yet
            except AttributeError:
                pass
            raise ExitPrompt
        
        command = command_line.split()

        if self.next_parser == '':
            self.base_rsh_parser(command)
        elif self.next_parser == 'target':
            self.target_rsh_parser(command)
        elif self.next_parser == 'method':
            self.method_rsh_parser(command)

    def base_rsh_parser(self, command):
        parser = argparse.ArgumentParser(prog='rsh', exit_on_error=False, usage=argparse.SUPPRESS)
        action_subparser = parser.add_subparsers(help='commands', dest="action")

        # Top level
        show_action_parser = action_subparser.add_parser('show')
        add_action_parser = action_subparser.add_parser('add')
        set_action_parser = action_subparser.add_parser('set')

        # 'show' parsers
        show_action_subparser = show_action_parser.add_subparsers(dest="noun")
        show_action_targets_parser = show_action_subparser.add_parser('targets')
        show_action_targets_parser.add_argument('--full', dest='full', action="store_true")
        show_action_targets_parser.set_defaults(func=self.show_targets)
        #show_action_settings_parser = show_action_subparser.add_parser('settings')

        # 'add' parsers
        add_action_subparser = add_action_parser.add_subparsers(dest='noun')
        add_action_target_parser = add_action_subparser.add_parser('target')
        add_action_target_parser.add_argument('--ip', dest='ip_addr', type=str)
        add_action_target_parser.add_argument('--hostname', dest='hostname', type=str)
        add_action_target_parser.set_defaults(func=self.rsh.targets.append)

        # 'set' parsers
        set_action_subparser = set_action_parser.add_subparsers(dest='noun')
        set_action_target_parser = set_action_subparser.add_parser('target')
        set_action_target_parser.add_argument('value', type=str) # used to be ip

        # Parse options
        try:
            args = parser.parse_args(command)
            if args.action == 'set' and args.noun == 'target':
                #self.target = self.rsh.targets[args.ip]
                self.target = self.rsh.targets[args.value]
                self.next_parser = 'target'
            # All other functions will take only correct args
            else:
                args.func(**vars(args))
        # Catch argparse exit attempts
        except SystemExit:
            pass

    def target_rsh_parser(self, command):
        if command[0] == 'back':
            self.next_parser = ''
            return

        parser = argparse.ArgumentParser(prog='rsh', exit_on_error=False, usage=argparse.SUPPRESS)
        action_subparser = parser.add_subparsers(help='commands', dest="action")

        # Top level
        show_action_parser = action_subparser.add_parser('show')
        add_action_parser = action_subparser.add_parser('add')
        set_action_parser = action_subparser.add_parser('set')
        unset_action_parser = action_subparser.add_parser('unset')

        # 'show' parsers
        show_action_subparser = show_action_parser.add_subparsers(dest="noun")

        show_action_targets_parser = show_action_subparser.add_parser('targets')
        show_action_targets_parser.add_argument('--full', dest='full', action="store_true")
        show_action_targets_parser.set_defaults(func=self.show_targets)

        show_action_settings_parser = show_action_subparser.add_parser('settings')
        show_action_settings_parser.set_defaults(func=self.show_settings)

        show_action_credentials_parser = show_action_subparser.add_parser('credentials')
        show_action_credentials_parser.set_defaults(func=self.show_credentials)

        show_action_methods_parser = show_action_subparser.add_parser('methods')
        show_action_methods_parser.set_defaults(func=self.show_methods)
        
        show_action_tunnels_parser = show_action_subparser.add_parser("tunnels")
        show_action_tunnels_parser.set_defaults(func=self.show_tunnels)

        show_action_containers_parser = show_action_subparser.add_parser("containers")
        show_action_containers_parser.set_defaults(func=self.show_containers)

        # 'add' parsers
        add_action_subparser = add_action_parser.add_subparsers(dest='noun')

        add_action_credential_parser = add_action_subparser.add_parser('credential')
        add_action_credential_parser.add_argument('--user', dest='username', type=str, required=True)
        add_action_credential_parser.add_argument('--type', dest='ctype', type=str, required=True)
        add_action_credential_parser.add_argument('--cred', dest='cred', type=str, required=True)
        add_action_credential_parser.add_argument('--domain', dest='domain', type=str)
        add_action_credential_parser.set_defaults(func=self.target.credentials.append)

        add_action_tunnel_parser = add_action_subparser.add_parser("tunnel")
        add_action_tunnel_parser.add_argument('--ip', dest='ip_addr', type=str, required=True)
        add_action_tunnel_parser.add_argument('--port', dest='port', type=str, required=True)
        add_action_tunnel_parser.add_argument('--type', dest='tunnel_type', type=str, required=True)
        add_action_tunnel_parser.set_defaults(func=self.target.tunnels.append)

        add_action_method_parser = add_action_subparser.add_parser('method')
        add_action_method_parser.add_argument('method', type=str)
        add_action_method_parser.add_argument('cred', nargs='?', default=self.credential)
        add_action_method_parser.add_argument("tunnel", nargs="?", default=self.tunnel)
        add_action_method_parser.set_defaults(func=self.target.methods.append)

        # 'set' parsers
        set_action_subparser = set_action_parser.add_subparsers(dest='noun')

        set_action_credential_parser = set_action_subparser.add_parser('credential')
        set_action_credential_parser.add_argument('number', nargs='?', type=int)
    
        set_action_tunnel_parser = set_action_subparser.add_parser('tunnel')
        set_action_tunnel_parser.add_argument('number', nargs='?', type=int)

        set_action_method_parser = set_action_subparser.add_parser('method')
        set_action_method_parser.add_argument('number', nargs='?', type=int)

        # 'unset' parsers
        unset_action_parser.add_argument("setting")

        # Parse options
        try:
            args = parser.parse_args(command)

            if args.action == 'set':
                if args.noun == 'credential':
                    # Update list before checking length
                    self.target.credentials.update()
                    # Get selection
                    if args.number is None:
                        self.show_credentials()
                        try:
                            selection = int(input('ID: '))
                        except ValueError:
                            print_fail("Selection must be a number")
                            return
                    else:
                        selection = args.number
                    # Process selection
                    if selection < len(self.target.credentials):
                        self.credential = self.target.credentials[selection]
                    else:
                        print_fail('Must make selection from list')
                elif args.noun == 'method':
                    # Update list before checking length
                    self.target.methods.update()
                    # Get selection
                    if args.number is None:
                        self.show_methods()
                        try:
                            selection = int(input('ID: '))
                        except ValueError:
                            print_fail("Selection must be a number")
                            return
                    else:
                        selection = args.number
                    # Process selection
                    if selection < len(self.target.methods):
                        self.method = self.target.methods[selection]
                        # Change settings to match selected method
                        self.credential = self.method.cred
                        self.tunnel = self.method.tunnel
                        self.next_parser = 'method'
                    else:
                        print_fail('Must make selection from list')
                elif args.noun == "tunnel":
                    # Update list before checking length
                    self.target.tunnels.update()
                    # Get selection
                    if args.number is None:
                        self.show_tunnels()
                        selection = int(input('ID: '))
                    else:
                        selection = args.number
                    # Process selection
                    if selection < len(self.target.tunnels):
                        self.tunnel = self.target.tunnels[selection]
                    else:
                        print_fail('Must make selection from list!')
            elif args.action == 'add' and args.noun == 'method':
                if not self.credential:
                    print_fail("Credential must be set first")
                else:
                    args.func(**vars(args))
            elif args.action == "unset":
                if args.setting == "credential":
                    self.credential = None
                elif args.setting == "tunnel":
                    self.tunnel = None
            # All other functions will take only correct args
            else:
                args.func(**vars(args))
        except SystemExit:
            pass

    def method_rsh_parser(self, command):
        if command[0] == 'back':
            #self.method.disconnect()
            self.method = None
            self.next_parser = 'target'
            return

        parser = argparse.ArgumentParser(prog='rsh', exit_on_error=False, usage=argparse.SUPPRESS)
        action_subparser = parser.add_subparsers(help='commands', dest="action")

        # Top level
        show_action_parser = action_subparser.add_parser('show')
        add_action_parser = action_subparser.add_parser('add')
        set_action_parser = action_subparser.add_parser('set')
        remove_action_parser = action_subparser.add_parser('remove')
        connect_action_parser = action_subparser.add_parser('connect')
        run_action_parser = action_subparser.add_parser('run')
        shell_action_parser = action_subparser.add_parser('shell')
        get_action_parser = action_subparser.add_parser("get")
        tunnel_action_parser = action_subparser.add_parser("tunnel")

        # 'show' parser
        show_action_subparser = show_action_parser.add_subparsers(dest="noun")
        show_action_targets_parser = show_action_subparser.add_parser('targets')
        show_action_targets_parser.add_argument('--full', dest='full', action="store_true")
        show_action_targets_parser.set_defaults(func=self.show_targets)

        show_action_settings_parser = show_action_subparser.add_parser('settings')
        show_action_settings_parser.set_defaults(func=self.show_settings)

        # Single word actions
        connect_action_parser.set_defaults(func=self.method.connect)

        # 'shell' parser
        shell_action_parser.add_argument('--full', dest="mode", action="store_const", const="full")
        shell_action_parser.add_argument('--lowvis', dest="mode", action="store_const", const="lowvis")
        shell_action_parser.add_argument('--stealth', dest="mode", action="store_const", const="stealth")
        shell_action_parser.set_defaults(func=self.method.shell)

        # 'run' parser
        run_action_parser.add_argument('builtin')
        run_action_parser.set_defaults(func=self.method.builtins)

        # 'get' parser
        get_action_parser.add_argument('file_path', nargs="+")
        #get_action_parser.set_defaults(func=self.method.get_file)

        # "tunnel" parser
        tunnel_action_parser.add_argument("tunnel_type")
        tunnel_action_parser.add_argument("--port", dest="local_port", required=True)
        tunnel_action_parser.set_defaults(func=self.method.build_tunnel)

        # Parse options
        try:
            parsed, unknown = parser.parse_known_args(command)
            # If using a builtin, allow for any args particular to that custom module to get
            # added to argparse automatically.
            try:
                if parsed.builtin:
                    for arg in unknown:
                        if arg.startswith(("-", "--")):
                            # you can pass any arguments to add_argument
                            run_action_parser.add_argument(arg.split('=')[0])
            except AttributeError:
                pass

            # Handle spaces in value wrapped in quotes
            formatted_command = []
            full_name_list = []
            record = False
            for part in command:
                if record is False:
                    # Quoted path with no spaces
                    if part.startswith('"') and part.endswith('"'):
                        formatted_command.append(part[1:-1])
                    # Quoted path WITH spaces
                    elif part.startswith('"'):
                        record = True
                        full_name_list.append(part[1:])
                    else:
                        formatted_command.append(part)
                elif record is True:
                    if part.endswith('"'):
                        full_name_list.append(part[:-1])
                        full_name = ' '.join(full_name_list)
                        formatted_command.append(full_name)
                        record = False
                        full_name_list = []
                    else:
                        full_name_list.append(part)

            args = parser.parse_args(formatted_command)
            if args.action == "get":
                for file in args.file_path:
                    self.method.get_file(file)
            else:
                args.func(**vars(args))
        except SystemExit:
            pass
        except argparse.ArgumentError as err:
            print(err)

    def base_rsh_prompt(self):
        session = PromptSession()
        while True:
            if self.next_parser == '':
                command = session.prompt('RSH:~$ ', completer=FuzzyCompleter(self.rsh.actions), complete_while_typing=True)
            elif self.next_parser == 'target':
                if self.target.hostname and self.target.ip_addr:
                    command = session.prompt(f'RSH({self.target.hostname}/{self.target.ip_addr})$ ',
                        completer=FuzzyCompleter(self.target.actions), complete_while_typing=True)
                elif self.target.hostname and not self.target.ip_addr:
                    command = session.prompt(f'RSH({self.target.hostname})$ ',
                        completer=FuzzyCompleter(self.target.actions), complete_while_typing=True)
                else:
                    command = session.prompt(f'RSH({self.target.ip_addr})$ ',
                        completer=FuzzyCompleter(self.target.actions), complete_while_typing=True)
            elif self.next_parser == 'method':
                connect_status = self.method.connected
                style = Style.from_dict(
                    {
                        "method": "#00aa00",
                    }
                )
                if connect_status is False:
                    command = session.prompt(f'RSH({self.target.hostname}/{self.target.ip_addr})->{self.method.NAME}$ ',
                        completer=FuzzyCompleter(self.method.actions), complete_while_typing=True)
                else:
                    message = [
                            ("class:shell", "RSH("),
                            ("class:host", f"{self.target.hostname}/{self.target.ip_addr}"),
                            ("class:close_paren", ")"),
                            ("class:method", f"->{self.method.NAME}"),
                            ("class:prompt", "$ "),
                        ]
                    command = session.prompt(message, style=style,
                        completer=FuzzyCompleter(self.method.actions), complete_while_typing=True)
            self.rsh_parser_handler(command)


if __name__ == "__main__":
    rsh = RSH()
    try:
        CLI(rsh)
    except ExitPrompt:
        print('Exiting...')
    except KeyboardInterrupt:
        print('Exiting...')
