import os
import docker
from sqlalchemy.exc import IntegrityError
from prompt_toolkit.completion import NestedCompleter
from collections import UserDict, UserList
from redshell import config
from .database import Base, db_session, engine
from .models import Target, Credential, Tunnel, Command
from .methods import MethodsController
from .output_formatter import print_success, print_running, print_fail
from .rshcompleters import AppendTargetCompleter, TargetCompleter, MethodCompleter, CredentialCompleter

class RSH:
    def __init__(self) -> None:
        self.op_path = ''
        self.actions = NestedCompleter.from_nested_dict({
            'show': {
                'targets': {
                    "--full",
                }
            },
            'add': {
                'target': AppendTargetCompleter()
            },
            'remove': {
                'target'
            },
            'set': {
                'target': TargetCompleter()
            },
            'unset': {
                'target'
            },
            'exit': None,
        })

        # Read config
        default_config_path = os.path.join(os.getcwd(), "config.json")
        configuration = config.read_config(default_config_path)

        # Set instance variables
        self.op_path = configuration["op_path"]

        # Make sure op_path exists
        os.makedirs(self.op_path, exist_ok=True)

        # Start SQLite database
        Base.metadata.create_all(bind=engine)
        self.targets = TargetsController(self.op_path)

    @property
    def containers(self) -> dict:
        """
        Returns a dict of methods and container objects started by the RedShell session.
        """

        rsh_containers = {}
        targets = self.targets.items()
        for target in targets:
            _, target_instance = target
            for method in target_instance.methods:
                if method.container:
                    rsh_containers[method] = method.container
        return rsh_containers

class TargetsController(UserDict):
    def __init__(self, op_path):
        self.data = {}
        self.op_path = op_path
        old_db = db_session.query(Target).all()
        for row in old_db:
            if row.hostname:
                self.data[row.hostname] = TargetController(row.id, row.ip_addr, row.hostname, self.op_path)
            else:
                self.data[row.ip_addr] = TargetController(row.id, row.ip_addr, row.hostname, self.op_path)

    def __getitem__(self, key):
        old_db = db_session.query(Target).all()
        for row in old_db:
            # Only create TargetController instance from database row if it doesn't already exist
            # Prevents overwriting existing instances each time the list is referenced
            # This allows better container management (reattach to existing sessions)
            #self.data.setdefault(row.ip_addr, TargetController(row.ip_addr, row.hostname, self.op_path))
            if row.hostname:
                self.data.setdefault(row.hostname, TargetController(row.id, row.ip_addr, row.hostname, self.op_path))
            elif row.ip_addr and not row.hostname:
                self.data.setdefault(row.ip_addr, TargetController(row.id, row.ip_addr, row.hostname, self.op_path))
        return super().__getitem__(key)

    def append(self, ip_addr=None, hostname=None, **_):
        # Take **kwargs to handle arg parser
        # Add target to database
        try:
            target = Target(ip_addr=ip_addr, hostname=hostname)
            #if hostname:
                #if hostname not in self.data.keys():
            db_session.add(target)
            db_session.flush()
                    # commented out to see if it fixes wrong value added to self.data list
                    #self.data[ip_addr] = target
            print_success("Target successfully added")
                #else:
                #    print_fail('This target already exists in the database')
            db_session.flush()
        except IntegrityError:
            db_session.rollback()
            print_fail('This target already exists in the database')
        db_session.commit()

class TargetController:
    def __init__(self, id, ip_addr, hostname, op_path):
        self.id = id
        self.ip_addr = ip_addr
        self.hostname = hostname
        
        # Create engagement_data folder for target
        if self.hostname:
            self.op_path = os.path.join(op_path, self.hostname)
        elif self.ip_addr and not self.hostname:
            self.op_path = os.path.join(op_path, self.ip_addr)

        if not os.path.exists(self.op_path):
            os.makedirs(self.op_path)

        self.credentials = CredentialsController(self)
        self.methods = MethodsController(self)
        self.tunnels = TunnelsController(self)

        self.actions = NestedCompleter.from_nested_dict({
            'show': {
                'credentials': None,
                'methods': None,
                "settings": None,
                "tunnels": None,
                "containers": None,
                "targets": {
                    "--full"
                },
            },
            'add': {
                'credential': CredentialCompleter(),
                "method": MethodCompleter(),
                "tunnel": None,
            },
            'unset': {
                'credential',
                "tunnel",
                'method',
            },
            'set': {
                'credential': None,
                'method': None,
                'tunnel': None,
            },
            'unset': {
                'credential',
                'method',
                'tunnel',
            },
            'back': None,
            'exit': None,
        })

class CredentialsController(UserList):
    def __init__(self, target):
        self.target = target
        self.data = []
        #old_db = database.db_session.query(models.Credential).filter(models.Credential.targets.any(ip_addr=target.ip_addr))
        old_db = db_session.query(Credential).all()
        for row in old_db:
            self.data.append(row)

    """def __getitem__(self, key):
        #old_db = database.db_session.query(models.Credential).filter(models.Credential.targets.any(ip_addr=target.ip_addr))
        print('getting creds')
        old_db = db_session.query(Credential).all()
        for row in old_db:
            self.data.append(row)
        #return self.data[key]
        return super().__getitem__(key)"""

    def append(self, username, ctype, cred, domain=None, origin="Manual", **_):
        if db_session.query(Credential).filter(Credential.username==username, Credential.ctype==ctype, Credential.cred==cred, Credential.domain==domain, Credential.origin==origin).count() == 0:
            credential = Credential(username=username, ctype=ctype, cred=cred, domain=domain, origin=origin)
            target_obj = db_session.query(Target).filter(Target.id==self.target.id).one()
            
            # Add to database
            target_obj.credentials.append(credential)
            db_session.commit()

            # Append to instance list
            self.data.append(credential)
            print_success("Credential successfully added")
        else:
            print_fail('This credential already exists in the database')

    def update(self) -> None:
        old_db = db_session.query(Credential).all()
        for row in old_db:
            # Don't append if already there
            if row not in self.data:
                self.data.append(row)

class TunnelsController(UserList):
    def __init__(self, target):
        self.target = target
        self.data = []
        #old_db = database.db_session.query(models.Credential).filter(models.Credential.targets.any(ip_addr=target.ip_addr))
        old_db = db_session.query(Tunnel).all()
        for row in old_db:
            self.data.append(row)

    def append(self, ip_addr, port, tunnel_type, **_):
        if db_session.query(Tunnel).filter(Tunnel.ip_addr==ip_addr, Tunnel.port==port, Tunnel.tunnel_type==tunnel_type).count() == 0:
            tunnel = Tunnel(ip_addr=ip_addr, port=port, tunnel_type=tunnel_type)
            #target_obj = db_session.query(Target).filter(Target.ip_addr==self.target.ip_addr).one()
            
            # Add to database
            #target_obj.credentials.append(credential)
            db_session.add(tunnel)
            db_session.commit()

            # Append to instance list
            self.data.append(tunnel)
            print_success("Tunnel successfully added")
        else:
            print_fail('This tunnel already exists in the database')

    def update(self) -> None:
        old_db = db_session.query(Tunnel).all()
        for row in old_db:
            # Don't append if already there
            if row not in self.data:
                self.data.append(row)

#class CommandsController(UserList):
#    def __init__(self, target):
#        self.target = target
#        self.data = []
#        old_db = db_session.query(Command).all()
#        for row in old_db:
#            self.data.append(row)
#
#    def append(self, command_line, result, **_):
#        if db_session.query(Command).filter(Tunnel.ip_addr==ip_addr, Tunnel.port==port, Tunnel.tunnel_type==tunnel_type).count() == 0:
#            tunnel = Tunnel(ip_addr=ip_addr, port=port, tunnel_type=tunnel_type)
#            #target_obj = db_session.query(Target).filter(Target.ip_addr==self.target.ip_addr).one()
#            
#            # Add to database
#            #target_obj.credentials.append(credential)
#            db_session.add(tunnel)
#            db_session.commit()
#
#            # Append to instance list
#            self.data.append(tunnel)
#            print(f"[+] Tunnel successfully added")
#        else:
#            print('[!] This tunnel already exists in the database')
#
#    def update(self) -> None:
#        old_db = db_session.query(Tunnel).all()
#        for row in old_db:
#            # Don't append if already there
#            if row not in self.data:
#                self.data.append(row)
