# public.payment（支付记录表，存储客户租赁服务的付款信息及交易详情）
## 字段列表：
- payment_id (integer(32)) - 支付记录唯一标识ID [示例: 17503, 17504]
- customer_id (smallint(16)) - 关联客户ID [示例: 341, 341]
- staff_id (smallint(16)) - 处理支付的员工ID [示例: 2, 1]
- rental_id (integer(32)) - 关联租赁记录ID [示例: 1520, 1778]
- amount (numeric(5,2)) - 支付金额（单位：元） [示例: 7.99, 1.99]
- payment_date (timestamp without time zone) - 支付发生的时间戳 [示例: 2007-02-15 22:25:46.996577, 2007-02-16 17:23:14.996577]
## 字段补充说明：
- 主键约束 payment_pkey: payment_id
- 外键约束 customer_id 关联 public.customer.customer_id
- 外键约束 rental_id 关联 public.rental.rental_id
- 外键约束 staff_id 关联 public.staff.staff_id
- 索引 idx_fk_customer_id (btree): customer_id
- 索引 idx_fk_rental_id (btree): rental_id
- 索引 idx_fk_staff_id (btree): staff_id
- amount 使用numeric(5,2)存储，精确到小数点后2位