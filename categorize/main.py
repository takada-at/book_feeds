from datetime import date, datetime, timedelta
from google.cloud import bigquery
from google.cloud import secretmanager
from google.cloud import storage
from openai import OpenAI
import functions_framework
import gzip
import json
import os
import pandas as pd
import pytz
import tempfile


PROJECT_NAME = os.environ["PROJECT_NAME"]
bigquery_client = bigquery.Client(PROJECT_NAME)
secret_manager_client = secretmanager.SecretManagerServiceClient()
storage_client = storage.Client(project=PROJECT_NAME)
openai_client = None
SQL = """SELECT isbn, raw_title, authors, title, publisher, description, label
FROM book_feed.external_new_books
WHERE
  SUBSTR(c_code, 1, 1)!="9" AND SUBSTR(c_code, 3, 2) IN ("93", "97") AND description != ""
  AND date=@date
"""


def upload_gcs(bucket_name: str, path: str, local_path):
    project = os.environ["PROJECT_NAME"]
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(path)
    blob.content_encoding = "gzip"
    blob.upload_from_filename(local_path)


def fetch(target_date: date):
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("date", "DATE", target_date)]
    )
    return bigquery_client.query(SQL, job_config=job_config).to_dataframe()


def schema():
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "book_categories",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "number": {"type": "integer"},
                                "genre": {"type": "string"},
                            },
                            "required": [
                                "number",
                                "genre",
                            ],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["items"],
                "additionalProperties": False,
            },
        },
    }


def do_openai_api(df):
    system_prompt = """タスク
- これらの小説を以下のカテゴリーに分類し、JSONで返しなさい

カテゴリは以下から選びなさい。
ミステリ、ライトノベル、ホラー、SF、ファンタジー、時代小説、戦争もの、児童向け、恋愛小説、官能小説、純文学、その他

## OUTPUT FORMAT
[
    {"number": 1, "genre": "ミステリ"},
    {"number": 2, "genre": "ライトノベル"},
]
"""
    lines = []
    for i, row in df.iterrows():
        author = row["authors"]
        title = row["title"]
        publisher = row["publisher"]
        description = row["description"].replace("\n", "\\n")[:500]
        if row["label"]:
            label = f"({row['label']})"
        else:
            label = ""
        line = f"{i + 1}. {author}『{title}』{label}{publisher}"
        line += f'\n    "{description}"'
        lines.append(line)
    books = "\n".join(lines)
    prompt = f"# BOOKS\n{books}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    args = dict(
        model="gpt-4o-mini",
        temperature=0.6,
        timeout=60,
        messages=messages,
        response_format=schema(),
    )
    openai_client = get_openai_client()
    completion = openai_client.chat.completions.create(**args)
    print(prompt)
    print(completion.choices[0].message.content)
    return parse_json(completion.choices[0].message.content)


def parse_json(result):
    try:
        return json.loads(result)
    except json.JSONDecodeError as e:
        return None


def categorize(df):
    unit = 5
    dfs = []
    for i in range(0, len(df), unit):
        target = df.loc[i : i + unit - 1].copy()
        raw_result = do_openai_api(target)
        try:
            result = check_result(raw_result, target)
        except AssertionError as e:
            print(e)
            continue
        target["genre"] = result
        dfs.append(target)
    return pd.concat(dfs, axis=0)


def check_result(result, target):
    print("result", result)
    assert len(result["items"]) == len(target)
    return_values = []
    for item in result["items"]:
        return_values.append(item["genre"])
    return return_values


def fetch_secret_version(key):
    name = f"projects/{PROJECT_NAME}/secrets/{key}/versions/latest"
    response = secret_manager_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def get_openai_client():
    global openai_client
    if openai_client is None:
        api_key = open(os.environ["SECRET_KEY_PATH"]).read()
        openai_client = OpenAI(api_key=api_key)
    return openai_client


def categorize_date(target_date: date, bucket_name: str):
    date_str = target_date.isoformat()
    df = fetch(target_date)
    if len(df) == 0:
        print("no data")
        return dict(count=0, date=date_str)
    df = categorize(df)
    df["book_type"] = "novel"
    df = df[["isbn", "raw_title", "book_type", "genre"]]
    tmp = tempfile.NamedTemporaryFile("wb")
    # df.to_csv("result.csv", index=False)
    with gzip.open(tmp.name, "wb") as fp:
        df.to_json(fp, orient="records", lines=True)
    tmp.flush()
    tmp.seek(0)
    remote_path = f"categorized/date={date_str}/novel.jsonl.gz"
    upload_gcs(bucket_name, remote_path, tmp.name)
    return dict(count=len(df), date=date_str)


def get_today():
    tz = pytz.timezone("Asia/Tokyo")
    return datetime.now(tz).date()


@functions_framework.http
def handle_request(request):
    bucket_name = os.environ.get("BUCKET_NAME")
    json_data = request.get_json()
    print(json_data)
    days = json_data.get("days", 0)
    target_date = get_today() + timedelta(days=days)
    result = categorize_date(target_date, bucket_name)
    return dict(result="ok", **result)
