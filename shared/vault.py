"""Keep WireGuard profiles encrypted in vpngo's own folder.

`vpngo profile add` copies the .conf into the profiles folder, encrypted with a key the
operating system keeps for this user, so no extra password is needed to use it:

- Linux: systemd-creds --user (systemd 256+), bound to this user on this machine (and to the
  TPM when there is one); without it, the desktop keyring through the Secret Service (secret-tool).
- Windows: DPAPI, bound to the Windows account.
- macOS: the login Keychain.

A plain copy exists only while something needs a file: vopono reads one from a private folder
in memory (XDG_RUNTIME_DIR) that is deleted as soon as the VPN is up. Mihomo's generated
config.yaml (macOS/Windows) still holds the keys while it runs; it stays in vpngo's private
state folder.
"""

import base64
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from apps import AppError, config_dir


STORE = config_dir() / "profiles"
SUFFIXES = {".cred": "systemd-creds", ".keyring": "secret-service", ".dpapi": "dpapi", ".keychain": "keychain"}
ENTROPY = b"vpngo WireGuard profile"


class VaultError(AppError):
    pass


def run(command, data=None):
    try:
        result = subprocess.run(command, input=data, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VaultError(f"{command[0]} failed: {error}") from None
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip() or f"exit code {result.returncode}"
        raise VaultError(f"{command[0]} failed: {detail}")
    return result.stdout


@lru_cache(maxsize=1)
def systemd_user_credentials():
    """systemd 256+ encrypts credentials for an unprivileged user; older ones only for root."""
    if not shutil.which("systemd-creds"):
        return False
    try:
        run(["systemd-creds", "encrypt", "--user", "--name=vpngo-probe", "-", "-"], b"probe")
        return True
    except VaultError:
        return False


def backend():
    if os.name == "nt":
        return "dpapi"
    if sys.platform == "darwin":
        return "keychain"
    if systemd_user_credentials():
        return "systemd-creds"
    if shutil.which("secret-tool"):
        return "secret-service"
    raise VaultError("Cannot encrypt VPN profiles here: vpngo needs systemd 256 or newer (systemd-creds), "
                     "or a desktop keyring with secret-tool (package libsecret).")


def credential_name(name):
    return f"vpngo-profile-{name}"


def dpapi(data, protect):
    """CryptProtectData / CryptUnprotectData for the current Windows user."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(value):
        buffer = ctypes.create_string_buffer(value, len(value))
        return Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.restype = wintypes.BOOL
    source, _source_buffer = blob(data)
    entropy, _entropy_buffer = blob(ENTROPY)
    output = Blob()
    ui_forbidden = 0x1
    description = ctypes.c_wchar_p("vpngo profile") if protect else None
    if not function(ctypes.byref(source), description, ctypes.byref(entropy), None, None, ui_forbidden,
                    ctypes.byref(output)):
        raise VaultError(f"Windows could not {'encrypt' if protect else 'decrypt'} the profile: "
                         f"{ctypes.WinError(ctypes.get_last_error())}")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def private_write(path, data):
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if os.name == "posix":
        path.parent.chmod(0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
    temporary.replace(path)


def seal(name, text):
    """Encrypt a profile's text into the profiles folder; returns the file the registry points to."""
    kind = backend()
    suffix = next(suffix for suffix, value in SUFFIXES.items() if value == kind)
    path = STORE / f"{name}{suffix}"
    data = text.encode("utf-8")
    if kind == "systemd-creds":
        private_write(path, run(["systemd-creds", "encrypt", "--user", f"--name={credential_name(name)}", "-", "-"],
                                data))
    elif kind == "dpapi":
        private_write(path, dpapi(data, protect=True))
    elif kind == "secret-service":
        # Base64, so the keyring cannot change the file's line endings.
        run(["secret-tool", "store", f"--label=vpngo profile {name}", "application", "vpngo", "profile", name],
            base64.b64encode(data))
        private_write(path, b"Stored in the Secret Service keyring (application=vpngo).\n")
    else:
        # `security -i` reads the command from stdin, so the secret never appears in a process list.
        encoded = base64.b64encode(data).decode("ascii")
        run(["security", "-i"], f'add-generic-password -U -a vpngo -s {credential_name(name)} -w "{encoded}"\n'
            .encode("ascii"))
        private_write(path, b"Stored in the login Keychain (service vpngo-profile-<name>).\n")
    if unseal(path) != text:
        discard(path)
        raise VaultError(f"The encrypted copy of profile '{name}' could not be read back; nothing was saved.")
    return path


def unseal(path):
    """The profile's text. A path without a vault suffix is a plain .conf from before v0.7.0."""
    path = Path(path)
    kind = SUFFIXES.get(path.suffix)
    name = path.stem
    if kind is None:
        return path.read_text(encoding="utf-8")
    if kind == "systemd-creds":
        data = run(["systemd-creds", "decrypt", "--user", f"--name={credential_name(name)}", str(path), "-"])
    elif kind == "dpapi":
        data = dpapi(path.read_bytes(), protect=False)
    elif kind == "secret-service":
        data = base64.b64decode(run(["secret-tool", "lookup", "application", "vpngo", "profile", name]).strip())
    else:
        data = base64.b64decode(run(["security", "find-generic-password", "-a", "vpngo", "-s",
                                     credential_name(name), "-w"]).strip())
    return data.decode("utf-8")


def discard(path):
    """Delete a sealed profile, and its keyring entry when it has one."""
    path = Path(path)
    kind = SUFFIXES.get(path.suffix)
    try:
        if kind == "secret-service":
            run(["secret-tool", "clear", "application", "vpngo", "profile", path.stem])
        elif kind == "keychain":
            run(["security", "delete-generic-password", "-a", "vpngo", "-s", credential_name(path.stem)])
    except VaultError:
        pass
    if kind is not None:
        path.unlink(missing_ok=True)


def sealed(path):
    return Path(path).suffix in SUFFIXES


@contextmanager
def plain_file(name, text):
    """A plain .conf for a program that needs a file, in a private folder deleted on exit.

    The folder lives in XDG_RUNTIME_DIR (memory, this user only) when there is one.
    """
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    folder = Path(tempfile.mkdtemp(prefix="vpngo-", dir=base if base.is_dir() else None))
    try:
        os.chmod(folder, 0o700)
        path = folder / f"{name}.conf"
        private_write(path, text.encode("utf-8"))
        yield path
    finally:
        shutil.rmtree(folder, ignore_errors=True)
