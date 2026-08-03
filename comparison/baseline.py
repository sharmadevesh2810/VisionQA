"""
==============================================================================
VisionQA - Baseline Manager
==============================================================================

Copyright (c) 2026 Devesh Sharma.
All Rights Reserved.

Author      : Devesh Sharma
Framework   : VisionQA

Responsible for creating and loading visual baselines.
"""

from pathlib import Path
import shutil


class BaselineManager:

    def __init__(self):

        self.root = Path("baseline")

    def get_baseline_path(
        self,
        environment: str,
        version: str,
    ) -> Path:

        return (
            self.root
            / environment
            / version
        )

    def exists(
        self,
        environment: str,
        version: str,
    ) -> bool:

        return self.get_baseline_path(
            environment,
            version,
        ).exists()

    def create(
        self,
        run_directory: Path,
        environment: str,
        version: str,
    ) -> Path:

        baseline_path = self.get_baseline_path(
            environment,
            version,
        )

        if baseline_path.exists():

            raise FileExistsError(
                f"Baseline already exists: {baseline_path}"
            )

        if baseline_path.exists():

            shutil.rmtree(
                baseline_path
            )

        shutil.copytree(
            run_directory,
            baseline_path,
        )

        return baseline_path

    def load(
        self,
        environment: str,
        version: str,
    ) -> Path:

        return self.get_baseline_path(
            environment,
            version,
        )