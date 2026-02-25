# public.store（门店信息表，存储门店编号、负责人、地址及最后更新时间）
## 字段列表：
- store_id (integer(32)) - 门店唯一标识ID [示例: 1, 2]
- manager_staff_id (smallint(16)) - 门店经理员工ID [示例: 1, 2]
- address_id (smallint(16)) - 门店地址信息ID [示例: 1, 2]
- last_update (timestamp without time zone) - 最后更新时间戳 [示例: 2006-02-15 09:57:12, 2006-02-15 09:57:12]
## 字段补充说明：
- 主键约束 store_pkey: store_id
- 外键约束 address_id 关联 public.address.address_id
- 外键约束 manager_staff_id 关联 public.staff.staff_id