import boto3
import botocore
from botocore.config import Config
import psycopg
from dotenv import load_dotenv
import os

# Setting credentials
load_dotenv()
rustUser = os.environ["RUSTFS_USER"]
rustPW = os.environ["RUSTFS_PW"]
pgUser = os.environ["PG_USER"]
pgPW = os.environ["PG_PW"]
pgName = os.environ["PG_DB"]


def buildRustClient():
    # Create buck config
    s3 = boto3.client(
        "s3",
        endpoint_url="http://localhost:9000",
        aws_access_key_id=rustUser,
        aws_secret_access_key=rustPW,
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )
    return s3


def existsInS3(s3, buck_name, file_path):
    try:
        s3.head_object(Bucket=buck_name, Key=file_path)
        return True
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise
