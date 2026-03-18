# public.bss_service_area（服务区信息表，存储高速公路服务区的名称、编号、位置、类型、状态及所属公司等基础信息）
## 字段列表：
- id (character varying(32)) - 服务区域唯一标识ID [示例: 0271d68ef93de9684b7ad8c7aae600b6, 08e01d7402abd1d6a4d9fdd5df855ef8]
- version (integer(32)) - 数据版本号，用于乐观锁控制 [示例: 3, 6]
- create_ts (timestamp without time zone) - 记录创建时间戳 [示例: 2021-05-21 13:26:40.589000, 2021-05-20 19:51:46.314000]
- created_by (character varying(50)) - 创建人用户名 [示例: admin, admin]
- update_ts (timestamp without time zone) - 记录最后更新时间戳 [示例: 2021-07-10 15:41:28.795000, 2021-07-11 09:33:08.455000]
- updated_by (character varying(50)) - 最后更新人用户名 [示例: admin, admin]
- delete_ts (timestamp without time zone) - 逻辑删除时间戳（为空表示未删除） [示例: null]
- deleted_by (character varying(50)) - 逻辑删除操作人用户名 [示例: null]
- service_area_name (character varying(255)) - 服务区名称 [示例: 白鹭湖停车区, 南昌南服务区]
- service_area_no (character varying(255)) - 服务区编码 [示例: H0814, H0105]
- company_id (character varying(32)) - 公司id [示例: b1629f07c8d9ac81494fbc1de61f1ea5, ee9bf1180a2b45003f96e597a4b7f15a]
- service_position (character varying(255)) - 服务区经纬度 [示例: 114.574721,26.825584, 115.910549,28.396355]
- service_area_type (character varying(50)) - 服务区类型 [示例: 信息化服务区, 信息化服务区]
- service_state (character varying(50)) - 服务区状态 [示例: 开放, 开放]
## 字段补充说明：
- 主键约束 bss_service_area_pkey: id
- 索引 idx_bss_service_area_on_company (btree): company_id