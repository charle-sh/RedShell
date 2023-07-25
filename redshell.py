import argparse
from redshell import RSH
from redshell.cli import CLI, ExitPrompt

def script_parser(script_path):

    rsh = RSH()
    parser = CLI(rsh, interactive=False)

    with open(script_path, 'r') as file:
        commands = file.readlines()

    for command in commands:
        parser.rsh_parser_handler(command)

    try:
        for item in rsh.containers.items():
            method, _ = item
            method.disconnect()
    # Handle no method set yet
    except AttributeError:
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--script", type=str)
    args = parser.parse_args()

    if args.script:
        script_parser(args.script)
    else:
        rsh = RSH()
        try:
            CLI(rsh)
        except ExitPrompt:
            print('Exiting...')
        except KeyboardInterrupt:
            print('Exiting...')
