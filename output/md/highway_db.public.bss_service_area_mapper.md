# public.bss_service_area_mapper（服务区信息映射表，关联不同来源系统中的服务区名称、编号与唯一标识）
## 字段列表：
- id (character varying(32)) - 服务区域映射记录唯一标识ID [示例: 00e1e893909211ed8ee6fa163eaf653f, 013867f5962211ed8ee6fa163eaf653f]
- version (integer(32)) - 记录版本号，用于乐观锁控制 [示例: 1, 1]
- create_ts (timestamp without time zone) - 记录创建时间戳 [示例: 2023-01-10 10:54:03, 2023-01-17 12:47:29]
- created_by (character varying(50)) - 创建人用户名 [示例: admin, admin]
- update_ts (timestamp without time zone) - 记录最后更新时间戳 [示例: 2023-01-10 10:54:07, 2023-01-17 12:47:32]
- updated_by (character varying(50)) - 最后更新人用户名 [示例: null]
- delete_ts (timestamp without time zone) - 逻辑删除时间戳（NULL表示未删除） [示例: null]
- deleted_by (character varying(50)) - 逻辑删除人用户名 [示例: null]
- service_name (character varying(255)) - 服务区名称 [示例: 信丰西服务区, 南康北服务区]
- service_no (character varying(255)) - 服务区编码 [示例: 1067, 1062]
- service_area_id (character varying(32)) - 服务区id [示例: 97cd6cd516a551409a4d453a58f9e170, fdbdd042962011ed8ee6fa163eaf653f]
- source_system_type (character varying(50)) - 数据来源类别名称 [示例: 驿美, 驿购]
- source_type (integer(32)) - 数据来源类别id [示例: 3, 1]
## 字段补充说明：
- 主键约束 bss_service_area_mapper_pkey: id
- 索引 idx_bss_service_area_mapper_on_service_area (btree): service_area_id