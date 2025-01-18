from typing import Optional
import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from common.services.logger import logger
from settings import settings

class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        self.bucket_name = settings.AWS_BUCKET_NAME


    def generate_presigned_url(
        self,
        file_path: str,
        operation: str,
        expiration: int = 3600,
        extra_args: Optional[dict] = None
    ) -> str:
        """
        Generate a presigned URL for various S3 operations.
        
        Args:
            file_path: The path to the file in S3
            operation: S3 operation ('get_object', 'put_object', 'delete_object')
            expiration: URL expiration time in seconds (default: 1 hour)
            extra_args: Additional arguments for the operation (e.g., ContentType for uploads)
        """
        try:
            params = {
                'Bucket': self.bucket_name,
                'Key': file_path
            }
            if extra_args:
                params.update(extra_args)

            url = self.s3_client.generate_presigned_url(
                ClientMethod=operation,
                Params=params,
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"could not generate presigned URL"
            )

    def get_download_url(self, file_path: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for downloading a file."""
        return self.generate_presigned_url(file_path, 'get_object', expiration)

    def get_upload_url(
        self,
        file_path: str,
        content_type: str,
        expiration: int = 3600
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
        if not (content_type.startswith('image/') or content_type.startswith('video/')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only image and video files are allowed"
            )
            
        extra_args = {'ContentType': content_type}
        print(extra_args)
        return self.generate_presigned_url(
            file_path,
            'put_object',
            expiration,
            extra_args
        )

    def get_delete_url(self, file_path: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for deleting a file."""
        return self.generate_presigned_url(file_path, 'delete_object', expiration)

    def list_folder_contents(
        self,
        folder_path: str,
        recursive: bool = True
    ) -> list[dict]:
        """
        List contents of a folder in S3.
        
        Args:
            folder_path: Path to the folder (prefix) in S3
            recursive: If True, list contents recursively
        """
        try:
            # Ensure folder_path ends with '/'
            if not folder_path.endswith('/'):
                folder_path += '/'

            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=folder_path,
                Delimiter='' if recursive else '/'
            )

            contents = []
            for page in pages:
                if 'Contents' in page:
                    for item in page['Contents']:
                        contents.append({
                            'key': item['Key'],
                            'size': item['Size'],
                            'last_modified': item['LastModified'],
                            'type': 'file'
                        })
                
                # Include folders (CommonPrefixes) when not recursive
                if not recursive and 'CommonPrefixes' in page:
                    for prefix in page['CommonPrefixes']:
                        contents.append({
                            'key': prefix['Prefix'],
                            'type': 'folder'
                        })

            return contents
        except ClientError as e:
            logger.error(f"Error listing folder contents: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"could not list folder contents"
            )

    def delete_folder(self, folder_path: str) -> None:
        """Delete a folder and all its contents from S3."""
        try:
            # List all objects in the folder
            objects = self.list_folder_contents(folder_path)
            
            if not objects:
                return

            # Delete objects in batches of 1000 (S3 limit)
            delete_keys = [{'Key': obj['key']} for obj in objects]
            for i in range(0, len(delete_keys), 1000):
                batch = delete_keys[i:i + 1000]
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={'Objects': batch}
                )
        except ClientError as e:
            logger.error(f"could not delete folder: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"could not delete folder"
            )

s3_service = S3Service()