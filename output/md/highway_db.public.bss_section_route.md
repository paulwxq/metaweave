# public.bss_section_route（路段与路线关联表，存储路段名称、所属路线及唯一编码信息）
## 字段列表：
- id (character varying(32)) - 路段路由记录唯一标识ID [示例: 04ri3j67a806uw2c6o6dwdtz4knexczh, 0g5mnefxxtukql2cq6acul7phgskowy7]
- version (integer(32)) - 数据版本号，用于乐观锁控制 [示例: 1, 1]
- create_ts (timestamp without time zone) - 记录创建时间戳 [示例: 2021-10-29 19:43:50, 2021-10-29 19:43:50]
- created_by (character varying(50)) - 创建人用户名 [示例: admin, admin]
- update_ts (timestamp without time zone) - 记录最后更新时间戳 [示例: null]
- updated_by (character varying(50)) - 最后更新人用户名 [示例: null]
- delete_ts (timestamp without time zone) - 逻辑删除时间戳（为空表示未删除） [示例: null]
- deleted_by (character varying(50)) - 逻辑删除人用户名 [示例: null]
- section_name (character varying(255)) - 路段名称 [示例: 昌栗, 昌宁]
- route_name (character varying(255)) - 路线名称 [示例: 昌栗, 昌韶]
- code (character varying(255)) - 编号 [示例: SR0001, SR0002]
## 字段补充说明：
- 主键约束 bss_section_route_pkey: id