# public.actor（演员信息表，存储电影演员的姓名、唯一标识及最后更新时间）
## 字段列表：
- actor_id (integer(32)) - 演员唯一标识ID [示例: 1, 2]
- first_name (character varying(45)) - 演员名字 [示例: Penelope, Nick]
- last_name (character varying(45)) - 演员姓氏 [示例: Guiness, Wahlberg]
- last_update (timestamp without time zone) - 记录最后更新时间 [示例: 2013-05-26 14:47:57.620000, 2013-05-26 14:47:57.620000]
## 字段补充说明：
- 主键约束 actor_pkey: actor_id
- 索引 idx_actor_last_name (btree): last_name