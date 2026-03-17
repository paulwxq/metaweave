# public.city（城市信息表，存储全球城市名称、所属国家及最后更新时间）
## 字段列表：
- city_id (integer(32)) - 城市唯一标识ID [示例: 1, 2]
- city (character varying(50)) - 城市名称 [示例: A Corua (La Corua), Abha]
- country_id (smallint(16)) - 所属国家ID [示例: 87, 82]
- last_update (timestamp without time zone) - 最后更新时间 [示例: 2006-02-15 09:45:25, 2006-02-15 09:45:25]
## 字段补充说明：
- 主键约束 city_pkey: city_id
- 外键约束 country_id 关联 public.country.country_id
- 索引 idx_fk_country_id (btree): country_id