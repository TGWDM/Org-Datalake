import boto3
from DLConfig import buildRustClient


# list buckets
def listBuckets():
    s3 = buildRustClient()
    for bucket in s3.list_buckets()["Buckets"]:
        print(bucket.get("Name"))


def GetMetaDataAndSource():
    s3 = buildRustClient()
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
                print(obj["Key"])
                sourceNMetaPaths.append((name, obj["Key"]))
    return sourceNMetaPaths


sourceNMMetaPaths = GetMetaDataAndSource()

#
