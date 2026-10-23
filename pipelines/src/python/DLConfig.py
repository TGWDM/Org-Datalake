import boto3
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


def getTables():
    with psycopg.connect(
        f"dbname={pgName} user={pgUser} password={pgPW} host=127.0.0.1 port=5433"
    ) as pgConn:
        with pgConn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables WHERE table_schema = 'clean'
            """)
            records = cur.fetchall()
            print(records)


getTables()
