from DLConfig import buildRustClient, existsInS3
from psycopg_pool import ConnectionPool
import pandas as pd
import io
import os
from dotenv import load_dotenv
import json

s3 = buildRustClient()

load_dotenv()
rust_user = os.environ["RUSTFS_USER"]
rust_pw = os.environ["RUSTFS_PW"]
pg_user = os.environ["PG_USER"]
pg_pw = os.environ["PG_PW"]
pg_name = os.environ["PG_DB"]


# list buckets
def listBuckets():
    for bucket in s3.list_buckets()["Buckets"]:
        print(bucket.get("Name"))


def getMetaDataAndSource():
    paginator = s3.get_paginator("list_objects_v2")
    raw_buck = "org-raw"
    base_path = "calls/"

    # Get all sources
    source_paths = []
    sources = []
    source_paths_names = []
    # Search folder one step down
    for pages in paginator.paginate(Bucket=raw_buck, Prefix=base_path, Delimiter="/"):
        # CommonPrefixes = Folders
        for page in pages.get("CommonPrefixes", []):
            # Get content type
            source_paths.append(page["Prefix"])
            name = page["Prefix"].removeprefix(base_path).rstrip("/")
            sources.append(name)
            source_pn = (page["Prefix"], name)
            source_paths_names.append(source_pn)

    # list each metadata by source

    source_and_metapath = []
    for path, name in source_paths_names:
        metaList = []
        srcMeta = f"{path}metadata/"
        for page in paginator.paginate(Bucket=raw_buck, Prefix=srcMeta):
            for obj in page.get("Contents", []):
                # Store source and path to file in a tuple
                source_and_metapath.append((name, obj["Key"]))
    return source_and_metapath


def getTables():
    with pool.connection() as pgConn:
        with pgConn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables WHERE table_schema = 'clean'
            """)
            records = cur.fetchall()
        pgConn.commit()


def extractXC(mPath):
    print("xcomm")


def extractCXM(mPath):
    print("connex")


def extract8x8(mPath):
    print("8x8")


def processNPush(pool):
    sourceNMeta = getMetaDataAndSource()
    for source, mPath in sourceNMeta:
        match source.lower():
            case "aircall":
                extractAC(mPath, pool, "aircall")
            case "xcom":
                extractXC(mPath)
            case "cxm":
                extractCXM(mPath)
            case "8x8":
                extract8x8(mPath)
            case _:
                raise Exception("Invalid source type")


def extractAC(mPath, pool, source):
    resp = s3.get_object(Bucket="org-raw", Key=mPath)
    file_name = os.path.basename(mPath)
    dFrame = pd.read_csv(
        io.BytesIO(resp["Body"].read()),
        usecols=[
            "Call Uuid",
            "Direction",
            "In Call Duration",
            "Duration (in seconds)",
            "From",
            "To",
            "Full Name",
            "Created Time",
            "Answered Time",
            "Ended Time",
            "Was Answered (Yes / No)",
        ],
    )
    # convert to answered to boolean
    dFrame["answered"] = dFrame["Was Answered (Yes / No)"].map(
        {"Yes": True, "No": False}
    )
    # convert datetimes to timestamps with timezones
    cols = ["Created Time", "Ended Time", "Answered Time"]
    for c in cols:
        dFrame[c] = dtToUk(dFrame[c])
    # clean duration columns
    duration_cols = ["In Call Duration", "Duration (in seconds)"]
    for c in duration_cols:
        dFrame[c] = pd.to_numeric(
            dFrame[c].astype(str).str.replace(",", "", regex=False),
            errors="coerce",
        )

    mask_missing_duration = dFrame[duration_cols].isna().any(axis=1)
    mask_missing_created = dFrame["Created Time"].isna()
    mask_missing_uuid = dFrame["Call Uuid"].isna()
    mask_missing_dir = dFrame["Direction"].isna()
    bad_mask = (
        mask_missing_duration
        | mask_missing_created
        | mask_missing_uuid
        | mask_missing_dir
    )

    # Create new column
    dFrame["_quarantine_reason"] = ""
    # Assign reason for invalid rows
    dFrame.loc[mask_missing_duration, "_quarantine_reason"] += "Invalid duration; "
    dFrame.loc[mask_missing_created, "_quarantine_reason"] += "Missing Created Time; "
    dFrame.loc[mask_missing_uuid, "_quarantine_reason"] += "Missing Call Uuid; "
    dFrame.loc[mask_missing_dir, "_quarantine_reason"] += "Missing Direction; "

    # Split into valid and none valid rows
    good_rows = dFrame[~bad_mask]
    bad_rows = dFrame[bad_mask]

    # Build bad row lists
    reasons = bad_rows["_quarantine_reason"].str.strip("; ").tolist()
    raw_jsons = bad_rows.apply(
        # convert NaNs to null for json compatiablity
        lambda r: json.dumps(r.to_dict(), default=str).replace("NaN", "null"),
        axis=1,
    ).tolist()
    row_nums = (bad_rows.index + 2).tolist()
    file_names = [file_name] * len(bad_rows)
    apps = [source] * len(bad_rows)
    companies = ["bi"] * len(bad_rows)

    bad_params = list(zip(file_names, row_nums, raw_jsons, reasons, apps, companies))

    rows = [
        (
            source,
            row["Call Uuid"],
            file_name,
            "bi",
            row["Created Time"],
            row["Ended Time"],
            row["Answered Time"],
            row["In Call Duration"],
            row["Duration (in seconds)"],
            row["Direction"],
            row["From"],
            row["To"],
            row["Full Name"],
            row["answered"],
            getRecordingPath(row["Created Time"], source, row["Call Uuid"]),
        )
        for _, row in good_rows.iterrows()
    ]
    with pool.connection() as pgConn:
        with pgConn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO clean.call_metadata (
                    source_app,
                    source_call_id,
                    source_file,
                    company_id,
                    start_time,
                    end_time,
                    answered_time,
                    call_duration_secs,
                    total_duration_secs,
                    direction,
                    customer_tel,
                    agent_tel,
                    agent,
                    answered,
                    recording_uri
                ) VALUES(
                    %s,%s, %s, %s, %s, %s, %s, 
                    %s,%s, %s, %s, %s, %s, %s,%s
                )
                """,
                rows,
            )
            if not bad_rows.empty:
                cur.executemany(
                    """
                    INSERT INTO clean.call_quarantine (
                        source_file,
                        source_row_number,
                        raw_row,
                        reason,
                        source_app,
                        company_id
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s
                    )
                    """,
                    bad_params,
                )
            print(
                f"{file_name}: Inserted {len(rows)} rows, Quarantined {len(bad_rows)} rows"
            )


def getRecordingPath(start_time, source, file_name):
    # Will check using Cron job later
    if pd.isna(start_time):
        return ""
    date_path = start_time.strftime("%Y/%m/%d")
    return f"calls/{source}/{date_path}/{file_name}.mp3"


def dtToUk(s):
    s = pd.to_datetime(s, dayfirst=True, format="mixed", errors="coerce")
    return s.dt.tz_localize(
        "Europe/London", ambiguous="infer", nonexistent="shift_forward"
    )


with ConnectionPool(
    conninfo=f"dbname={pg_name} user={pg_user} password={pg_pw} host=127.0.0.1 port=5433",
    min_size=1,
    max_size=5,
    open=True,
) as pool:
    processNPush(pool)
