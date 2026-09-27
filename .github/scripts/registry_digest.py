"""Select a single registry-qualified digest from Docker image metadata."""

from __future__ import annotations

import json
import re
import sys


def select_registry_digest(digests: object, image: str) -> str:
    """Reject absent, ambiguous or malformed identities; ignore other repositories."""
    if not isinstance(digests, list) or any(
        not isinstance(value, str) for value in digests
    ):
        raise ValueError("expected a list of digest strings")
    matches = [value for value in digests if value.startswith(image + "@")]
    if (
        len(matches) != 1
        or re.fullmatch(re.escape(image) + r"@sha256:[0-9a-f]{64}", matches[0]) is None
    ):
        raise ValueError("expected exactly one SHA-256 digest for the target image")
    return matches[0]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: registry_digest.py REGISTRY_IMAGE")
    try:
        selected = select_registry_digest(json.load(sys.stdin), sys.argv[1])
    except ValueError as error:
        print(f"Registry digest rejected: {error}", file=sys.stderr)
        sys.exit(2)
    print(selected)
