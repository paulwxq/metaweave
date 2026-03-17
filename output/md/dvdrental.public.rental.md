# public.rental（租赁记录表，存储影片租借的起止时间、租借人、库存项及经办员工信息）
## 字段列表：
- rental_id (integer(32)) - 租赁记录唯一标识ID [示例: 2, 3]
- rental_date (timestamp without time zone) - 租赁发生时间戳 [示例: 2005-05-24 22:54:33, 2005-05-24 23:03:39]
- inventory_id (integer(32)) - 影片库存记录ID [示例: 1525, 1711]
- customer_id (smallint(16)) - 租赁客户唯一标识ID [示例: 459, 408]
- return_date (timestamp without time zone) - 影片归还时间戳（可为空） [示例: 2005-05-28 19:40:33, 2005-06-01 22:12:39]
- staff_id (smallint(16)) - 处理租赁业务的员工ID [示例: 1, 1]
- last_update (timestamp without time zone) - 记录最后更新时间戳 [示例: 2006-02-16 02:30:53, 2006-02-16 02:30:53]
## 字段补充说明：
- 主键约束 rental_pkey: rental_id
- 外键约束 customer_id 关联 public.customer.customer_id
- 外键约束 inventory_id 关联 public.inventory.inventory_id
- 外键约束 staff_id 关联 public.staff.staff_id
- 索引 idx_fk_inventory_id (btree): inventory_id