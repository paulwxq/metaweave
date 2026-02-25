# public.inventory（库存记录表，存储影片在各门店的库存数量及最后更新时间）
## 字段列表：
- inventory_id (integer(32)) - 库存记录唯一标识ID [示例: 1, 2]
- film_id (smallint(16)) - 电影ID，关联films表 [示例: 1, 1]
- store_id (smallint(16)) - 门店ID，关联stores表 [示例: 1, 1]
- last_update (timestamp without time zone) - 最后更新时间戳 [示例: 2006-02-15 10:09:17, 2006-02-15 10:09:17]
## 字段补充说明：
- 主键约束 inventory_pkey: inventory_id
- 外键约束 film_id 关联 public.film.film_id
- 索引 idx_store_id_film_id (btree): store_id, film_id