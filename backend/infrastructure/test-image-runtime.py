import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXPECTED = "sha256:efa53edd08c54786bb7e04cc2509b6ace31ff903d1a2c473f203548b2e4d6d12"
PROBE = r"""
import errno
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import zlib


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": type(error).__name__}


def elf_paths(path):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("ELF inspection size limit exceeded")
    data = path.read_bytes()
    if data[:4] != b"\x7fELF":
        return {"format": "not ELF", "search_paths": []}
    if data[4] not in (1, 2) or data[5] not in (1, 2):
        raise ValueError("Unsupported ELF encoding")
    endian = "<" if data[5] == 1 else ">"
    wide = data[4] == 2

    def read(fmt, offset):
        return struct.unpack_from(endian + fmt, data, offset)

    phoff = read("Q" if wide else "I", 32 if wide else 28)[0]
    entry_size, count = read("HH", 54 if wide else 42)
    if entry_size < (56 if wide else 32) or count == 65535:
        raise ValueError("Unsupported ELF program headers")
    loads, dynamics = [], []
    for index in range(count):
        entry = phoff + index * entry_size
        kind = read("I", entry)[0]
        offset, address = read("QQ" if wide else "II", entry + (8 if wide else 4))
        size = read("Q" if wide else "I", entry + (32 if wide else 16))[0]
        if offset + size > len(data):
            raise ValueError("ELF segment outside file")
        if kind == 1:
            loads.append((address, size, offset))
        elif kind == 2:
            dynamics.append((offset, size))
    strings, string_size, paths = None, None, []
    stride = 16 if wide else 8
    for offset, size in dynamics:
        for pos in range(offset, offset + size - stride + 1, stride):
            tag, value = read("qQ" if wide else "iI", pos)
            if tag == 0:
                break
            if tag == 5:
                strings = value
            elif tag == 10:
                string_size = value
            elif tag in (15, 29):
                paths.append((tag, value))
    result = []
    if paths:
        if strings is None or string_size is None:
            raise ValueError("Missing ELF string table")
        load = next(
            (
                item
                for item in loads
                if item[0] <= strings and strings + string_size <= item[0] + item[1]
            ),
            None,
        )
        if load is None:
            raise ValueError("ELF string table outside load segment")
        base = load[2] + strings - load[0]
        for tag, offset in paths:
            if offset >= string_size:
                raise ValueError("ELF path outside string table")
            end = data.find(b"\0", base + offset, base + string_size)
            if end < 0:
                raise ValueError("Unterminated ELF path")
            result.append(
                {
                    "tag": "DT_RPATH" if tag == 15 else "DT_RUNPATH",
                    "value": data[base + offset : end].decode(
                        "utf-8", errors="backslashreplace"
                    ),
                }
            )
    return {"format": "ELF64" if wide else "ELF32", "search_paths": result}


roots = sorted(
    {
        str(Path(name).resolve())
        for name in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/opt", "/app")
        if Path(name).exists()
    }
)
roots = [
    root
    for root in roots
    if not any(root.startswith(other + "/") for other in roots if root != other)
]
seen, privileged, errors = set(), [], []
for root in roots:
    for folder, directories, files in os.walk(
        root,
        followlinks=False,
        onerror=lambda error: errors.append(
            {"path": error.filename, "error": type(error).__name__}
        ),
    ):
        for name in files:
            path = Path(folder) / name
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) in seen:
                    continue
                seen.add((info.st_dev, info.st_ino))
                privilege_bits = info.st_mode & (stat.S_ISUID | stat.S_ISGID)
                if not privilege_bits and not info.st_mode & 0o111:
                    continue
                try:
                    capabilities = os.getxattr(path, "security.capability").hex()
                except OSError as error:
                    if error.errno not in (errno.ENODATA, errno.ENOTSUP):
                        errors.append(
                            {
                                "path": str(path),
                                "error": "capability_" + type(error).__name__,
                            }
                        )
                    capabilities = ""
                if privilege_bits or capabilities:
                    item = {
                        "path": str(path),
                        "mode": oct(stat.S_IMODE(info.st_mode)),
                        "uid": info.st_uid,
                        "gid": info.st_gid,
                        "file_capabilities_hex": capabilities,
                    }
                    try:
                        item.update(elf_paths(path))
                    except (OSError, ValueError, IndexError, struct.error) as error:
                        item["inspection_error"] = str(error)
                    privileged.append(item)
            except OSError as error:
                errors.append({"path": str(path), "error": type(error).__name__})
report = {
    "effective_uid": os.geteuid(),
    "glibc_runtime": os.confstr("CS_GNU_LIBC_VERSION"),
    "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
    "zlib_build": zlib.ZLIB_VERSION,
    "packages": command(
        [
            "dpkg-query",
            "-W",
            "-f=${binary:Package}\t${Status}\t${Version}\n",
            "libc6",
            "libc-bin",
            "zlib1g",
            "perl-base",
            "perl",
            "perl-modules-5.40",
        ]
    ),
    "pod_text": command(
        [
            "perl",
            "-MPod::Text",
            "-e",
            "print qq(Pod::Text version: $Pod::Text::VERSION\n)",
        ]
    ),
    "scanned_roots": roots,
    "privileged_files": sorted(privileged, key=lambda item: item["path"]),
    "inspection_errors": errors,
    "scope": ("Image inventory only. Binaries are read, not executed. "
              "Probe restrictions do not establish future AWS runtime controls."),
}
print(json.dumps(report))
"""


def checked(args, timeout):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or "Command failed.").strip())
    return result.stdout


def main():
    if len(sys.argv) != 1:
        raise RuntimeError("Run this script without arguments.")
    if not shutil.which("docker"):
        raise RuntimeError("Docker Desktop is required.")
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
        raise RuntimeError(
            "Unset DOCKER_HOST and DOCKER_CONTEXT before inspecting the local image."
        )
    context = checked(["docker", "context", "show"], 20).strip()
    endpoint = checked(
        ["docker", "context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}"], 20
    ).strip()
    if not endpoint.startswith("unix://"):
        raise RuntimeError("Expected the local Docker Desktop engine.")
    image = json.loads(checked(["docker", "image", "inspect", EXPECTED], 30))[0]
    if (image.get("Id"), image.get("Os"), image.get("Architecture")) != (
        EXPECTED,
        "linux",
        "amd64",
    ):
        raise RuntimeError("Local image does not match the accepted linux/amd64 image.")
    if image.get("Config", {}).get("User") != "10001:10001":
        raise RuntimeError("Image runtime user differs from the reviewed Dockerfile.")
    print(
        ("Inspecting the pinned Admin image locally; network disabled, filesystem read-only."),
        flush=True,
    )
    result = json.loads(
        checked(
            [
                "docker",
                "run",
                "--rm",
                "--pull=never",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--entrypoint",
                "python",
                EXPECTED,
                "-I",
                "-B",
                "-c",
                PROBE,
            ],
            120,
        )
    )
    if result.get("effective_uid") != 10001:
        raise RuntimeError("Inspection did not run as the expected non-root user.")
    report = {
        "image_id": EXPECTED,
        "image_created": image.get("Created"),
        "image_user": image["Config"]["User"],
        "os": image["Os"],
        "architecture": image["Architecture"],
        "checked_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "inspection": result,
        "security_acceptance": "pending review",
        "aws_calls": False,
    }
    destination = Path.home() / "Downloads"
    destination.mkdir(exist_ok=True)
    descriptor, filename = tempfile.mkstemp(
        prefix="Fitfinity_Image_Runtime_efa53edd08c5_", suffix=".json", dir=destination
    )
    with os.fdopen(descriptor, "w") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print("RUNTIME_REPORT=" + filename)
    print(
        "Inspection complete. Send this JSON report for vulnerability"
        " review; this is not a security pass."
    )


if __name__ == "__main__":
    try:
        main()
    except (
        RuntimeError,
        OSError,
        ValueError,
        KeyError,
        IndexError,
        subprocess.TimeoutExpired,
    ) as error:
        print("STOPPED: " + str(error), file=sys.stderr)
        sys.exit(1)
