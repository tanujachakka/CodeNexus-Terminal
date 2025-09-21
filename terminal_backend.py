# terminal_backend.py
import os
import shutil
import shlex
import psutil
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TerminalBackend")

MAX_CAT_SIZE = 200*1024  # 200 KB

class TerminalBackend:
    def __init__(self, root_dir="sandbox"):
        self.root = os.path.realpath(root_dir)
        os.makedirs(self.root, exist_ok=True)
        self.cwd = self.root  # current working dir (realpath)
        logger.info(f"Sandbox root: {self.root}")

    def _resolve(self, path):
        """Resolve a path (relative or absolute inside sandbox)."""
        if not path or path == ".":
            return self.cwd
        if path.startswith("/"):
            candidate = os.path.join(self.root, path.lstrip("/"))
        else:
            candidate = os.path.join(self.cwd, path)
        candidate = os.path.realpath(candidate)
        if not candidate.startswith(self.root):
            raise PermissionError("Access outside sandbox is not allowed.")
        return candidate

    # --- command handlers ---
    def cmd_pwd(self, args):
        rel = os.path.relpath(self.cwd, self.root)
        return "/" if rel == "." else f"/{rel.replace(os.sep, '/')}"

    def cmd_ls(self, args):
        target = self._resolve(args[0]) if args else self.cwd
        if os.path.isdir(target):
            items = os.listdir(target)
            lines = []
            for name in sorted(items):
                p = os.path.join(target, name)
                suffix = "/" if os.path.isdir(p) else ""
                lines.append(name + suffix)
            return "\n".join(lines) if lines else ""
        else:
            return os.path.basename(target)

    def cmd_cd(self, args):
        if not args:
            self.cwd = self.root
            return ""
        target = self._resolve(args[0])
        if os.path.isdir(target):
            self.cwd = target
            return ""
        else:
            return f"cd: no such directory: {args[0]}"

    def cmd_mkdir(self, args):
        if not args:
            return "mkdir: missing operand"
        path = self._resolve(args[0])
        os.makedirs(path, exist_ok=True)
        return ""

    def cmd_rm(self, args):
        if not args:
            return "rm: missing operand"
        path = self._resolve(args[0])
        # prevent removing root
        if path == self.root:
            return "rm: refusing to remove root sandbox"
        if os.path.isdir(path):
            # allow recursive delete with -r flag
            if "-r" in args or "--recursive" in args:
                shutil.rmtree(path)
                return ""
            else:
                return "rm: is a directory (use -r to remove directories)"
        else:
            os.remove(path)
            return ""

    def cmd_cat(self, args):
        if not args:
            return "cat: missing file operand"
        path = self._resolve(args[0])
        if not os.path.isfile(path):
            return f"cat: {args[0]}: No such file"
        size = os.path.getsize(path)
        if size > MAX_CAT_SIZE:
            return f"cat: file too large ({size} bytes)"
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def cmd_touch(self, args):
        if not args:
            return "touch: missing file operand"
        path = self._resolve(args[0])
        dirp = os.path.dirname(path)
        os.makedirs(dirp, exist_ok=True)
        with open(path, "a"):
            os.utime(path, None)
        return ""

    def cmd_mv(self, args):
        if len(args) < 2:
            return "mv: missing operand"
        src = self._resolve(args[0])
        dst = self._resolve(args[1])
        shutil.move(src, dst)
        return ""

    def cmd_cp(self, args):
        if len(args) < 2:
            return "cp: missing operand"
        src = self._resolve(args[0])
        dst = self._resolve(args[1])
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        return ""

    def cmd_echo(self, args):
        # echo support with optional '>' redirection is handled in execute()
        return " ".join(args)

    def cmd_ps(self, args):
        procs = []
        for p in psutil.process_iter(['pid','name','cpu_percent','memory_percent']):
            try:
                info = p.info
                procs.append(f"{info['pid']:>6} {info['name'][:30]:30} CPU:{info['cpu_percent']:>5} MEM:{info['memory_percent']:>5.1f}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return "\n".join(sorted(procs)[:50])

    def cmd_sysinfo(self, args):
        cpu = psutil.cpu_percent(interval=0.1)
        vm = psutil.virtual_memory()
        return f"CPU: {cpu}%\nMemory: {vm.percent}% ({vm.used//1024**2}MB / {vm.total//1024**2}MB)\nCores: {psutil.cpu_count(logical=True)}"

    def cmd_help(self, args):
        """Displays a list of available commands with descriptions."""
        output = ["Available commands:"]
        for cmd in sorted(self.COMMANDS.keys()):
            desc = self.CMD_DESCRIPTIONS.get(cmd, "No description available.")
            output.append(f"  {cmd:<10} - {desc}")
        return "\n".join(output)

    # mapping
    COMMANDS = {
        "pwd": cmd_pwd,
        "ls": cmd_ls,
        "cd": cmd_cd,
        "mkdir": cmd_mkdir,
        "rm": cmd_rm,
        "cat": cmd_cat,
        "touch": cmd_touch,
        "mv": cmd_mv,
        "cp": cmd_cp,
        "echo": cmd_echo,
        "ps": cmd_ps,
        "sysinfo": cmd_sysinfo,
        "help": cmd_help
    }

    # Descriptions for each command
    CMD_DESCRIPTIONS = {
        "pwd": "Print the current working directory.",
        "ls": "List directory contents.",
        "cd": "Change the current working directory.",
        "mkdir": "Create a new directory.",
        "rm": "Remove files or directories (-r for recursive).",
        "cat": "Display the content of a file.",
        "touch": "Create a new, empty file.",
        "mv": "Move or rename a file or directory.",
        "cp": "Copy files or directories.",
        "echo": "Display a line of text.",
        "ps": "Display a list of running processes.",
        "sysinfo": "Display system information (CPU, memory, cores).",
        "help": "Show this help message."
    }

    def execute(self, raw_cmd):
        """Parse and execute a single command string."""
        # Check for natural language commands first
        nl_cmd = nl_to_cmd(raw_cmd)
        if nl_cmd:
            raw_cmd = nl_cmd

        raw_cmd = raw_cmd.strip()
        if not raw_cmd:
            return ""
        # handle redirection '>'
        try:
            parts = shlex.split(raw_cmd)
        except ValueError as e:
            return f"parse error: {e}"

        if ">" in parts:
            idx = parts.index(">")
            cmd_parts = parts[:idx]
            out_file = parts[idx+1] if idx+1 < len(parts) else None
            if out_file is None:
                return "syntax error near unexpected token '>'"
            out, ok = self._run_command_parts(cmd_parts)
            # write out to file (overwrite)
            target = self._resolve(out_file)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(out)
            return ""  # in shell, redirection suppresses stdout
        else:
            out, ok = self._run_command_parts(parts)
            return out

    def _run_command_parts(self, parts):
        if not parts:
            return "", True
        cmd = parts[0]
        args = parts[1:]
        handler = None
        if cmd in self.COMMANDS:
            handler = self.COMMANDS[cmd]
            try:
                return handler(self, args), True
            except PermissionError as pe:
                return f"PermissionError: {pe}", False
            except Exception as e:
                logger.exception("Error executing command")
                return f"Error: {e}", False
        else:
            return f"{cmd}: command not found", False

def nl_to_cmd(nl):
    nl = nl.strip().lower()
    m = re.match(r'create (?:a )?folder called (.+)', nl)
    if m:
        return f"mkdir {shlex.quote(m.group(1))}"
    m = re.match(r'move (.+) to (.+)', nl)
    if m:
        return f"mv {shlex.quote(m.group(1))} {shlex.quote(m.group(2))}"
    m = re.match(r'create file (.+)', nl)
    if m:
        return f"touch {shlex.quote(m.group(1))}"
    return None

if __name__ == "__main__":
    tb = TerminalBackend()
    while True:
        try:
            s = input(f"{tb.cmd_pwd(None)}$ ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        out = tb.execute(s)
        if out:
            print(out)