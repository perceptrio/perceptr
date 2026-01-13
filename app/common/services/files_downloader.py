import os
import shutil
import tempfile
from typing import Any, Optional

import boto3
from common.services.logger import logger
from settings import settings


class FilesDownloader:
    def __init__(self, s3_client: boto3.client, keep_temp_dir: bool = False):
        self.s3_client = s3_client
        self.bucket_name = settings.AWS_BUCKET_NAME
        self.temp_dir = tempfile.mkdtemp()
        self.keep_temp_dir = keep_temp_dir
        logger.info(f"Temporary folder created: {self.temp_dir}")

    def download_file_from_s3(self, key: str) -> str:
        file_name = os.path.basename(key)
        if file_name.endswith(".quicktime"):
            file_name = file_name.replace(".quicktime", ".mov")
        local_file_path = os.path.join(self.temp_dir, file_name)
        self.s3_client.download_file(self.bucket_name, key, local_file_path)
        logger.info(f"Downloaded {key} to {local_file_path}")
        return local_file_path

    def download_all_session_batches(self, key: str) -> list[str]:
        local_file_paths = []
        response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=key)
        # Handle case when no objects are found (no 'Contents' key in response)
        if "Contents" not in response:
            logger.warning(f"No objects found in S3 for prefix: {key}")
            return local_file_paths

        for obj in response["Contents"]:
            filename = os.path.basename(obj["Key"])
            if filename.startswith("batch_"):
                local_file_path = os.path.join(self.temp_dir, filename)
                self.s3_client.download_file(
                    self.bucket_name, obj["Key"], local_file_path
                )
                local_file_paths.append(local_file_path)
        return local_file_paths

    def get_local_temp_dir(self) -> str:
        return self.temp_dir

    def __enter__(self) -> "FilesDownloader":
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_value: Optional[Exception],
        traceback: Optional[Any],
    ) -> None:
        if not self.keep_temp_dir:
            shutil.rmtree(self.temp_dir)
            logger.info(f"Temporary folder deleted: {self.temp_dir}")
        else:
            logger.info(f"Temporary folder kept: {self.temp_dir}")
