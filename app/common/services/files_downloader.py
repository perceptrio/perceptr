import tempfile
import shutil
import os
import boto3
from common.services.logger import logger
from settings import settings

class FilesDownloader:
    def __init__(self, s3_client: boto3.client):
        self.s3_client = s3_client
        self.bucket_name = settings.AWS_BUCKET_NAME
        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"Temporary folder created: {self.temp_dir}")


    def download_file_from_s3(self, key: str) -> str:
        local_file_path = os.path.join(self.temp_dir, os.path.basename(key))
        self.s3_client.download_file(self.bucket_name, key, local_file_path)
        logger.info(f"Downloaded {key} to {local_file_path}")
        return local_file_path


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        shutil.rmtree(self.temp_dir)
        logger.info(f"Temporary folder deleted: {self.temp_dir}")