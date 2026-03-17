# public.bss_car_day_count（按日统计各车型在服务区域的客户使用数量）
## 字段列表：
- id (character varying(32)) - 汽车日统计记录唯一标识ID [示例: 00022c1c99ff11ec86d4fa163ec0f8fc, 00022caa99ff11ec86d4fa163ec0f8fc]
- version (integer(32)) - 数据版本号，用于乐观锁控制 [示例: 1, 1]
- create_ts (timestamp without time zone) - 记录创建时间戳 [示例: 2022-03-02 16:01:43, 2022-03-02 16:01:43]
- created_by (character varying(50)) - 创建人用户名或系统标识 [示例: null]
- update_ts (timestamp without time zone) - 记录最后更新时间戳 [示例: 2022-03-02 16:01:43, 2022-03-02 16:01:43]
- updated_by (character varying(50)) - 最后更新人用户名或系统标识 [示例: null]
- delete_ts (timestamp without time zone) - 逻辑删除时间戳（为空表示未删除） [示例: null]
- deleted_by (character varying(50)) - 逻辑删除人用户名或系统标识 [示例: null]
- customer_count (bigint(64)) - 车辆数量 [示例: 1114, 295]
- car_type (character varying(100)) - 车辆类别 [示例: 其他, 其他]
- count_date (date) - 统计日期 [示例: 2022-03-02, 2022-03-02]
- service_area_id (character varying(32)) - 服务区id [示例: null]
## 字段补充说明：
- 主键约束 bss_car_day_count_pkey: id
- 索引 idx_bss_car_day_count_on_service_area (btree): service_area_id