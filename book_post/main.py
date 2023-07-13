from datetime import date, datetime, timedelta
from google.cloud import bigquery
from pathlib import Path
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from typing import Dict, List
import functions_framework
import os
import pandas as pd
import random
import requests


PROJECT_NAME = os.environ["PROJECT_NAME"]
bigquery_client = bigquery.Client(project=PROJECT_NAME)


def get_client():
    uri = "mongodb+srv://ap_bot:{password}@serverlessinstance0.fzzbd4i.mongodb.net/?retryWrites=true&w=majority"
    password = open(os.environ["MONGODB_PASSWORD_PATH"]).read().strip()
    client = MongoClient(uri.format(password=password), server_api=ServerApi('1'))
    try:
        client.admin.command('ping')
    except Exception as e:
        print(e)
    return client


mongodb_client = get_client()


def fetch(sql: str, start_date: date, end_date: date) -> pd.DataFrame:
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
        ]
    )
    df = bigquery_client.query(sql, job_config=job_config).to_dataframe()
    df["publish_date"] = df["publish_date"].map(lambda x: x.isoformat())
    print(df)
    return df


def fetch_new_books(start_date: date, end_date: date):
    with (Path(__file__).parent / "book.sql").open() as fp:
        sql = fp.read()
    return fetch(sql, start_date, end_date)


def get_db_data(client: MongoClient) -> List[Dict]:
    db = client.get_database(os.environ["MONGODB_DATABASE"])
    collection = db.get_collection("new_books")
    return list(collection.find({}))


def update_db(client: MongoClient, records: List[Dict]):
    db = client.get_database(os.environ["MONGODB_DATABASE"])
    collection = db.get_collection("new_books")
    collection.delete_many({})
    collection.insert_many(records)


def get_todays_book_post() -> str:
    today = datetime.now().date()
    data = fetch_new_books(today, today)
    items = []
    datestr = today.strftime("%Y年%m月%d日")
    for i, row in data.iterrows():
        link = link_to_a(row['link'])
        print(row)
        item = f"{row['authors']}『{row['title']}』{row['publisher']}\n{link}"
        items.append(item)
    return f"{datestr}\n本日出る本\n" + "\n\n".join(items)


def link_to_a(url: str):
    return f"<a href={url}>{url}</a>"


def get_random_book_post(enable_update: bool = False) -> str:
    book_data = get_random_book(enable_update=enable_update)
    print(book_data)
    author = book_data["authors"]
    title = book_data["title"]
    description = book_data["description"]
    link = link_to_a(book_data["link"])
    publisher = book_data["publisher"]
    date_str = date.fromisoformat(book_data["publish_date"]).strftime("%Y年%m月%d日")
    post = f"""{date_str}発売予定
{author}『{title}』{publisher}
{description}
{link}
"""
    return post


def get_random_book(enable_update: bool = True):
    today = datetime.now().date()
    enddate = today + timedelta(days=30)
    posted_books = get_db_data(mongodb_client)
    # publish_dateが今日以降のものだけを抽出
    posted_books = [d for d in posted_books if d["publish_date"] >= today.isoformat()]
    posted_isbn = {d["isbn"] for d in posted_books}
    data = fetch_new_books(today, enddate)
    entries = []
    for i, row in data.iterrows():
        if row["isbn"] in posted_isbn:
            continue
        row = row.to_dict()
        entries.append(row)
    if len(entries) == 0:
        print("No new books found.")
        return
    new_post = random.choice(entries)
    if enable_update:
        new_data = {
            "isbn": new_post["isbn"],
            "publish_date": new_post["publish_date"],
            "title": new_post["title"],
        }
        update_db(mongodb_client, posted_books + [new_data])
    return new_post


@functions_framework.http
def handle_request(request):
    json_data = request.get_json()
    print(json_data)
    mode = json_data.get("mode", "random")
    if mode == "random":
        post = get_random_book_post(enable_update=True)
    elif mode == "today":
        post = get_todays_book_post()
    else:
        return "Invalid mode", 400
    print(post)
    # secret_token = open(os.environ["SECRET_TOKEN_PATH"]).read().strip()
    data = {
        "content": post
    }
    headers = {
        "Content-Type": "application/json",
    #    "Authorization": secret_token
    }
    # resp = requests.post(os.environ["POST_URL"], headers=headers, json=data)
    # print(resp.content)
    return "OK"

