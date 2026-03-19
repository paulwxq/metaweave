# public.highway_metadata（高速公路业务主题元数据表，存储各分析主题的定义、关联表、典型问题及关键词等元信息）
## 字段列表：
- id (integer(32)) - 元数据记录唯一标识ID [示例: 1, 2]
- topic_code (character varying(50)) - 主题编码（如日营收、车流量等） [示例: daily_revenue, vehicle_flow]
- topic_name (character varying(255)) - 主题中文名称 [示例: 日营业数据分析, 车流量分析]
- description (text) - 主题业务描述与分析口径说明 [示例: 基于 bss_business_day_data 表，分析每个服务区和档口每天的营业收入、订单数量、支付方式等。, 基于 bss_car_day_count 表，分析各服务区每日车流量及不同车辆类型分布情况。]
- related_tables (array) - 关联的源数据表名数组 [示例: ["bss_business_day_data", "bss_branch", "bss_service_area"], ["bss_car_day_count", "bss_service_area"]]
- questions (jsonb) - 常见业务问题及对应SQL查询示例 [示例: {"哪个档口今天订单最多？": "SELECT branch_name, order_sum FROM bss_business_day_data WHERE oper_date = CURRENT_DATE ORDER BY order_sum DESC LIMIT 1", "今日各支付方式的收入汇总是多少？": "SELECT SUM(wx) AS wx_total, SUM(zfb) AS zfb_total, SUM(rmb) AS rmb_total, SUM(xs) AS xs_total, SUM(jd) AS jd_total FROM bss_business_day_data WHERE oper_date = CURRENT_DATE", "鄱阳湖服务区今天的总收入是多少？": "SELECT SUM(pay_sum) FROM bss_business_day_data WHERE service_name = '鄱阳湖服务区' AND oper_date = CURRENT_DATE"}, {"昨天货车最多的服务区是哪个？": "SELECT s.service_area_name, SUM(c.customer_count) AS truck_count FROM bss_car_day_count c JOIN bss_service_area s ON c.service_area_id = s.id WHERE c.car_type = '货车' AND c.count_date = CURRENT_DATE - INTERVAL '1 day' GROUP BY s.service_area_name ORDER BY truck_count DESC LIMIT 1", "某服务区的车种分布是怎样的？": "SELECT car_type, SUM(customer_count) FROM bss_car_day_count WHERE service_area_id = 'xxx' GROUP BY car_type", "最近7天车流量最多的服务区是哪个？": "SELECT s.service_area_name, SUM(c.customer_count) AS total_cars FROM bss_car_day_count c JOIN bss_service_area s ON c.service_area_id = s.id WHERE c.count_date >= CURRENT_DATE - INTERVAL '7 day' GROUP BY s.service_area_name ORDER BY total_cars DESC LIMIT 1"}]
- keywords (array) - 主题关联的核心业务关键词数组 [示例: ["收入", "订单", "支付方式"], ["车流量", "车辆类型", "过境"]]
- theme_tag (character varying(50)) - 主题所属分析大类标签 [示例: 交易分析, 流量分析]
- update_ts (timestamp without time zone) - 元数据最后更新时间戳 [示例: 2025-06-18 05:23:32.570917, 2025-06-18 05:23:32.594986]
## 字段补充说明：
- 主键约束 highway_metadata_pkey: id