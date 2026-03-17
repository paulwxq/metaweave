-- ====================================
-- Database: highway_db
-- Table: public.qa_feedback
-- Comment: 用户对SQL查询结果的反馈记录，包含问题、生成SQL、点赞状态及是否用于训练数据
-- Generated: 2026-03-17 23:00:08
-- ====================================

CREATE TABLE IF NOT EXISTS public.qa_feedback (
    id INTEGER(32) NOT NULL DEFAULT nextval('qa_feedback_id_seq'::regclass),
    question TEXT NOT NULL,
    sql TEXT NOT NULL,
    is_thumb_up BOOLEAN NOT NULL,
    user_id CHARACTER VARYING(64) NOT NULL,
    create_time TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_in_training_data BOOLEAN DEFAULT false,
    update_time TIMESTAMP WITHOUT TIME ZONE,
    CONSTRAINT qa_feedback_pkey PRIMARY KEY (id)
);

-- Column Comments
COMMENT ON COLUMN public.qa_feedback.id IS '反馈记录唯一标识ID';
COMMENT ON COLUMN public.qa_feedback.question IS '用户提出的自然语言问题';
COMMENT ON COLUMN public.qa_feedback.sql IS '系统生成的对应SQL查询语句';
COMMENT ON COLUMN public.qa_feedback.is_thumb_up IS '用户是否点赞（True-是，False-否）';
COMMENT ON COLUMN public.qa_feedback.user_id IS '提交反馈的用户账号标识';
COMMENT ON COLUMN public.qa_feedback.create_time IS '反馈记录创建时间戳';
COMMENT ON COLUMN public.qa_feedback.is_in_training_data IS '是否已纳入训练数据集（True-是，False-否）';
COMMENT ON COLUMN public.qa_feedback.update_time IS '反馈记录最后更新时间戳';

-- Indexes
CREATE INDEX idx_qa_feedback_create_time ON public.qa_feedback(create_time);
CREATE INDEX idx_qa_feedback_is_in_training ON public.qa_feedback(is_in_training_data);
CREATE INDEX idx_qa_feedback_is_thumb_up ON public.qa_feedback(is_thumb_up);
CREATE INDEX idx_qa_feedback_user_id ON public.qa_feedback(user_id);

-- Table Comment
COMMENT ON TABLE public.qa_feedback IS '用户对SQL查询结果的反馈记录，包含问题、生成SQL、点赞状态及是否用于训练数据';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.qa_feedback",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "id": "4",
        "question": "按服务区统计营收",
        "sql": "SELECT service_name, SUM(pay_sum) as total_revenue FROM bss_business_day_data WHERE delete_ts IS NULL GROUP BY service_name ORDER BY total_revenue DESC;",
        "is_thumb_up": "True",
        "user_id": "user004",
        "create_time": "2024-01-16 09:45:00",
        "is_in_training_data": "False",
        "update_time": null
      }
    },
    {
      "label": "Record 2",
      "data": {
        "id": "5",
        "question": "查询今日新增用户",
        "sql": "SELECT COUNT(*) as new_users FROM users WHERE DATE(create_time) = CURRENT_DATE;",
        "is_thumb_up": "True",
        "user_id": "user005",
        "create_time": "2024-01-16 16:30:00",
        "is_in_training_data": "False",
        "update_time": null
      }
    },
    {
      "label": "Record 3",
      "data": {
        "id": "6",
        "question": "热门商品排行榜",
        "sql": "SELECT product_name, SUM(quantity) as total_sold FROM order_items oi JOIN products p ON oi.product_id = p.id GROUP BY product_name ORDER BY total_sold DESC LIMIT 10;",
        "is_thumb_up": "True",
        "user_id": "admin",
        "create_time": "2024-01-17 10:00:00",
        "is_in_training_data": "True",
        "update_time": null
      }
    },
    {
      "label": "Record 4",
      "data": {
        "id": "7",
        "question": "查询用户余额",
        "sql": "SELECT user_id, account_balance FROM user_accounts WHERE user_id = '12345';",
        "is_thumb_up": "True",
        "user_id": "user006",
        "create_time": "2024-01-17 13:25:00",
        "is_in_training_data": "False",
        "update_time": null
      }
    },
    {
      "label": "Record 5",
      "data": {
        "id": "8",
        "question": "按月统计订单趋势",
        "sql": "SELECT DATE_TRUNC('month', create_time) as month, COUNT(*) as order_count FROM orders GROUP BY month ORDER BY month;",
        "is_thumb_up": "True",
        "user_id": "user007",
        "create_time": "2024-01-18 11:40:00",
        "is_in_training_data": "False",
        "update_time": null
      }
    }
  ]
}
*/