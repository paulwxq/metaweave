# public.highway_metadata（高速公路元数据表，存储高速公路主题数据的描述、关联表、问题及关键词等元信息）
## 字段列表：
- id (integer(32)) - 元数据记录唯一标识ID [示例: null]
- topic_code (character varying(50)) - 主题编码（如日营收、车流量等） [示例: null]
- topic_name (character varying(255)) - 主题中文名称 [示例: null]
- description (text) - 主题业务描述与分析口径说明 [示例: null]
- related_tables (array) - 关联的源数据表名数组 [示例: null]
- questions (jsonb) - 常见业务问题及对应SQL查询语句 [示例: null]
- keywords (array) - 主题相关关键词数组 [示例: null]
- theme_tag (character varying(50)) - 主题分类标签（如交易分析、流量分析等） [示例: null]
- update_ts (timestamp without time zone) - 元数据最后更新时间 [示例: null]
## 字段补充说明：
- 主键约束 highway_metadata_pkey: id