from typing import Optional, cast

import boto3
from botocore.exceptions import ClientError
from common.services.logger import logger
from fastapi import HTTPException, status
from settings import settings


class S3Service:
    def __init__(self) -> None:
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        self.bucket_name = settings.AWS_BUCKET_NAME

    def generate_presigned_url(
        self,
        file_path: str,
        operation: str,
        expiration: int = 3600,
        extra_args: Optional[dict] = None,
    ) -> str:
        """
        Generate a presigned URL for various S3 operations.

        Args:
            file_path: The path to the file in S3
            operation: S3 operation ('get_object', 'put_object', 'delete_object')
            expiration: URL expiration time in seconds (default: 1 hour)
            extra_args: Additional arguments for the operation
        """
        try:
            params = {"Bucket": self.bucket_name, "Key": file_path}
            if extra_args:
                params.update(extra_args)

            url = self.s3_client.generate_presigned_url(
                ClientMethod=operation, Params=params, ExpiresIn=expiration
            )
            return cast(str, url)
        except ClientError as e:
            logger.error(f"Error generating presigned URL", exc_info=e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="could not generate presigned URL",
            )

    def get_download_url(self, file_path: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for downloading a file."""
        return self.generate_presigned_url(file_path, "get_object", expiration)

    def get_upload_url(
        self, file_path: str, content_type: str, expiration: int = 3600
    ) -> str:
        """
        Generate a presigned URL for uploading a photo or video file.

        Args:
            file_path: The path where the file will be stored in S3
            content_type: The MIME type of the file (must be image/* or video/*)
            expiration: URL expiration time in seconds (default: 1 hour)

        Raises:
            HTTPException: If content type is not an accepted image or video format
        """
        # Validate content type
        if not (
            content_type.startswith("image/")
            or content_type.startswith("video/")
            or content_type == "application/json"
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only image and video files are allowed",
            )

        extra_args = {"ContentType": content_type}
        print(extra_args)
        return self.generate_presigned_url(
            file_path, "put_object", expiration, extra_args
        )

    def get_delete_url(self, file_path: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for deleting a file."""
        return self.generate_presigned_url(file_path, "delete_object", expiration)

    def check_file_exists(self, file_path: str) -> bool:
        """Check if a file exists in S3."""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=file_path)
            return True
        except ClientError:
            return False

    def delete_file(self, file_path: str) -> None:
        """Delete a file from S3."""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_path)
        except ClientError as e:
            logger.error(f"Error deleting file", exc_info=e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="could not delete file",
            )

    def download_file(self, file_path: str) -> bytes:
        """Download a file from S3."""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=file_path)
            return cast(bytes, response["Body"].read())
        except ClientError as e:
            logger.error(f"Error downloading file", exc_info=e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="could not download file",
            )

    def upload_file(self, file_path: str, content: bytes) -> None:
        """Upload a file to S3."""
        self.s3_client.put_object(Bucket=self.bucket_name, Key=file_path, Body=content)

    def list_folder_contents(
        self, folder_path: str, recursive: bool = True
    ) -> list[dict]:
        """
        List contents of a folder in S3.

        Args:
            folder_path: Path to the folder (prefix) in S3
            recursive: If True, list contents recursively
        """
        try:
            # Ensure folder_path ends with '/'
            if not folder_path.endswith("/"):
                folder_path += "/"

            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=folder_path,
                Delimiter="" if recursive else "/",
            )

            contents = []
            for page in pages:
                if "Contents" in page:
                    for item in page["Contents"]:
                        contents.append(
                            {
                                "key": item["Key"],
                                "size": item["Size"],
                                "last_modified": item["LastModified"],
                                "type": "file",
                            }
                        )

                # Include folders (CommonPrefixes) when not recursive
                if not recursive and "CommonPrefixes" in page:
                    for prefix in page["CommonPrefixes"]:
                        contents.append({"key": prefix["Prefix"], "type": "folder"})

            return contents
        except ClientError as e:
            logger.error(f"Error listing folder contents", exc_info=e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="could not list folder contents",
            )

    def delete_folder(self, folder_path: str) -> None:
        """Delete a folder and all its contents from S3."""
        try:
            # List all objects in the folder
            objects = self.list_folder_contents(folder_path)

            if not objects:
                return

            # Delete objects in batches of 1000 (S3 limit)
            delete_keys = [{"Key": obj["key"]} for obj in objects]
            for i in range(0, len(delete_keys), 1000):
                batch = delete_keys[i : i + 1000]
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name, Delete={"Objects": batch}
                )
        except ClientError as e:
            logger.error(f"could not delete folder", exc_info=e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="could not delete folder",
            )

    def get_s3_client(self) -> boto3.client:
        return self.s3_client


s3_service = S3Service()
