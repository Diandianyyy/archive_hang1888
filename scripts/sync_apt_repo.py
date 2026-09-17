#!/usr/bin/env python3
"""Incrementally archive packages from a Debian-style APT repository."""

from __future__ import annotations

import argparse
import bz2
import gzip
import hashlib
import lzma
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen


USER_AGENT = "hang1888-archive-sync/1.0"
INDEX_CANDIDATES = ("Packages.xz", "Packages.bz2", "Packages.gz", "Packages")


def fetch(url: str, destination: Path | None = None) -> bytes | None:
    encoded_url = quote(url, safe=":/?&=%")
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(encoded_url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=120) as response:
                if destination is None:
                    return response.read()
                with destination.open("wb") as output:
                    shutil.copyfileobj(response, output, length=1024 * 1024)
                return None
        except Exception as error:  # Network errors vary by Python/OpenSSL version.
            last_error = error
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to download {url}: {last_error}")


def load_upstream_index(source: str) -> str:
    base = source.rstrip("/") + "/"
    errors: list[str] = []
    for name in INDEX_CANDIDATES:
        url = urljoin(base, name)
        try:
            payload = fetch(url)
            assert payload is not None
            if name.endswith(".xz"):
                payload = lzma.decompress(payload)
            elif name.endswith(".bz2"):
                payload = bz2.decompress(payload)
            elif name.endswith(".gz"):
                payload = gzip.decompress(payload)
            print(f"Using upstream index: {url}")
            return payload.decode("utf-8", errors="replace")
        except Exception as error:
            errors.append(f"{name}: {error}")
    raise RuntimeError("No readable Packages index found:\n" + "\n".join(errors))


def parse_packages(text: str) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    normalized = text.replace("\r\n", "\n").strip()
    for paragraph in re.split(r"\n\s*\n", normalized):
        fields: dict[str, str] = {}
        current = ""
        for line in paragraph.splitlines():
            if line.startswith((" ", "\t")) and current:
                fields[current] += "\n" + line
                continue
            key, separator, value = line.partition(":")
            if separator:
                current = key
                fields[key] = value.lstrip()
        if fields.get("Package"):
            packages.append(fields)
    return packages


def safe_component(value: str, limit: int = 80) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9.+~_-]", "_", value)
    return (cleaned or "unknown")[:limit]


def existing_hashes() -> set[str]:
    index = Path("Packages")
    if not index.exists():
        return set()
    return {
        package["SHA256"].lower()
        for package in parse_packages(index.read_text(encoding="utf-8", errors="replace"))
        if package.get("SHA256")
    }


def download_package(source: str, package: dict[str, str]) -> Path:
    required = ("Package", "Version", "Architecture", "SHA256", "Filename")
    missing = [field for field in required if not package.get(field)]
    if missing:
        raise ValueError(f"Package entry is missing fields: {', '.join(missing)}")

    digest = package["SHA256"].lower()
    architecture = safe_component(package["Architecture"])
    filename = "_".join(
        (
            safe_component(package["Package"]),
            safe_component(package["Version"]),
            architecture,
            digest,
        )
    ) + ".deb"
    destination_dir = Path("debs") / architecture
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / filename
    package_url = urljoin(source.rstrip("/") + "/", package["Filename"].lstrip("./"))

    with tempfile.NamedTemporaryFile(dir=destination_dir, suffix=".part", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        fetch(package_url, temporary)
        hasher = hashlib.sha256()
        with temporary.open("rb") as downloaded:
            while chunk := downloaded.read(1024 * 1024):
                hasher.update(chunk)
        actual_digest = hasher.hexdigest()
        if actual_digest != digest:
            raise ValueError(
                f"SHA256 mismatch for {package_url}: expected {digest}, got {actual_digest}"
            )
        expected_size = package.get("Size")
        if expected_size and temporary.stat().st_size != int(expected_size):
            raise ValueError(f"Size mismatch for {package_url}")
        subprocess.run(
            ["dpkg-deb", "--info", os.fspath(temporary)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def write_indexes() -> None:
    result = subprocess.run(
        ["apt-ftparchive", "packages", "debs"],
        check=True,
        stdout=subprocess.PIPE,
    )
    paragraphs = [item.strip() for item in result.stdout.split(b"\n\n") if item.strip()]
    payload = b"\n\n".join(sorted(paragraphs)) + (b"\n" if paragraphs else b"")
    Path("Packages").write_bytes(payload)
    Path("Packages.bz2").write_bytes(bz2.compress(payload, compresslevel=9))
    Path("Packages.xz").write_bytes(lzma.compress(payload, preset=9 | lzma.PRESET_EXTREME))
    with Path("Packages.gz").open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as zipped:
            zipped.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--max-downloads", type=int, default=100)
    args = parser.parse_args()
    if args.max_downloads < 0:
        parser.error("--max-downloads must be 0 or greater")

    upstream = parse_packages(load_upstream_index(args.source))
    known = existing_hashes()
    missing: list[dict[str, str]] = []
    queued = set(known)
    for package in upstream:
        digest = package.get("SHA256", "").lower()
        if digest and digest not in queued:
            missing.append(package)
            queued.add(digest)
    selected = missing if args.max_downloads == 0 else missing[: args.max_downloads]
    print(f"Upstream: {len(upstream)} packages; missing: {len(missing)}; this run: {len(selected)}")

    for position, package in enumerate(selected, start=1):
        destination = download_package(args.source, package)
        print(f"[{position}/{len(selected)}] Downloaded {destination}")

    write_indexes()


if __name__ == "__main__":
    main()
