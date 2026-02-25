# public.address（地址信息表，存储客户或实体的详细地址、行政区划及联系方式）
## 字段列表：
- address_id (integer(32)) - 地址唯一标识ID [示例: 1, 2]
- address (character varying(50)) - 详细地址（街道、门牌号等） [示例: 47 MySakila Drive, 28 MySQL Boulevard]
- address2 (character varying(50)) - 补充地址（如楼层、房间号等） [示例: ]
- district (character varying(20)) - 所属行政区（省/州/区） [示例: Alberta, QLD]
- city_id (smallint(16)) - 所属城市的外键ID [示例: 300, 576]
- postal_code (character varying(10)) - 邮政编码 [示例: , ]
- phone (character varying(20)) - 联系电话 [示例: , ]
- last_update (timestamp without time zone) - 最后更新时间 [示例: 2006-02-15 09:45:30, 2006-02-15 09:45:30]
## 字段补充说明：
- 主键约束 address_pkey: address_id
- 外键约束 city_id 关联 public.city.city_id
- 索引 idx_fk_city_id (btree): city_id