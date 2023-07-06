from datetime import datetime
from google.cloud import storage
from typing import Dict, NamedTuple
import feedparser
import functions_framework
import google.api_core.exceptions
import gzip
import json
import os
import requests
import re
import tempfile


class HanmotoData(NamedTuple):
    id: str
    raw_title: str
    title: str
    authors: str
    publisher: str
    publish_date: str
    link: str
    isbn: str
    openbd: Dict = None

    def to_dict(self):
        description = self.openbd["description"] if self.openbd else ""
        keyword = self.openbd["keyword"] if self.openbd else ""
        c_code = self.openbd["c_code"] if self.openbd else ""
        author_data = self.openbd["authors"] if self.openbd else []
        return dict(id=self.id, raw_title=self.raw_title, title=self.title,
                    authors=self.authors, publisher=self.publisher,
                    publish_date=self.publish_date, link=self.link,
                    isbn=self.isbn, description=description, keywords=keyword, c_code=c_code,
                    author_data=author_data)


def upload_gcs(bucket_name: str, path: str, local_path):
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(path)
    blob.content_encoding = "gzip"
    blob.upload_from_filename(local_path)


def download_gcs(bucket_name: str, path: str) -> str:
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(path)
    blob.content_encoding = "gzip"
    try:
        return blob.download_as_text()
    except google.api_core.exceptions.NotFound:
        return ""


def parse_openbd(record):
    onix = record["onix"]
    title = onix["DescriptiveDetail"]["TitleDetail"]["TitleElement"]["TitleText"]["content"]
    description = ""
    for collateral in onix["CollateralDetail"].get("TextContent", []):
        if collateral["TextType"] == "03":
            description = collateral["Text"]
            break
    authors = onix["DescriptiveDetail"]["Contributor"]
    keyword = ""
    c_code = ""
    if "Subject" in onix["DescriptiveDetail"]:
        subjects = onix["DescriptiveDetail"]["Subject"]
        for sub in subjects:
            if sub["SubjectSchemeIdentifier"] == "20":
                keyword = sub["SubjectHeadingText"]
            elif sub["SubjectSchemeIdentifier"] == "78":
                c_code = sub["SubjectCode"]
    return dict(
        title=title,
        description=description,
        authors=authors,
        subjects=onix["DescriptiveDetail"].get("Subject"),
        keyword=keyword,
        c_code=c_code,
    )


def fetch_openbk(isbns):
    base_url = "https://api.openbd.jp/v1/get?isbn=" + ",".join(isbns)
    resp = requests.get(base_url).json()
    return_value = {}
    for d in resp:
        if d is None:
            continue
        onix = d["onix"]
        idbn = onix["RecordReference"]
        return_value[idbn] = parse_openbd(d)
    return return_value


def parse_date(date_str: str) -> str:
    """parser date
    sample 'Wed, 05 Jul 2023 00:00:00 +0900
    :param date_str:
    :return:
    """
    datetime_obj = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
    return datetime_obj.date().isoformat()


def parse_title(raw_title: str):
    """parse title
    sample '江戸川乱歩⑤\u3000火星の運河 - 江戸川 乱歩(著/文) | 三和書籍'
    :param title:
    :return:
    """
    reg = re.compile(u"(?P<title>.*)\s-\s(?P<author>.*)\s\|\s(?P<publisher>.*)")
    return reg.match(raw_title).groupdict()


def handle_entries(entries):
    isbns = []
    book_data = []
    for entry in entries:
        raw_title = entry["title"]
        id_ = entry["id"]
        link = entry["link"]
        published = entry["published"]   # 'Wed, 05 Jul 2023 00:00:00 +0900'
        date = parse_date(published)
        isbn = id_.split("/")[-1]
        title = parse_title(raw_title)
        data = HanmotoData(id_, raw_title, title["title"], title["author"],
                           title["publisher"],
                           date, link, isbn)
        book_data.append(data)
        isbns.append(isbn)
    openbd_data = fetch_openbk(isbns)
    return_values = []
    for bd in book_data:
        if bd.isbn in openbd_data:
            bd = bd._replace(openbd=openbd_data[bd.isbn])
        return_values.append(bd.to_dict())
    return return_values


def fetch_feed(url):
    d = feedparser.parse(url)
    unit = 200
    for i in range(0, len(d["entries"]), unit):
        entries = d["entries"][i:i + unit]
        books = handle_entries(entries)
        yield from books


def get_new_book_cache(bucket_name: str, path: str, today: str):
    new_book_cache = download_gcs(bucket_name, path)
    return_values = []
    for line in new_book_cache.split("\n"):
        line = line.strip()
        if not line:
            continue
        isbn, date = line.split("\t")
        if date < today:
            continue
        return_values.append((isbn, date))
    return return_values


def fetch_and_save(url: str, bucket_name: str):
    cache_data_path = "cache/new_book_cache.txt.gz"
    today = datetime.now().date().isoformat()
    new_book_cache = get_new_book_cache(bucket_name, cache_data_path, today)
    new_book_set = set([d[0] for d in new_book_cache])
    feed_data = tempfile.NamedTemporaryFile("wb")
    cache_data = tempfile.NamedTemporaryFile("wb")
    count = 0
    with gzip.open(feed_data.name, "wb") as f:
        with gzip.open(cache_data.name, "wb") as cf:
            for cache in new_book_cache:
                cf.write((cache[0] + "\t" + cache[1] + "\n").encode("utf-8"))
            for b in fetch_feed(url):
                if b["isbn"] in new_book_set:
                    continue
                cf.write((b["isbn"] + "\t" + b["publish_date"] + "\n").encode("utf-8"))
                f.write((json.dumps(b) + "\n").encode("utf-8"))
                count += 1
    feed_data.flush()
    feed_data.seek(0)
    cache_data.flush()
    cache_data.seek(0)
    remote_path = f"new_books/date={today}/hanmoto.jsonl.gz"
    if count > 0:
        upload_gcs(bucket_name, remote_path, feed_data.name)
    upload_gcs(bucket_name, cache_data_path, cache_data.name)
    print(dict(date=today, count=count))
    return dict(count=count, date=today)


@functions_framework.http
def handle_request(request):
    base_url = os.environ.get("BASE_URL")
    bucket_name = os.environ.get("BUCKET_NAME")
    print(f"base_url: {base_url}")
    result = fetch_and_save(base_url, bucket_name)
    return dict(result="ok", **result)
