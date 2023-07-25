import os
import re
from typing import Iterable
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.completion.base import CompleteEvent, Completion
from prompt_toolkit.document import Document
from .database import db_session
from redshell import config
from .models import Target
from .methods import MethodBase
from .methods.builtins import BuiltinBase

class AppendTargetCompleter(Completer):
    """
    Custom Prompt Toolkit completer that displays options for appending new targets.
    """
    def get_completions(self, document, complete_event):
        word = document.get_word_before_cursor(WORD=True)
        options_dict = {
            "--ip": "IP address of target",
            "--hostname": "Hostname of target",
            }
        options = list(options_dict.items())

        # Target appending options
        for option in options:
            option_name, meta = option
            # Filter out options already used in argument
            if document.find_backwards(option_name):
                continue
            if option_name.startswith(word):
                yield Completion(
                    option_name,
                    start_position=-len(word),
                    display_meta=meta
                )

class TargetCompleter(Completer):
    """
    Custom Prompt Toolkit completer that displays targets in the database.
    """
    def get_completions(self, document, complete_event):
        word = document.get_word_before_cursor(WORD=True)
        targets = db_session.query(Target).all()

        target_dict = {}

        for target in targets:
            if target.hostname and not target.ip_addr:
                target_dict[target.hostname] = "N/A"
            elif target.hostname and target.ip_addr:
                target_dict[target.hostname] = target.ip_addr
            elif target.ip_addr and not target.hostname:
                target_dict[target.ip_addr] = "N/A"
        for target in target_dict:
            if target.startswith(word):
                yield Completion(
                    target,
                    start_position=-len(word),
                    display_meta=target_dict[target],
                )

class MethodCompleter(Completer):
    """
    Custom Prompt Toolkit completer that displays all valid methods.
    """
    def get_completions(self, document, complete_event):
        word = document.get_word_before_cursor()
        method_list = MethodBase.methods
        for method in method_list:
            if method.NAME.startswith(word):
                yield Completion(
                    method.NAME,
                    start_position=-len(word),
                    display_meta=method.META,
                )

class FilesystemCompleter(Completer):
    def __init__(self, method) -> None:
        self.method = method
        super().__init__()

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterable[Completion]:
        configuration = config.read_config()
        op_path = configuration["op_path"]
        file_tracker = f"{op_path}{self.method.host}/filesystem.txt"
        try:
            with open(file_tracker, "r") as file:
                filesystem = file.read()
        except FileNotFoundError:
            return

        text = document.text_before_cursor

        dirname = os.path.dirname(text)
        basename = os.path.basename(text)

        # Get only files that match
        filesystem = filesystem.split("\n")
        matching_files = []
        for name in filesystem:
            if name.startswith(dirname):
                matching_files.append(name)

        # Need to have it replace the whole filename, not add to the end of what was typed
        # Still need to work on getting it to show the root "/"
        # I think ^^ are fixed now for Linux and Windows, just needs more testing
        for file in matching_files:
            #if dirname != "/":
            #    completion = file[len(dirname) + 1:]
            #else:
            #    completion = file
            completion = file
            yield Completion(
                f'"{completion}"',
                #display=completion[1:-1],
                start_position=(len(text) * -1),
            )

class BuiltinCompleter(Completer):
    """
    Custom Prompt Toolkit completer that dynamically displays all valid builtins and their options.
    """
    def __init__(self, method) -> None:
        self.method = method
        super().__init__()

    def get_completions(self, document, complete_event):
        word = document.get_word_before_cursor(WORD=True)
        # Get list of registered builtins
        builtin_list = BuiltinBase.builtins
        # Filter list based on target OS
        builtin_list_os = []
        for builtin in builtin_list:
            for os in builtin.TARGET_OS:
                if os in self.method.TARGET_OS:
                    builtin_list_os.append(builtin)
        for builtin in builtin_list_os:
            document_split = document.text.split()
            # Find builtin name already typed to know which options to show
            if document.find_backwards(builtin.NAME):
                # Check if builtin has options to avoid NoneType error
                if builtin.OPTIONS is not None:
                    options = list(builtin.OPTIONS.items())
                    for option in options:
                        option_name, meta = option
                        # Filter out options already used in argument
                        if document.find_backwards(option_name):
                            continue
                        if option_name.startswith(word):
                            yield Completion(
                                option_name,
                                start_position=-len(word),
                                display_meta=meta
                            )
            # Pass if iterating and a builtin is already typed out
            elif len(document_split) > 0:
                continue
            # Yield builtin name
            elif builtin.NAME.startswith(word):
                yield Completion(
                    builtin.NAME,
                    start_position=-len(word),
                    display_meta=builtin.META
                )

class CredentialCompleter(Completer):
    """
    Custom Prompt Toolkit completer that aids adding credentials.
    """
    def get_completions(self, document, complete_event):
        word = document.get_word_before_cursor(WORD=True)
        options_dict = {
            "--user": "Username for the credential",
            "--type": "Type of credential",
            "--cred": "Credential value itself",
            "--domain": "Active Directory domain name"
            }
        cred_types_dict = {
            'password': "Plaintext password", 
            'nthash': "Windows NT Hash", 
            'key': "Key"
            }
        options = list(options_dict.items())
        cred_types = list(cred_types_dict.items())

        # Get full text of argument to check for when to put up other options
        # This is basically a custom nested completer
        text = document.text_before_cursor
        split_text = text.split()
        # Make sure list has values
        if len(split_text) == 1:
            # Check if previous word is "--type"
            if split_text[-1] == "--type":
                for cred_type in cred_types:
                    cred_type_name, meta = cred_type
                    if cred_type_name.startswith(word):
                        # Show cred types as completions
                        yield Completion(
                                cred_type_name,
                                start_position=-len(word),
                                display_meta=meta
                            )
                return
        # Moves to this after the cred type starts getting typed
        elif len(split_text) > 1:
            # Check that "--type" is last complete word, make sure it only completes if another
            # type isn't already written down
            if split_text[-1] == "--type" or (split_text[-2] == "--type" and split_text[-1] not in cred_types_dict.keys()):
                for cred_type in cred_types:
                    cred_type_name, meta = cred_type
                    if cred_type_name.startswith(word):
                        yield Completion(
                                cred_type_name,
                                start_position=-len(word),
                                display_meta=meta
                            )
                return

        # Actual credential appending options
        for option in options:
            option_name, meta = option
            # Filter out options already used in argument
            if document.find_backwards(option_name):
                continue
            if option_name.startswith(word):
                yield Completion(
                    option_name,
                    start_position=-len(word),
                    display_meta=meta
                )
