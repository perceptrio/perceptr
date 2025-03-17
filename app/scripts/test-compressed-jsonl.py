import boto3
import gzip
import json
import os
import argparse
import tempfile
from pathlib import Path
from botocore.exceptions import ClientError

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # AWS settings
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    AWS_BUCKET_NAME: str = "perceptr-recordings-dev"

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()


def download_and_decompress_jsonl(s3_path, output_dir=None):
    """
    Download a gzipped JSONL file from S3, decompress it, and save each JSON entry to a separate file.

    Args:
        s3_path: Path to the gzipped JSONL file in S3 (e.g., "org_id/session_id/events.jsonl.gz")
        output_dir: Directory to save the decompressed JSON files (default: temporary directory)

    Returns:
        Path to the directory containing the decompressed JSON files
    """
    # Initialize S3 client
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    bucket_name = settings.AWS_BUCKET_NAME

    # Create output directory if not provided
    if not output_dir:
        output_dir = tempfile.mkdtemp()
    else:
        os.makedirs(output_dir, exist_ok=True)

    print(f"Downloading {s3_path} from bucket {bucket_name}...")

    try:
        # Download the gzipped file
        local_gz_path = os.path.join(output_dir, "events.jsonl.gz")
        s3_client.download_file(bucket_name, s3_path, local_gz_path)

        # Decompress and process each line
        with gzip.open(local_gz_path, "rt") as f:
            # Save uncompressed JSONL file
            jsonl_path = os.path.join(output_dir, "events.jsonl")
            with open(jsonl_path, "w") as jsonl_file:
                for line in f:
                    jsonl_file.write(line)
            # Reset file pointer to beginning for processing individual entries
            f.seek(0)
            for index, line in enumerate(f):
                try:
                    # Parse JSON
                    json_data = json.loads(line.strip())

                    # Save to individual file
                    output_file = os.path.join(output_dir, f"file_{index}.json")
                    with open(output_file, "w") as json_file:
                        json.dump(json_data, json_file, indent=2)

                    print(f"Saved entry {index} to {output_file}")
                except json.JSONDecodeError:
                    print(f"Error parsing JSON at line {index}")

        # Clean up the gzipped file
        os.remove(local_gz_path)

        print(f"Successfully extracted {index + 1} JSON entries to {output_dir}")
        return output_dir

    except ClientError as e:
        print(f"Error downloading file: {e}")
        return None


if __name__ == "__main__":
    # parser = argparse.ArgumentParser(
    #     description="Decompress a gzipped JSONL file from S3 and save each entry as a separate JSON file"
    # )
    # parser.add_argument(
    #     "path",
    #     help="Path to the gzipped JSONL file in S3 (e.g., 'org_id/session_id/events.jsonl.gz')",
    # )
    # parser.add_argument(
    #     "--output-dir", help="Directory to save the decompressed JSON files"
    # )

    # args = parser.parse_args()

    # download_and_decompress_jsonl(args.path, args.output_dir)
    download_and_decompress_jsonl(
        "9/9d48d53c-65a2-4730-babd-d476f4961561/events.jsonl.gz", "test-output"
    )
