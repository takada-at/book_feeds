"""
版元ドットコムから新刊書籍情報を取得し、OpenBDから追加情報を取得して、
Google Cloud Storageに保存するCloud Functions用のスクリプト。

このスクリプトは以下の処理を行います:
1. 版元ドットコムのRSSフィードから指定日の新刊情報を取得
2. 取得した書籍情報からISBNを抽出し、OpenBDから詳細情報を取得
3. 取得したデータをGCS上に日付ごとにgzip圧縮したJSONLファイルとして保存
"""

from bs4 import BeautifulSoup
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
import time


ENABLE_CRAWLING = False


class HanmotoData(NamedTuple):
    """
    版元ドットコムから取得した書籍データを格納するためのデータクラス。

    Attributes:
        id: 版元ドットコムでの書籍ID
        raw_title: 元のタイトル文字列（著者・出版社情報を含む）
        title: パース済みの書籍タイトル
        authors: 著者情報
        publisher: 出版社名
        publish_date: 出版日（ISO形式の文字列）
        link: 書籍詳細ページへのリンク
        isbn: 書籍のISBNコード
        openbd: OpenBDから取得した追加情報（辞書型）
    """

    id: str
    raw_title: str
    title: str
    authors: str
    publisher: str
    publish_date: str
    link: str
    isbn: str
    openbd: Dict = None
    from_hanmotoweb: Dict = None

    def to_dict(self):
        """
        HanmotoDataオブジェクトを辞書形式に変換するメソッド。
        OpenBDから取得した追加情報も含めて、すべての書籍情報を辞書形式で返します。

        Returns:
            dict: 書籍情報を含む辞書
        """
        description = self.openbd["description"] if self.openbd else ""
        keyword = self.openbd["keyword"] if self.openbd else ""
        c_code = self.openbd["c_code"] if self.openbd else ""
        author_data = self.openbd["authors"] if self.openbd else []
        if not c_code and self.from_hanmotoweb:
            c_code = self.from_hanmotoweb["ccode"]
        if not description and self.from_hanmotoweb:
            description = self.from_hanmotoweb["description"]
        label = self.openbd["label"] if self.openbd else ""
        series = self.openbd["series"] if self.openbd else ""
        return dict(
            id=self.id,
            raw_title=self.raw_title,
            title=self.title,
            authors=self.authors,
            publisher=self.publisher,
            publish_date=self.publish_date,
            link=self.link,
            isbn=self.isbn,
            description=description,
            keywords=keyword,
            c_code=c_code,
            author_data=author_data,
            label=label,
            series=series,
        )


def get_book_info(isbn):
    """版元ドットコムの書籍詳細ページからCコードと書籍説明を取得する関数。
    :param isbn: 書籍のISBNコード
    :return: Cコードと書籍説明を含む辞書
    """
    url = f"https://www.hanmoto.com/bd/isbn/{isbn}"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises HTTPError for bad requests (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        return f"Error fetching URL: {e}"

    soup = BeautifulSoup(response.text, "html.parser")

    # Extract book title
    # title_element = soup.select_one('h1.book-title-block span.book-title')
    # title = title_element.text.strip() if title_element else "Title not found"

    # Extract author
    # author_elements = soup.select('div.book-authors a.book-author span.book-author-name')
    # authors = [a.text.strip() for a in author_elements] if author_elements else ["Author not found"]
    # author = ", ".join(authors)

    # Extract publisher
    # publisher_element = soup.select_one('div.book-publishers a.book-imprint')
    # publisher = publisher_element.text.strip() if publisher_element else "Publisher not found"

    # Extract C-code
    ccode_element = soup.select_one("div.book-ccode-num")
    ccode = (
        ccode_element.text.strip().split()[0] if ccode_element else "C-Code not found"
    )

    # Extract description
    description_element = soup.select_one("div.book-contents p")
    description = (
        description_element.text.strip()
        if description_element
        else "Description not found"
    )

    return {"ccode": ccode, "description": description}


def upload_gcs(bucket_name: str, path: str, local_path):
    """ローカルファイルをGoogle Cloud Storageにアップロードする関数。

    :param bucket_name: GCSバケット名
    :param path: GCS上のファイルパス
    :param local_path: アップロードするローカルファイルのパス
    """
    project = os.environ["PROJECT_NAME"]
    storage_client = storage.Client(project=project)
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(path)
    blob.content_encoding = "gzip"
    blob.upload_from_filename(local_path)


def download_gcs(bucket_name: str, path: str) -> str:
    """Google Cloud Storageからファイルをダウンロードしてテキストとして返す関数。

    :param bucket_name: GCSバケット名
    :param path: GCS上のファイルパス
    :return: ダウンロードしたファイルの内容（テキスト）。ファイルが存在しない場合は空文字列を返す。
    """
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
    """ONIXデータからレーベル名とシリーズ名を抽出する関数。

    :param onix: OpenBDから取得したONIXデータ
    :return: レーベル名とシリーズ名を含む辞書
    """
    label = None
    series = None
    if (
        "Collection" in onix["DescriptiveDetail"]
        and onix["DescriptiveDetail"]["Collection"].get("CollectionType") == "10"
    ):
        collection = onix["DescriptiveDetail"]["Collection"]
        if "TitleDetail" in collection:
            for elm in collection["TitleDetail"].get("TitleElement", []):
                if elm["TitleElementLevel"] == "02":
                    label = elm["TitleText"]["content"]
                elif elm["TitleElementLevel"] == "03":
                    series = elm["TitleText"]["content"]
    return dict(label=label, series=series)


def parse_openbd(record):
    """OpenBDから取得した書籍レコードを解析し、必要な情報を抽出する関数。

    :param record: OpenBDから取得した書籍レコード
    :return: 抽出した書籍情報を含む辞書（タイトル、説明、著者、キーワード、Cコード、レーベル、シリーズなど）
    """
    onix = record["onix"]
    title = onix["DescriptiveDetail"]["TitleDetail"]["TitleElement"]["TitleText"][
        "content"
    ]
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
        series=series,
    )


def fetch_openbk(isbns):
    """OpenBD APIを使用して複数のISBNコードに対応する書籍情報を取得する関数。

    :param isbns: 取得したい書籍のISBNコードのリスト
    :return: ISBNコードをキー、書籍情報を値とする辞書
    """
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
    """日付文字列をパースしてISO形式の日付文字列に変換する関数。

    :param date_str: パースする日付文字列（例: 'Wed, 05 Jul 2023 00:00:00 +0900'）
    :return: ISO形式の日付文字列（例: '2023-07-05'）
    """
    datetime_obj = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
    return datetime_obj.date().isoformat()


def parse_title(raw_title: str):
    """タイトル文字列から書籍タイトル、著者、出版社を抽出する関数。

    :param raw_title: パースするタイトル文字列（例: '江戸川乱歩⑤\u3000火星の運河 - 江戸川 乱歩(著/文) | 三和書籍'）
    :return: タイトル、著者、出版社の情報を含む辞書
    """
    reg = re.compile(
        "(?P<title>.*)\s-\s(?P<author>.*)\s\|\s(?P<publisher>.*)", flags=re.DOTALL
    )
    return reg.match(raw_title).groupdict()


def handle_entries(entries):
    """RSSフィードから取得したエントリーを処理し、書籍データを構造化する関数。

    :param entries: RSSフィードから取得したエントリーのリスト
    :return: 構造化された書籍データのリスト
    """
    isbns = []
    book_data = []
    for entry in entries:
        raw_title = entry["title"]
        id_ = entry["id"]
        link = entry["link"]
        published = entry["published"]  # 'Wed, 05 Jul 2023 00:00:00 +0900'
        date = parse_date(published)
        isbn = id_.split("/")[-1]
        title = parse_title(raw_title)
        data = HanmotoData(
            id_,
            raw_title,
            title["title"],
            title["author"],
            title["publisher"],
            date,
            link,
            isbn,
        )
        book_data.append(data)
        isbns.append(isbn)
    openbd_data = fetch_openbk(isbns)
    return_values = []
    for bd in book_data:
        if bd.isbn in openbd_data:
            bd = bd._replace(openbd=openbd_data[bd.isbn])
        if ENABLE_CRAWLING and (
            bd.openbd is None or not bd.openbd["description"] or not bd.openbd["c_code"]
        ):
            from_hanmotoweb = get_book_info(bd.isbn)
            bd = bd._replace(from_hanmotoweb=from_hanmotoweb)
            time.sleep(1)
        return_values.append(bd.to_dict())
    return return_values


def get_url(date_int: int) -> str:
    """指定された日数オフセットに基づいて版元ドットコムのRSS URL を生成する関数。

    :param date_int: 現在の日付からの日数オフセット（正の値は未来、負の値は過去）
    :return: 版元ドットコムのRSS URL
    """
    day = f"{date_int}day"
    url = f"https://www.hanmoto.com/ci/bd/search/sdate/{day}/edate/{day}/order/asc/vw/rss20/"
    return url


def get_today():
    """日本時間の現在の日付を取得する関数。

    :return: 日本時間の現在の日付（date型）
    """
    tz = pytz.timezone("Asia/Tokyo")
    return datetime.now(tz).date()


def fetch_feed_by_date(target_date: date):
    """指定された日付の版元ドットコムRSSフィードを取得する関数。

    :param target_date: 取得したい書籍情報の日付
    :yield: RSSフィードのエントリー
    """
    today = get_today()
    days = (target_date - today).days
    url = get_url(days)
    print(url)
    response = feedparser.parse(url)
    entries = response["entries"]
    yield from entries


def fetch_feed(target_date: date):
    """指定された日付の書籍情報を取得し、バッチ処理する関数。

    エントリーを200件ずつバッチ処理して、メモリ使用量を抑えます。

    :param target_date: 取得したい書籍情報の日付
    :yield: 構造化された書籍データ
    """
    entries = []
    unit = 200
    for entry in fetch_feed_by_date(target_date):
        entries.append(entry)
        if len(entries) >= unit:
            yield from handle_entries(entries)
            entries = []
    if entries:
        yield from handle_entries(entries)


def fetch_and_save(target_date: date, bucket_name: str):
    """指定された日付の書籍情報を取得し、GCSに保存する関数。

    :param target_date: 取得したい書籍情報の日付
    :param bucket_name: 保存先のGCSバケット名
    :return: 処理結果の情報（取得した書籍数と日付を含む辞書）
    """
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
    """Cloud Functionsのエントリーポイント。HTTPリクエストを処理し、書籍情報を取得・保存する。

    :param request: HTTPリクエストオブジェクト
    :return: 処理結果のJSON応答
    """
    bucket_name = os.environ.get("BUCKET_NAME")
    json_data = request.get_json()
    print(json_data)
    days = json_data.get("days", 0)
    target_date = get_today() + timedelta(days=days)
    result = fetch_and_save(target_date, bucket_name)
    return dict(result="ok", **result)
