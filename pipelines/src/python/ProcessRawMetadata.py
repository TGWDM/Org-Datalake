from DLConfig import buildRustClient
from psycopg_pool import ConnectionPool
import pandas as pd
import io
import os
from dotenv import load_dotenv
import json

s3 = buildRustClient()

load_dotenv()
rustUser = os.environ["RUSTFS_USER"]
rustPW = os.environ["RUSTFS_PW"]
pgUser = os.environ["PG_USER"]
pgPW = os.environ["PG_PW"]
pgName = os.environ["PG_DB"]


# list buckets
def listBuckets():
    for bucket in s3.list_buckets()["Buckets"]:
        print(bucket.get("Name"))


def GetMetaDataAndSource():
    paginator = s3.get_paginator("list_objects_v2")
    rawBuck = "org-raw"
    basePath = "calls/"

    # Get all sources
    sourcePaths = []
    sources = []
    sourcePathsAndNames = []
    # Search folder one step down
    for pages in paginator.paginate(Bucket=rawBuck, Prefix=basePath, Delimiter="/"):
        # CommonPrefixes = Folders
        for page in pages.get("CommonPrefixes", []):
            # Get content type
            sourcePaths.append(page["Prefix"])
            name = page["Prefix"].removeprefix(basePath).rstrip("/")
            sources.append(name)
            sourcePN = (page["Prefix"], name)
            sourcePathsAndNames.append(sourcePN)

    # list each metadata by source

    sourceNMetaPaths = []
    for path, name in sourcePathsAndNames:
        metaList = []
        srcMeta = f"{path}metadata/"
        print(" \n srcMeta: " + name)
        for page in paginator.paginate(Bucket=rawBuck, Prefix=srcMeta):
            for obj in page.get("Contents", []):
                # Store source and path to file in a tuple
                sourceNMetaPaths.append((name, obj["Key"]))
    return sourceNMetaPaths


def getTables():
    with pool.connection() as pgConn:
        with pgConn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables WHERE table_schema = 'clean'
            """)
            records = cur.fetchall()
        pgConn.commit()
    print(records)


def processNPush(pool):
    """
    Extract columns from aircall
    return the extract
    """
    sourceNMeta = GetMetaDataAndSource()
    for source, mPath in sourceNMeta:
        match source.lower():
            case "aircall":
                ExtractAC(mPath, pool)
            case "xcom":
                ExtractXC(mPath)
            case "cxm":
                ExtractCXM(mPath)
            case "8x8":
                Extract8x8(mPath)
            case _:
                raise Exception("Invalid source type")


def ExtractAC(mPath, pool):
    acResp = s3.get_object(Bucket="org-raw", Key=mPath)
    filename = os.path.basename(mPath)
    print(filename)
    dFrame = pd.read_csv(
        io.BytesIO(acResp["Body"].read()),
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
        dFrame[c] = dt_to_uk(dFrame[c])
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
    filenames = [filename] * len(bad_rows)
    apps = ["aircall"] * len(bad_rows)
    companies = ["bi"] * len(bad_rows)

    bad_params = list(zip(filenames, row_nums, raw_jsons, reasons, apps, companies))

    rows = [
        (
            "aircall",
            row["Call Uuid"],
            filename,
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
                    answered
                ) VALUES(
                    %s,%s, %s, %s, %s, %s, %s, 
                    %s,%s, %s, %s, %s, %s, %s
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


def ExtractXC(mPath):
    print("xcomm")


def ExtractCXM(mPath):
    print("connex")


def Extract8x8(mPath):
    print("8x8")


def dt_to_uk(s):
    s = pd.to_datetime(s, dayfirst=True, format="mixed", errors="coerce")
    return s.dt.tz_localize(
        "Europe/London", ambiguous="infer", nonexistent="shift_forward"
    )


with ConnectionPool(
    conninfo=f"dbname={pgName} user={pgUser} password={pgPW} host=127.0.0.1 port=5433",
    min_size=1,
    max_size=5,
    open=True,
) as pool:
    processNPush(pool)
