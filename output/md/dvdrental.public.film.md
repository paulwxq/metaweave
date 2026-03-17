# public.film（电影信息表，存储影片标题、描述、年份、语言、租借参数、时长、分级等元数据）
## 字段列表：
- film_id (integer(32)) - 电影唯一标识ID [示例: null]
- title (character varying(255)) - 电影标题 [示例: null]
- description (text) - 电影剧情简介 [示例: null]
- release_year (integer(32)) - 电影上映年份 [示例: null]
- language_id (smallint(16)) - 电影语言标识ID [示例: null]
- rental_duration (smallint(16)) - 租赁期限（天） [示例: null]
- rental_rate (numeric(4,2)) - 租赁单价（美元） [示例: null]
- length (smallint(16)) - 电影时长（分钟） [示例: null]
- replacement_cost (numeric(5,2)) - 丢失/损坏赔偿金额（美元） [示例: null]
- rating (user-defined) - 电影分级（如NC-17、R、PG等） [示例: null]
- last_update (timestamp without time zone) - 最后更新时间戳 [示例: null]
- special_features (array) - 特别花絮（数组，如预告片、幕后花絮等） [示例: null]
- fulltext (tsvector) - 全文检索向量（用于标题和简介的全文搜索） [示例: null]
## 字段补充说明：
- 主键约束 film_pkey: film_id
- 外键约束 language_id 关联 public.language.language_id
- 索引 film_fulltext_idx (btree): fulltext
- 索引 idx_fk_language_id (btree): language_id
- 索引 idx_title (btree): title
- rental_rate 使用numeric(4,2)存储，精确到小数点后2位
- replacement_cost 使用numeric(5,2)存储，精确到小数点后2位