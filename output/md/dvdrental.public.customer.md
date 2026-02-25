# public.customer（客户信息表，存储客户的姓名、联系方式、地址及账户状态等基本信息）
## 字段列表：
- customer_id (integer(32)) - 客户唯一标识ID [示例: 524, 1]
- store_id (smallint(16)) - 所属门店ID [示例: 1, 1]
- first_name (character varying(45)) - 客户名字 [示例: Jared, Mary]
- last_name (character varying(45)) - 客户姓氏 [示例: Ely, Smith]
- email (character varying(50)) - 客户电子邮箱地址 [示例: jared.ely@sakilacustomer.org, mary.smith@sakilacustomer.org]
- address_id (smallint(16)) - 关联地址ID [示例: 530, 5]
- activebool (boolean) - 账户激活状态（true-启用，false-禁用） [示例: True, True]
- create_date (date) - 客户记录创建日期 [示例: 2006-02-14, 2006-02-14]
- last_update (timestamp without time zone) - 最后更新时间戳 [示例: 2013-05-26 14:49:45.738000, 2013-05-26 14:49:45.738000]
- active (integer(32)) - 活跃状态（1-活跃，0-非活跃） [示例: 1, 1]
## 字段补充说明：
- 主键约束 customer_pkey: customer_id
- 外键约束 address_id 关联 public.address.address_id
- 索引 idx_fk_address_id (btree): address_id
- 索引 idx_fk_store_id (btree): store_id
- 索引 idx_last_name (btree): last_name