WITH base AS (
  SELECT isbn, title, authors, publisher, publish_date, description, link, c_code,
    ARRAY_TO_STRING(
      ARRAY(
        SELECT
          CONCAT(x.PersonName.content,
            ARRAY_TO_STRING(ARRAY(
              SELECT CASE role
                WHEN 'A01' THEN '(著/文)'
                WHEN 'A12' THEN '(イラスト)'
                WHEN 'A21' THEN '(解説)'
                WHEN 'A38' THEN '(原著)'
                WHEN 'B01' THEN '(編集)'
                WHEN 'B06' THEN '(訳)'
                WHEN 'B20' THEN '(解説)'
                ELSE role
              END AS r
              FROM UNNEST(x.ContributorRole) AS role
            ), "・")) FROM UNNEST(author_data) AS x
      ), "、"
    ) AS author_full
  FROM`peak-bit-229907.book_feed.external_new_books`
  WHERE
    publish_date BETWEEN @start_date AND @end_date
)
SELECT isbn, publish_date, authors, author_full, base.title, c.genre, publisher, c_code, description, link
FROM `peak-bit-229907.book_feed.external_categorized` AS c
LEFT JOIN base USING (isbn)
WHERE
    date BETWEEN @start_date AND @end_date
  AND
    (STRPOS(c.genre, "ホラー") > 0
     OR
     STRPOS(c.genre, "SF") > 0
     OR
     STRPOS(c.genre, "ファンタジー") > 0 AND SUBSTR(c_code, 3, 2) = "97"
     OR
     base.publisher IN ("早川書房", "東京創元社", "国書刊行会")
    )
ORDER BY publish_date