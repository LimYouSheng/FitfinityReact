"""Use Ubuntu's main archive without changing suites, keys or package policy."""

import re
import sys
from pathlib import Path

ARCHIVE = "https://archive.ubuntu.com/ubuntu/"
REVIEWED_ARCHIVES = {
    f"{scheme}://{host}/ubuntu{slash}"
    for scheme in ("http", "https")
    for host in ("azure.archive.ubuntu.com", "us.archive.ubuntu.com", "archive.ubuntu.com")
    for slash in ("", "/")
} | {"mirror+file:/etc/apt/apt-mirrors.txt"}
REVIEWED_SECURITY = {
    f"{scheme}://security.ubuntu.com/ubuntu{slash}"
    for scheme in ("http", "https")
    for slash in ("", "/")
}


def main():
    source = Path(sys.argv[1])
    original = source.read_text()
    replacement = []
    archive_found = False
    uri_field = False
    for line in original.splitlines(keepends=True):
        if line.startswith("#"):
            replacement.append(line)
            continue
        # Deb822 supports continuation lines: reject them for URIs rather than
        # validating only the first URI and leaving an extra repository behind.
        if uri_field and line.startswith((" ", "\t")):
            raise SystemExit("Unexpected Ubuntu source layout; no source changes written")
        match = re.fullmatch(r"(URIs:[ \t]*)([^\r\n]*?)([ \t]*)(\r?\n)?", line, re.I)
        uri_field = match is not None
        if match:
            uri = match[2]
            if uri in REVIEWED_ARCHIVES:
                line = match[1] + ARCHIVE + match[3] + (match[4] or "")
                archive_found = True
            elif uri not in REVIEWED_SECURITY:
                raise SystemExit("Unexpected Ubuntu source layout; no source changes written")
        replacement.append(line)
    if not archive_found:
        raise SystemExit("Unexpected Ubuntu source layout; no source changes written")
    updated = "".join(replacement)
    if updated != original:
        source.write_text(updated)
    print("Browser dependencies: Ubuntu main archive; suites and Signed-By unchanged")


if __name__ == "__main__":
    main()
