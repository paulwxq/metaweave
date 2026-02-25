# public.country（国家信息表，存储世界各国名称及最后更新时间）
## 字段列表：
- country_id (integer(32)) - 国家唯一标识ID [示例: 1, 2]
- country (character varying(50)) - 国家名称 [示例: Afghanistan, Algeria]
- last_update (timestamp without time zone) - 最后更新时间 [示例: 2006-02-15 09:44:00, 2006-02-15 09:44:00]
## 字段补充说明：
- 主键约束 country_pkey: country_id