新刊犬というボットを作った。リンクを開いてもマストドンのフォロー画面に飛んだりはしないが、以下をマストドンで検索するとフォローできる。

@bookbot@apub-bot1-46e33xglnq-uc.a.run.app


## 作るまでの流れ
ちょっと前に版元ドットコムのRSSとOpenBD APIから新刊情報を取ってきて、ChatGPTにジャンルを分類させる仕組みを作ったので、これを使ってマストドンに新刊BOTを作ろうと思った。

人のサーバーでBOTを動かすのもどうなのかなあと思ったところ、ActivityPubの存在を知った。ActivityPubの作法にのっとってWebAPIを作ればマストドンからフォローできるらしい。

じゃあそれで作るかと決めた。最小の機能だけなら、APIを4つくらい実装すればいいだけっぽかったし。実際やってみると、情報も少なくて思ったより面倒だったが……。


## 構成
サーバーを管理したくなかったので、完全サーバーレスで動いている。

私用で諸々使っているGCPのプロジェクトを利用している。

新刊情報の収集と分類はCloud Functionで動くシンプルなバッチスクリプト。

ボット本体はGCPのCloudRunで動かし、データベースはMongoDB Atlasのサーバーレスインスタンスにした。ほぼ費用はかかっていない。URLもCloudRunで自動発行されるものを使っているのでドメインの取得や証明書も不要だった(そのせいでURLがきもくてあやしい感じにはなったが、URLを代償にして恩恵を受けているので仕方がない)。

ちなみに、ActivityPubの方は、投稿用APIに送られた投稿を転送しているだけで、新刊情報の抽出はまた別に行なっている。
下記の記事を書いている方が似たような仕組みを作っており、実装も参考にさせていただいた。

https://castaneai.hatenablog.com/entry/webhook-for-activitypub 


## 本の選定基準
Cコードを使って小説だけを抽出し、ChatGPTにタイトルと概要を渡して、「ミステリ、ライトノベル、ホラー、SF、ファンタジー、時代小説、戦争もの、児童向け、恋愛小説、官能小説、純文学、その他」に分類させている。GPT-3.5を使用している。ジャンル分類の正答率は計測していないが、ざっと見た感じ、完璧ではないが8、9割は合っているように見える。
ChatGPTにおすすめスコアなどを出させる案なども考えたが、今のところ単純なジャンル分類だけをやらせている。

その上で、SF、ホラー、海外ファンタジー、いくつかの出版社のものだけを優先して抽出している。ミステリも追加したかったが、出版点数が多いのでどう絞りこんだものか迷っている。
国内ファンタジーを入れていない理由も、なろう系とライトノベルの出版点数が多くて絞りこめなかったから。

選定基準を見直したり、小説以外の追加などもそのうち検討したい。
