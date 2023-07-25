import os
import random
import string
import traceback
import shutil
from importlib import util
from collections import UserList
import docker
from docker import errors
from redshell import config
from redshell.output_formatter import print_success, print_running, print_fail
from redshell.database import db_session
from redshell.methods.builtins import BuiltinBase
from redshell.models import Method, Target, Command


class MethodsController(UserList):
    # Have to pass target object to access it in the plugin
    def __init__(self, target) -> None:
        self.target = target
        self.data = []
        self.method_list = { method.NAME: method for method in MethodBase.methods }
        old_db = db_session.query(Method).filter(Method.target_id==self.target.id).all()
        # For each database entry, create method instance with its attributes
        for row in old_db:
            self.data.append(self.method_list[row.method_type](self.target, row.credential, row.tunnel, row))

    '''
    def __getitem__(self, key):
        print('get')
        old_db = db_session.query(Method).filter(Method.target_ip_addr==self.target.ip_addr).any()
        #old_db = db_session.query(Method).all()
        for row in old_db:
            self.data.append(row)
        return self.data[key]
        #return super().__getitem__(key)
    '''

    def append(self, method, cred, tunnel, **_):
        if method in self.method_list.keys():
            # Handle 'tunnel' being None
            if tunnel is not None:
                query_logic = db_session.query(Method).filter(Method.method_type==method,Method.target_id==self.target.id,Method.cred_id==cred.id,Method.tunnel_id==tunnel.id).count()
            else:
                query_logic = db_session.query(Method).filter(Method.method_type==method,Method.target_id==self.target.id,Method.cred_id==cred.id,Method.tunnel_id==None).count()
            # If not already in database
            if  query_logic == 0:
                # Create/commit to Method Association table
                new_method = Method(method_type=method)
                new_method.credential = cred
                new_method.tunnel = tunnel
                new_method.status = "Unused"
                target_model = db_session.query(Target).filter(Target.id==self.target.id).one()
                target_model.methods.append(new_method)
                db_session.commit()

                # Create and add method instance to list
                self.data.append(self.method_list[method](self.target, cred, tunnel, new_method))
                print_success("Method successfully added")
            else:
                print_fail('This method already exists in the database')

    def update(self) -> None:
        old_db = db_session.query(Method).filter(Method.target_id==self.target.id).all()
        # For each database entry, create method instance with its attributes
        for row in old_db:
            # Check against existing method objects, only add if they are new
            for method_obj in self.data:
                if method_obj.table_instance != row:
                    self.data.append(self.method_list[row.method_type](self.target, row.credential, row.tunnel, row))
                    break


class MethodBase:
    methods = []

    # For every class that inherits from the current,
    # the class name will be added to plugins
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.methods.append(cls)
        cls.count = 0
        required_methods = ["connect"]
        for f in required_methods:
            if getattr(cls, f) is getattr(__class__, f):
                raise NotImplementedError("Methods must implement")

    def docker_build(self):
        for file in os.listdir("./images"):
            full_path = os.path.abspath(f"./images/{file}")
            shutil.copy(full_path, self.docker_path)
        self.docker_tag = f"rsh_{self.NAME}_{self.cred.username.lower()}_{self.cred.ctype}"
        if self.tunnel:
            self.proxychains_build()
        self.client = docker.from_env()
        self.client.images.build(path=self.docker_path, tag=self.docker_tag)
        #print("[+] Build successful")

    def proxychains_build(self):
        proxychains_config_path = os.path.join(self.docker_path, "proxychains.conf")
        with open(proxychains_config_path, "a", encoding="utf-8") as file:
            file.write(f"\nsocks4 {self.tunnel.ip_addr} {self.tunnel.port}")

    def write_command_to_db(self, command_line, result):
        command = Command(command_line=command_line, result=result)
        target_model = db_session.query(Target).filter(Target.id==self.target.id).one()
        target_model.commands.append(command)
        db_session.commit()

    def connect(self):
        pass

    def run_command(self, command):
        print_fail("This method cannot run commands")

    def shell(self, **_):
        print_fail("This method cannot start a shell")

    def name_generator(self) -> str:
        random_value = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        if self.hostname:
            container_name = f"{self.hostname}_{self.NAME}_{random_value}"
        else:
            container_name = f"{self.ip_addr}_{self.NAME}_{random_value}"
        return container_name

    def builtins(self, builtin, **kwargs):
        builtin_list = BuiltinBase.builtins
        builtin_dict = {builtin.NAME: builtin for builtin in builtin_list}
        if self.connected is True:
            if builtin in builtin_dict.keys():
                print_running(f"Running {builtin} builtin...")
                chosen_builtin = builtin_dict[builtin](method=self)
                try:
                    chosen_builtin.run(**kwargs)
                    print()
                    print_success(f"{builtin} builtin complete")
                except Exception as exc:
                    print(exc)
                    print()
                    print_fail(f"{builtin} builtin failed")
            else:
                print_fail("No builtin by that name")
        else:
            print_fail("Method is not connected")

    def build_tunnel(self):
        pass

    def disconnect(self):
        if self.container == None:
            return
        try:
            print_running("Removing containers...")
            self.container.stop()
            self.container.remove()
        except errors.NotFound:
            pass
        except AttributeError:
            pass


def load_module(module_path):
    """Utility to automatically load modules."""
    name = os.path.split(module_path)[-1]
    spec = util.spec_from_file_location(name, module_path)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Get current path
path = os.path.abspath(__file__)
dirpath = os.path.dirname(path)

for fname in os.listdir(dirpath):
    # Load only "real modules"
    if (
        not fname.startswith(".")
        and not fname.startswith("__")
        and fname.endswith(".py")
    ):
        try:
            load_module(os.path.join(dirpath, fname))
        except OSError:
            traceback.print_exc()