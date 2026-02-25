# public.film_category（电影与分类的多对多关联表，记录每部电影所属的分类及最后更新时间）
## 字段列表：
- film_id (smallint(16)) - 电影唯一标识ID [示例: 1, 2]
- category_id (smallint(16)) - 电影分类唯一标识ID [示例: 6, 11]
- last_update (timestamp without time zone) - 最后更新时间戳 [示例: 2006-02-15 10:07:09, 2006-02-15 10:07:09]
## 字段补充说明：
- 主键约束 film_category_pkey: film_id, category_id
- 外键约束 category_id 关联 public.category.category_id
- 外键约束 film_id 关联 public.film.film_id