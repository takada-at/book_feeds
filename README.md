新刊情報収集とActivityPubのボット

Cloud Function用コード

- fetch_book_feeds: 版元ドットコムのフィードとopenBD APIから新刊情報を取得
- categorize: ChatGPT APIでデータを分類
- book_post: BOTに新刊情報を投稿させる

Cloud Run用コード

- apub_bot_func: ActivityPubボット。follow/unfollowの受け入れ機能と、投稿機能のみ。


インフラ構築用コード

- terraform: インフラ構築用