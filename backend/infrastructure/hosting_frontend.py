"""Build the exact accepted frontend in isolation with its existing API/PWA owners."""

import base64
import hashlib
import io
import json
import mimetypes
import os
import re
import subprocess
import tarfile
from pathlib import Path

import hosting_design as design
import private_runtime_preflight as pf

ROOT = Path(__file__).parent
require = pf.require


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=90)
    require(result.returncode == 0, "Git verification failed: " + args[0])
    return result.stdout


def source_check(repo, revision=None):
    revision = revision or os.getenv("GITHUB_SHA")
    require(
        isinstance(revision, str) and re.fullmatch(r"[a-f0-9]{40}", revision),
        "Exact release source required",
    )
    require(
        repo.is_dir() and not repo.is_symlink() and repo.resolve() == repo.absolute(),
        "Checkout path is missing or redirected",
    )
    require(
        git(repo, "rev-parse", "--show-toplevel").decode().strip() == str(repo),
        "Use the checkout root",
    )
    require(
        git(repo, "rev-parse", "HEAD").decode().strip() == revision,
        "Checkout HEAD differs from accepted main; preserve local work",
    )
    require(
        not git(repo, "status", "--porcelain=v1", "--untracked-files=all").strip(),
        "Checkout has changes or untracked files; preserve them before deployment",
    )
    expected = {}
    for row in git(repo, "ls-tree", "-r", "-z", revision).decode().split("\0"):
        if row:
            entry, name = row.split("\t", 1)
            mode, kind, sha = entry.split()
            require(kind == "blob", "Non-file source refused")
            expected[name] = {"mode": mode, "sha": sha}
    rows = git(repo, "ls-files", "--stage", "-z").decode().split("\0")
    actual = {}
    for row in filter(None, rows):
        entry, name = row.split("\t", 1)
        mode, sha, stage = entry.split()
        require(
            stage == "0" and mode in {"100644", "100755"}, "Unmerged or redirected source in index"
        )
        actual[name] = {"mode": mode, "sha": sha}
        path = repo
        for part in Path(name).parts:
            require(part not in {"..", "."}, "Unsafe tracked path")
            path /= part
            require(not path.is_symlink(), "Redirected tracked source: " + name)
        raw = path.read_bytes()
        digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(digest == sha, "Tracked source bytes differ: " + name)
    require(actual == expected, "Complete source/index inventory differs from accepted GitHub tree")
    return {
        "revision": revision,
        "source_files": len(actual),
        "git_tree_verified": True,
        "manifest_sha256": manifest_hash(actual),
        "files": actual,
    }


def command(args, cwd, env):
    pf.note("LOCAL " + " ".join(args))
    result = subprocess.run(args, cwd=cwd, env=env, timeout=180)
    require(result.returncode == 0, "Local build/PWA check failed; no upload for this candidate")


def node_environment():
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("VITE_", "FITFINITY_", "npm_config_", "NPM_CONFIG_"))
        and k not in {"NODE_OPTIONS", "NODE_PATH"}
    }
    script = r"""set -e
if ! command -v node >/dev/null 2>&1 ||
   [ "$(node -p 'process.versions.node.split(".")[0]')" != "24" ]; then
  fitfinity_nvm="${NVM_DIR:-$HOME/.nvm}"
  if [ ! -s "$fitfinity_nvm/nvm.sh" ] && [ -n "${XDG_CONFIG_HOME:-}" ]; then
    fitfinity_nvm="$XDG_CONFIG_HOME/nvm"
  fi
  [ -s "$fitfinity_nvm/nvm.sh" ] || {
    echo 'Existing Node 24/nvm is missing. Nothing was installed.' >&2; exit 1;
  }
  . "$fitfinity_nvm/nvm.sh" --no-use
  nvm use 24 >/dev/null || exit 1
fi
node -e '
if(process.versions.node.split(".")[0]!=="24")process.exit(1);
console.log(JSON.stringify({executable:process.execPath,version:process.version}))'
"""
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=30
    )
    require(
        result.returncode == 0,
        "Existing Node 24 could not be activated. No dependencies or shell settings were changed",
    )
    node = json.loads(result.stdout)
    require(
        node["version"].startswith("v24.") and Path(node["executable"]).is_file(),
        "Activated Node runtime differs",
    )
    env["PATH"] = str(Path(node["executable"]).parent) + os.pathsep + env.get("PATH", "")
    return env, node


def build(repo, folder, report, revision=None):
    report["frontend_source"] = source_check(repo, revision)
    require(
        (repo / "node_modules").is_dir() and not (repo / "node_modules").is_symlink(),
        "Existing local dependencies are missing or redirected; nothing was installed",
    )
    env, node = node_environment()
    result = subprocess.run(
        ["npm", "ls", "--all", "--json"], cwd=repo, env=env, capture_output=True, timeout=90
    )
    require(
        result.returncode == 0,
        "Installed dependencies do not satisfy the accepted checkout; no installation attempted",
    )
    report["frontend_dependencies"] = {
        "npm_ls_passed": True,
        "node": node["version"],
        "package_lock_sha256": hashlib.sha256(
            (repo / "package-lock.json").read_bytes()
        ).hexdigest(),
    }
    folder.mkdir(mode=0o700)
    raw = git(repo, "archive", "--format=tar", report["frontend_source"]["revision"])
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            path = Path(member.name)
            require(
                not path.is_absolute()
                and ".." not in path.parts
                and (member.isfile() or member.isdir()),
                "Unsafe Git archive member",
            )
            target = folder / path
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.write_bytes(archive.extractfile(member).read())
    (folder / "node_modules").symlink_to(repo / "node_modules", target_is_directory=True)
    command(["node", "scripts/build-api-test.mjs"], folder, env)
    command(["node", "scripts/verify-pwa.mjs", "dist-api-test", "/"], folder, env)
    output = folder / "dist-api-test"
    manifest = inventory(output)
    # The canonical configurable service can retain an unused demo chunk in API builds.
    # Its pinned build script selects mode=api; do not invent a filename-based mode gate.
    report["frontend_source_after_build"] = source_check(repo, revision)
    report["frontend_build"] = {
        "mode": "api",
        "base_path": "/",
        "api_base_url": "",
        "pwa_verified": True,
        "files": len(manifest),
        "manifest_sha256": manifest_hash(manifest),
    }
    return output, manifest


def inventory(folder):
    require(
        folder.is_dir() and not folder.is_symlink(), "Frontend artifact is missing or redirected"
    )
    result = {}
    for p in sorted(folder.rglob("*")):
        require(not p.is_symlink(), "Frontend artifact contains a symlink")
        if p.is_dir():
            continue
        name = p.relative_to(folder).as_posix()
        require(
            re.fullmatch(r"[A-Za-z0-9_./-]+", name)
            and not any(x.startswith(".") for x in Path(name).parts),
            "Unsafe frontend artifact path",
        )
        require(
            not name.endswith(".map") and p.stat().st_size <= 20 * 1024 * 1024,
            "Unreviewed frontend artifact",
        )
        raw = p.read_bytes()
        digest = hashlib.sha256(raw).digest()
        content_type = (
            {".js": "application/javascript", ".webmanifest": "application/manifest+json"}.get(
                p.suffix
            )
            or mimetypes.guess_type(name)[0]
            or "application/octet-stream"
        )
        result[name] = {
            "sha256": digest.hex(),
            "checksum": base64.b64encode(digest).decode(),
            "bytes": len(raw),
            "content_type": content_type,
            "cache_control": "public,max-age=31536000,immutable"
            if re.match(r"assets/[^/]+-[A-Za-z0-9_-]{8,}\.(js|css)$", name)
            else "no-cache,max-age=0,must-revalidate",
        }
    require(
        {"index.html", "sw.js", "manifest.webmanifest"} <= result.keys(),
        "Incomplete frontend/PWA artifact",
    )
    require(
        3 <= len(result) <= 300 and sum(r["bytes"] for r in result.values()) <= 50 * 1024 * 1024,
        "Frontend artifact outside reviewed budget",
    )
    return result


def manifest_hash(manifest):
    return hashlib.sha256(design.compact(manifest).encode()).hexdigest()


def release(repo, directory, revision):
    """Build once; deployment only consumes the immutable exported files."""
    import shutil

    import hosting_binding as binding
    from private_runtime import atomic_json

    require(not directory.exists(), "Release directory must be new")
    directory.mkdir(mode=0o700)
    report = {"operator_source": revision, "compatibility": binding.compatibility(repo)}
    output, manifest = build(repo, directory / "build", report, revision)
    shutil.copytree(output, directory / "artifact" / "frontend")
    report["manifest"] = manifest
    atomic_json(directory / "artifact" / "release.json", report)
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    release(Path(__file__).resolve().parents[2], args.directory.resolve(), args.revision)
