from colorama import Fore, Style

def print_success(message):
    #print(f"{Style.BRIGHT}[{Fore.GREEN}+{Fore.RESET}]{Style.RESET_ALL} {message}")
    print(f"{Style.BRIGHT}{Fore.GREEN}[+]{Style.RESET_ALL} {message}")

def print_running(message):
    #print(f"{Style.BRIGHT}[{Fore.BLUE}*{Fore.RESET}]{Style.RESET_ALL} {message}")
    print(f"{Style.BRIGHT}{Fore.BLUE}[*]{Style.RESET_ALL} {message}")

def print_fail(message):
    #print(f"{Style.BRIGHT}[{Fore.RED}!{Fore.RESET}]{Style.RESET_ALL} {message}")
    print(f"{Style.BRIGHT}{Fore.RED}[!]{Style.RESET_ALL} {message}")