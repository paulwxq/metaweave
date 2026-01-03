# public.order_item（订单明细表，存储每笔订单中商品的购买数量及对应信息）
## 字段列表：
- item_id (integer(32)) - 订单项唯一标识ID [示例: 1, 2]
- order_id (integer(32)) - 关联订单的唯一标识ID [示例: 5001, 5001]
- order_date (date) - 订单创建日期 [示例: 2024-01-01, 2024-01-01]
- product (character varying(100)) - 商品名称 [示例: 苹果, 香蕉]
- quantity (integer(32)) - 商品购买数量 [示例: 3, 2]
## 字段补充说明：
- 主键约束 order_item_pkey: item_id
- 外键约束 order_date, order_id 关联 public.order_header.order_date, order_id