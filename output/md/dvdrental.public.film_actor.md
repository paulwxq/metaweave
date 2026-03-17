# public.film_actor（电影与演员关联表，记录演员参演电影的关系及最后更新时间）
## 字段列表：
- actor_id (smallint(16)) - 演员唯一标识ID [示例: 1, 1]
- film_id (smallint(16)) - 电影唯一标识ID [示例: 1, 23]
- last_update (timestamp without time zone) - 记录最后更新时间 [示例: 2006-02-15 10:05:03, 2006-02-15 10:05:03]
## 字段补充说明：
- 主键约束 film_actor_pkey: actor_id, film_id
- 外键约束 actor_id 关联 public.actor.actor_id
- 外键约束 film_id 关联 public.film.film_id
- 索引 idx_fk_film_id (btree): film_id