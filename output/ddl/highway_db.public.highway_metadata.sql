-- ====================================
-- Database: highway_db
-- Table: public.highway_metadata
-- Comment: 高速公路业务主题元数据表，存储各分析主题的定义、关联表、典型问题及关键词等元信息
-- Generated: 2026-03-18 12:46:13
-- ====================================

CREATE TABLE IF NOT EXISTS public.highway_metadata (
    id INTEGER(32) NOT NULL DEFAULT nextval('highway_metadata_id_seq'::regclass),
    topic_code CHARACTER VARYING(50) NOT NULL,
    topic_name CHARACTER VARYING(255) NOT NULL,
    description TEXT,
    related_tables ARRAY,
    questions JSONB,
    keywords ARRAY,
    theme_tag CHARACTER VARYING(50),
    update_ts TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT highway_metadata_pkey PRIMARY KEY (id)
);

-- Column Comments
COMMENT ON COLUMN public.highway_metadata.id IS '元数据记录唯一标识ID';
COMMENT ON COLUMN public.highway_metadata.topic_code IS '主题编码（如日营收、车流量等）';
COMMENT ON COLUMN public.highway_metadata.topic_name IS '主题中文名称';
COMMENT ON COLUMN public.highway_metadata.description IS '主题业务描述与分析口径说明';
COMMENT ON COLUMN public.highway_metadata.related_tables IS '关联的源数据表名数组';
COMMENT ON COLUMN public.highway_metadata.questions IS '常见业务问题及对应SQL查询语句';
COMMENT ON COLUMN public.highway_metadata.keywords IS '主题相关关键词数组';
COMMENT ON COLUMN public.highway_metadata.theme_tag IS '主题分类标签（如交易分析、流量分析等）';
COMMENT ON COLUMN public.highway_metadata.update_ts IS '元数据最后更新时间';

-- Table Comment
COMMENT ON TABLE public.highway_metadata IS '高速公路业务主题元数据表，存储各分析主题的定义、关联表、典型问题及关键词等元信息';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.highway_metadata",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "id": "1",
        "topic_code": "daily_revenue",
        "topic_name": "日营业数据分析",
        "description": "基于 bss_business_day_data 表，分析每个服务区和档口每天的营业收入、订单数量、支付方式等。",
        "related_tables": "[\"bss_business_day_data\", \"bss_branch\", \"bss_service_area\"]",
        "questions": "{\"哪个档口今天订单最多？\": \"SELECT branch_name, order_sum FROM bss_business_day_data WHERE oper_date = CURRENT_DATE ORDER BY order_sum DESC LIMIT 1\", \"今日各支付方式的收入汇总是多少？\": \"SELECT SUM(wx) AS wx_total, SUM(zfb) AS zfb_total, SUM(rmb) AS rmb_total, SUM(xs) AS xs_total, SUM(jd) AS jd_total FROM bss_business_day_data WHERE oper_date = CURRENT_DATE\", \"鄱阳湖服务区今天的总收入是多少？\": \"SELECT SUM(pay_sum) FROM bss_business_day_data WHERE service_name = '鄱阳湖服务区' AND oper_date = CURRENT_DATE\"}",
        "keywords": "[\"收入\", \"订单\", \"支付方式\"]",
        "theme_tag": "交易分析",
        "update_ts": "2025-06-18 05:23:32.570917"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "id": "2",
        "topic_code": "vehicle_flow",
        "topic_name": "车流量分析",
        "description": "基于 bss_car_day_count 表，分析各服务区每日车流量及不同车辆类型分布情况。",
        "related_tables": "[\"bss_car_day_count\", \"bss_service_area\"]",
        "questions": "{\"昨天货车最多的服务区是哪个？\": \"SELECT s.service_area_name, SUM(c.customer_count) AS truck_count FROM bss_car_day_count c JOIN bss_service_area s ON c.service_area_id = s.id WHERE c.car_type = '货车' AND c.count_date = CURRENT_DATE - INTERVAL '1 day' GROUP BY s.service_area_name ORDER BY truck_count DESC LIMIT 1\", \"某服务区的车种分布是怎样的？\": \"SELECT car_type, SUM(customer_count) FROM bss_car_day_count WHERE service_area_id = 'xxx' GROUP BY car_type\", \"最近7天车流量最多的服务区是哪个？\": \"SELECT s.service_area_name, SUM(c.customer_count) AS total_cars FROM bss_car_day_count c JOIN bss_service_area s ON c.service_area_id = s.id WHERE c.count_date >= CURRENT_DATE - INTERVAL '7 day' GROUP BY s.service_area_name ORDER BY total_cars DESC LIMIT 1\"}",
        "keywords": "[\"车流量\", \"车辆类型\", \"过境\"]",
        "theme_tag": "流量分析",
        "update_ts": "2025-06-18 05:23:32.594986"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "id": "3",
        "topic_code": "brand_category",
        "topic_name": "品牌与品类分析",
        "description": "结合 bss_branch 与营业数据，分析品牌、经营品类与收入之间的关系。",
        "related_tables": "[\"bss_branch\", \"bss_business_day_data\"]",
        "questions": "{\"哪个品牌的收入最高？\": \"SELECT bb.product_brand, SUM(bd.pay_sum) AS total FROM bss_branch bb JOIN bss_business_day_data bd ON bb.branch_no = bd.branch_no WHERE bd.oper_date = CURRENT_DATE GROUP BY bb.product_brand ORDER BY total DESC LIMIT 1\", \"今天各品牌收入占比是多少？\": \"SELECT bb.product_brand, SUM(bd.pay_sum) AS total FROM bss_branch bb JOIN bss_business_day_data bd ON bb.branch_no = bd.branch_no WHERE bd.oper_date = CURRENT_DATE GROUP BY bb.product_brand\", \"不同经营品类的平均订单是多少？\": \"SELECT bb.classify, SUM(bd.pay_sum)/NULLIF(SUM(bd.order_sum), 0) AS avg_per_order FROM bss_branch bb JOIN bss_business_day_data bd ON bb.branch_no = bd.branch_no WHERE bd.oper_date = CURRENT_DATE GROUP BY bb.classify\"}",
        "keywords": "[\"品牌\", \"经营品类\", \"收入占比\"]",
        "theme_tag": "经营分析",
        "update_ts": "2025-06-18 05:23:32.613978"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "id": "4",
        "topic_code": "route_service_mapping",
        "topic_name": "线路与服务区映射分析",
        "description": "基于路线与服务区的多对多关系，分析高速路段服务覆盖情况。",
        "related_tables": "[\"bss_section_route\", \"bss_service_area\", \"bss_section_route_area_link\"]",
        "questions": "{\"服务区最多的线路是哪条？\": \"SELECT section_route_id, COUNT(*) AS service_count FROM bss_section_route_area_link GROUP BY section_route_id ORDER BY service_count DESC LIMIT 1\", \"每条线路包含多少服务区？\": \"SELECT section_route_id, COUNT(*) AS service_count FROM bss_section_route_area_link GROUP BY section_route_id\", \"某服务区属于哪些高速线路？\": \"SELECT section_route_id FROM bss_section_route_area_link WHERE service_area_id = 'xxx'\"}",
        "keywords": "[\"路线\", \"服务区\", \"映射关系\"]",
        "theme_tag": "结构分析",
        "update_ts": "2025-06-18 05:23:32.630444"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "id": "5",
        "topic_code": "company_performance",
        "topic_name": "公司维度绩效分析",
        "description": "基于公司主数据表 bss_company，结合服务区或档口的运营数据，分析各管理公司下属单位的经营情况。",
        "related_tables": "[\"bss_company\", \"bss_service_area\", \"bss_branch\", \"bss_business_day_data\"]",
        "questions": "{\"今天收入最高的公司是哪家？\": \"SELECT c.company_name, SUM(bd.pay_sum) AS total FROM bss_company c JOIN bss_service_area sa ON c.id = sa.company_id JOIN bss_branch b ON sa.id = b.service_area_id JOIN bss_business_day_data bd ON b.branch_no = bd.branch_no WHERE bd.oper_date = CURRENT_DATE GROUP BY c.company_name ORDER BY total DESC LIMIT 1\", \"各公司负责的档口数量是多少？\": \"SELECT c.company_name, COUNT(*) AS branch_count FROM bss_company c JOIN bss_branch b ON c.id = b.company_id GROUP BY c.company_name\", \"每个公司下属服务区的今日收入总和是多少？\": \"SELECT c.company_name, SUM(bd.pay_sum) AS total FROM bss_company c JOIN bss_service_area sa ON c.id = sa.company_id JOIN bss_branch b ON sa.id = b.service_area_id JOIN bss_business_day_data bd ON b.branch_no = bd.branch_no WHERE bd.oper_date = CURRENT_DATE GROUP BY c.company_name\"}",
        "keywords": "[\"公司\", \"收入\", \"绩效\", \"档口\"]",
        "theme_tag": "公司管理",
        "update_ts": "2025-06-18 05:23:32.647466"
      }
    }
  ]
}
*/