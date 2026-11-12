#!/usr/bin/env python3
"""Local-only, fixture-only launcher and point-in-time preflight for PR9's demo.

No provisioning, reverse proxy, SSH connection, dependencies, or live trading.
Run with --help for the operator procedure and the limitations.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import socket
import stat
import sys

PORT = 8765
HOST = "127.0.0.1"
TOKEN_NAME = "demo-session-token"
ROOT = Path(__file__).resolve().parent.parent

HELP = """ASAI private demo (simulation only; fixture quotes; no broker)

Usage: python3 ops/demo_private_deploy.py --check|--serve --session-dir /absolute/private/directory

Create the directory beforehand as the service user with mode 0700; no path
component may be a symlink or '..'. --check checks its ownership/mode, absence
of a previous token, and whether a temporary 127.0.0.1:8765 bind succeeds; it
does not start or deploy the server. --serve
binds the same fixed address and writes its new token to demo-session-token in
that directory, exclusively and with mode 0600. It never prints the token.
The launcher attempts to remove the token on normal shutdown, Ctrl-C, and
handled SIGTERM. A crash, startup interruption, or kill -9 can leave it
behind; remove any stale file securely before restarting.

Use only a trusted host, repository, account and private client. For a remote
host, an operator may separately establish an authenticated SSH tunnel:
  ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8765:127.0.0.1:8765 SSH_HOST
Use the SAME local port (the demo validates Host and Origin), then visit
http://127.0.0.1:8765/ and privately transfer the token file to that client
without exposing it to logs, command arguments, shell history or other users.
Protect any local copy and remove it after use. Do not use a public proxy,
container port publication, SSH gateway ports, or untrusted network forwarding.
Loopback access is not isolation from other users/processes on either host.
Trust the account and all directory ancestors: the final directory must not be
modified concurrently, even by the same user. Cleanup checks file identity but
cannot atomically unlink only that identity against a hostile directory writer.
The checks cannot detect remote forwarding, NAT, proxy rules, privilege or
host compromise, or guarantee the port stays free after --check. They do not
prove a remote host is safe. A successful check is not a deployment.
"""


class SafeFailure(Exception):
    pass


def validate_directory(fd: int) -> None:
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise SafeFailure("Private directory must be owned by the current user and mode 0700.")


def private_directory(path: str) -> int:
    if (not os.path.isabs(path) or ".." in path.split("/") or
            not all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC"))):
        raise SafeFailure("A supported absolute private directory is required.")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = -1
    try:
        fd = os.open("/", flags)
        for component in path.split("/"):
            if not component or component == ".":
                continue
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        validate_directory(fd)
        try:
            os.stat(TOKEN_NAME, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise SafeFailure("Token file already exists; inspect and remove any stale file first.")
        return fd
    except OSError:
        if fd >= 0:
            os.close(fd)
        raise SafeFailure("Cannot safely open the private directory.") from None
    except BaseException:
        if fd >= 0:
            os.close(fd)
        raise


def check_port() -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((HOST, PORT))
    except OSError:
        raise SafeFailure("Cannot bind the required loopback port 8765.") from None


def write_token(dir_fd: int, token: str) -> int:
    # Retain the open descriptor until cleanup so its inode cannot be reused.
    validate_directory(dir_fd)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(TOKEN_NAME, flags, 0o600, dir_fd=dir_fd)
    except OSError:
        raise SafeFailure("Cannot exclusively create the private token file.") from None
    identified = False
    try:
        info = os.fstat(fd)
        identified = True
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise SafeFailure("Token file is not a private regular file.")
        os.fchmod(fd, 0o600)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            raise SafeFailure("Cannot secure token file permissions.")
        data = (token + "\n").encode("ascii")
        while data:
            count = os.write(fd, data)
            if count <= 0:
                raise OSError("short token write")
            data = data[count:]
        os.fsync(fd)
        return fd
    except BaseException:
        try:
            if identified:
                remove_token(dir_fd, fd)
        finally:
            os.close(fd)
        raise


def remove_token(dir_fd: int, token_fd: int) -> None:
    # This comparison is not atomic with unlink. A same-user hostile writer
    # of the directory is outside the trust boundary, as noted in --help.
    held = os.fstat(token_fd)
    try:
        info = os.stat(TOKEN_NAME, dir_fd=dir_fd, follow_symlinks=False)
        if (info.st_dev, info.st_ino) == (held.st_dev, held.st_ino):
            os.unlink(TOKEN_NAME, dir_fd=dir_fd)
    except FileNotFoundError:
        pass


def serve(dir_fd: int) -> None:
    # The repo is trusted code, not a sandbox. Do not use demo.server.main(): it
    # prints the token. Fixed fixture mode never reads provider credentials.
    sys.path.insert(0, str(ROOT))
    from demo.server import DemoRequestHandler, INDEX_PATH, make_server

    class PrivateHandler(DemoRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/":
                return super().do_GET()
            if not self._check_host():
                return
            try:
                data = INDEX_PATH.read_bytes().replace(
                    b"Paste the session token printed by the local server.",
                    b"Paste the session token from the private token file.",
                )
            except OSError:
                self._error(500, "ui_unavailable")
                return
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(data)
            except OSError:
                self.close_connection = True

        # Early POST rejection in the underlying handler leaves the body
        # unread. Close each POST so those bytes cannot become a new request.
        def do_POST(self) -> None:
            self.close_connection = True
            super().do_POST()

        def end_headers(self) -> None:
            if getattr(self, "command", None) == "POST":
                self.send_header("Connection", "close")
            super().end_headers()

        def send_error(self, code: int, message: str | None = None,
                       explain: str | None = None) -> None:
            # BaseHTTPRequestHandler's parser embeds raw request text in some
            # errors; never reflect a malformed request or secret to the page.
            super().send_error(code)

    try:
        server = make_server(PORT, "fixture")
    except OSError:
        raise SafeFailure("Cannot bind the required loopback port 8765.") from None
    token_fd = None
    previous_sigterm = None
    try:
        if server.server_address != (HOST, PORT):
            raise SafeFailure("The server did not bind the required loopback address.")
        if not hasattr(signal, "pthread_sigmask"):
            raise SafeFailure("Signal masking is required for safe token creation.")
        # BaseServer otherwise logs unhandled handler tracebacks, which may
        # contain sensitive request details. Never log request data.
        server.handle_error = lambda _request, _address: None
        server.RequestHandlerClass = PrivateHandler
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def stop(_signum: int, _frame: object) -> None:
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop)
        # No handled shutdown can land between exclusive creation and recording
        # the descriptor. Pending signals are delivered after it is recorded.
        old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            token_fd = write_token(dir_fd, server.session_token)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
        print("Simulator running on 127.0.0.1:8765; fixture quotes only. Token is in the private directory.", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if token_fd is not None:
                try:
                    remove_token(dir_fd, token_fd)
                finally:
                    os.close(token_fd)
        finally:
            try:
                server.server_close()
            finally:
                if previous_sigterm is not None:
                    signal.signal(signal.SIGTERM, previous_sigterm)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--help"] or args == ["-h"]:
        print(HELP, end="")
        return 0
    if len(args) != 3 or args[0] not in ("--check", "--serve") or args[1] != "--session-dir":
        print("Invalid arguments; use --help. No deployment was performed.", file=sys.stderr)
        return 2
    try:
        fd = private_directory(args[2])
        try:
            if args[0] == "--check":
                check_port()
                print("Preflight passed for the local directory and current loopback bind; no deployment performed.")
            else:
                serve(fd)
        finally:
            os.close(fd)
        return 0
    except SafeFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception:
        # Do not print exception text, paths, request data, environment, or tokens.
        print("Private demo failed; no details logged. Check local configuration safely.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
