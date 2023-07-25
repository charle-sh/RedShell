import os
import json

def build_config(config_path):
    """
    Build default json config file.
    """
    op_path = os.path.join(os.getcwd(), "engagement_data/")
    database_path = os.path.join(op_path, "redshell.db")
    config = {
        "op_path" : op_path,
        "database_path": database_path,
    }
    with open(config_path, "w") as config_file:
        json.dump(config, config_file)

def read_config(config_path: os.PathLike=os.path.join(os.getcwd(), "config.json")) -> dict:
    """
    Read json config file and return contents as a dict.
    """
    with open(config_path, 'r') as config_file:
        config_json = json.load(config_file)
    return config_json