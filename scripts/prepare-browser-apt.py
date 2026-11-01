"""Use Ubuntu's main archive without changing suites, keys or package policy."""

import re
import sys
from pathlib import Path


def main():
    source = Path(sys.argv[1])
    original = source.read_text()
    replacement = re.sub(
        r"(?m)^(URIs:[ \t]+)(?:https?://(?:azure\.|us\.)archive\.ubuntu\.com/ubuntu/?|"
        r"mirror\+file:/etc/apt/apt-mirrors\.txt)(?=[ \t]*$)",
        r"\1https://archive.ubuntu.com/ubuntu/",
        original,
    )
    if "azure.archive.ubuntu.com" in replacement or not re.search(
        r"(?m)^URIs:[ \t]+https://archive\.ubuntu\.com/ubuntu/[ \t]*$",
        replacement,
    ):
        raise SystemExit("Unexpected Ubuntu source layout; no source changes written")
    if replacement != original:
        source.write_text(replacement)
    print("Browser dependencies: Ubuntu main archive; suites and Signed-By unchanged")


if __name__ == "__main__":
    main()
