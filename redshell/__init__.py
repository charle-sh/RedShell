import os
from redshell import config

# Create default config if one doesn't exist
default_config_path = os.path.join(os.getcwd(), "config.json")
if not os.path.exists(default_config_path):
    config.build_config(default_config_path)

# Set environment variable for Docker to reach X11 server

#os.environ["HOST_IP"] = 

from .rsh import RSH