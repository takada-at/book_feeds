WITH base AS (
  SELECT isbn, ANY_VALUE(title) AS title, ANY_VALUE(authors) AS authors, ANY_VALUE(publisher) AS publisher, ANY_VALUE(publish_date) AS publish_date, ANY_VALUE(description) AS description, ANY_VALUE(link) AS link,
  ANY_VALUE(c_code) AS c_code
  FROM`peak-bit-229907.book_feed.external_new_books`
  WHERE
    publish_date BETWEEN @start_date AND @end_date
  GROUP BY 1
)
SELECT isbn, publish_date, authors, base.title, c.genre, publisher, c_code, description, link
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