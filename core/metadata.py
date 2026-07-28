"""
Metadata Manager

Responsible for creating metadata.json for a snapshot.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.constants import (
    DEFAULT_ENCODING,
    METADATA_FILE,
    VISIONQA_VERSION,
)
from core.logger import Logger


class MetadataManager:
    """
    Creates metadata.json for a snapshot.
    """

    def __init__(
        self,
        snapshot_dir: Path,
    ):

        self.snapshot_dir = snapshot_dir

    @property
    def metadata_path(self) -> Path:
        return self.snapshot_dir / METADATA_FILE

    def write(
        self,
        environment: str,
        version: str,
        tenant: str,
        url: str,
    ) -> Path:
        """
        Create metadata.json.

        Returns
        -------
        Path
            Path to metadata.json
        """

        self.snapshot_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        metadata = {
            "environment": environment,
            "version": version,
            "tenant": tenant,
            "url": url,
            "captured_at": datetime.now().isoformat(),
            "visionqa_version": VISIONQA_VERSION,
        }

        with open(
            self.metadata_path,
            "w",
            encoding=DEFAULT_ENCODING,
        ) as fp:

            json.dump(
                metadata,
                fp,
                indent=4,
                ensure_ascii=False,
            )

        Logger.section("Metadata Manager")

        Logger.kv("Metadata File", self.metadata_path)

        Logger.success("metadata.json created successfully.")

        return self.metadata_path