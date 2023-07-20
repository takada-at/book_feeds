from datetime import date, datetime, timedelta
from google.cloud import storage
from typing import Dict, NamedTuple
import feedparser
import functions_framework
import google.api_core.exceptions
import gzip
import json
import os
import pytz
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
        label = self.openbd["label"] if self.openbd else ""
        series = self.openbd["series"] if self.openbd else ""
        return dict(id=self.id, raw_title=self.raw_title, title=self.title,
                    authors=self.authors, publisher=self.publisher,
                    publish_date=self.publish_date, link=self.link,
                    isbn=self.isbn, description=description, keywords=keyword, c_code=c_code,
                    author_data=author_data, label=label, series=series)


def upload_gcs(bucket_name: str, path: str, local_path):
    project = os.environ["PROJECT_NAME"]
    storage_client = storage.Client(project=project)
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(path)
    blob.content_encoding = "gzip"
    blob.upload_from_filename(local_path)


def download_gcs(bucket_name: str, path: str) -> str:
    project = os.environ["PROJECT_NAME"]
    storage_client = storage.Client(project=project)
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(path)
    blob.content_encoding = "gzip"
    try:
        return blob.download_as_text()
    except google.api_core.exceptions.NotFound:
        return ""


def get_title_detail(onix):
    label = None
    series = None
    if "Collection" in onix["DescriptiveDetail"] and onix["DescriptiveDetail"]["Collection"].get("CollectionType") == "10":
        collection = onix["DescriptiveDetail"]["Collection"]
        if "TitleDetail" in collection:
            for elm in collection["TitleDetail"].get("TitleElement", []):
                if elm["TitleElementLevel"] == "02":
                    label = elm["TitleText"]["content"]
                elif elm["TitleElementLevel"] == "03":
                    series = elm["TitleText"]["content"]
    return dict(label=label, series=series)


def parse_openbd(record):
    onix = record["onix"]
    title = onix["DescriptiveDetail"]["TitleDetail"]["TitleElement"]["TitleText"]["content"]
    description = ""
    for collateral in onix["CollateralDetail"].get("TextContent", []):
        if collateral["TextType"] == "03":
            description = collateral["Text"]
            break
    authors = onix["DescriptiveDetail"]["Contributor"]
    title_detail = get_title_detail(onix)
    label = title_detail.get("label", "")
    series = title_detail.get("series", "")
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
        label=label,
        series=series
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
    reg = re.compile(u"(?P<title>.*)\s-\s(?P<author>.*)\s\|\s(?P<publisher>.*)", flags=re.DOTALL)
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


def get_url(date_int: int) -> str:
    day = f"{date_int}day"
    url = f"https://www.hanmoto.com/ci/bd/search/sdate/{day}/edate/{day}/order/asc/vw/rss20/"
    return url


def get_today():
    tz = pytz.timezone('Asia/Tokyo')
    return datetime.now(tz).date()
    

def fetch_feed_by_date(target_date: date):
    today = get_today()
    days = (target_date - today).days
    url = get_url(days)
    print(url)
    response = feedparser.parse(url)
    entries = response["entries"]
    yield from entries


def fetch_feed(target_date: date):
    entries = []
    unit = 200
    for entry in fetch_feed_by_date(target_date):
        entries.append(entry)
        if len(entries) >= unit:
            yield from handle_entries(entries)
            entries = []
    if entries:
        yield from handle_entries(entries)


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


def fetch_and_save(target_date: date, bucket_name: str):
    date_str = target_date.isoformat()
    feed_data = tempfile.NamedTemporaryFile("wb")
    count = 0
    with gzip.open(feed_data.name, "wb") as f:
        for b in fetch_feed(target_date):
            f.write((json.dumps(b) + "\n").encode("utf-8"))
            count += 1
    feed_data.flush()
    feed_data.seek(0)
    remote_path = f"new_books/date={date_str}/hanmoto.jsonl.gz"
    if count > 0:
        upload_gcs(bucket_name, remote_path, feed_data.name)
    print(dict(date=date_str, count=count))
    return dict(count=count, date=date_str)


@functions_framework.http
def handle_request(request):
    bucket_name = os.environ.get("BUCKET_NAME")
    json_data = request.get_json()
    print(json_data)
    days = json_data.get("days", 0)
    target_date = get_today() + timedelta(days=days)
    result = fetch_and_save(target_date, bucket_name)
    return dict(result="ok", **result)
