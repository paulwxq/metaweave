# public.qa_feedback（用户对SQL查询结果的反馈记录，包括问题、生成SQL、点赞状态及是否用于训练）
## 字段列表：
- id (integer(32)) - 反馈记录唯一标识ID [示例: 4, 5]
- question (text) - 用户提出的自然语言问题 [示例: 按服务区统计营收, 查询今日新增用户]
- sql (text) - 生成的对应SQL查询语句 [示例: SELECT service_name, SUM(pay_sum) as total_revenue FROM bss_business_day_data WHERE delete_ts IS NULL GROUP BY service_name ORDER BY total_revenue DESC;, SELECT COUNT(*) as new_users FROM users WHERE DATE(create_time) = CURRENT_DATE;]
- is_thumb_up (boolean) - 用户是否点赞（True-点赞，False-未点赞） [示例: True, True]
- user_id (character varying(64)) - 提交反馈的用户ID [示例: user004, user005]
- create_time (timestamp without time zone) - 反馈创建时间戳 [示例: 2024-01-16 09:45:00, 2024-01-16 16:30:00]
- is_in_training_data (boolean) - 是否已纳入训练数据集（True-是，False-否） [示例: False, False]
- update_time (timestamp without time zone) - 反馈最后更新时间戳 [示例: null]
## 字段补充说明：
- 主键约束 qa_feedback_pkey: id
- 索引 idx_qa_feedback_create_time (btree): create_time
- 索引 idx_qa_feedback_is_in_training (btree): is_in_training_data
- 索引 idx_qa_feedback_is_thumb_up (btree): is_thumb_up
- 索引 idx_qa_feedback_user_id (btree): user_id