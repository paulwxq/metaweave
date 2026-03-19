# public.bss_company（公司信息表，存储企业分公司名称、编号及基础审计信息）
## 字段列表：
- id (character varying(32)) - 公司唯一标识ID（UUID格式） [示例: 30675d85ba5044c31acfa243b9d16334, 47ed0bb37f5a85f3d9245e4854959b81]
- version (integer(32)) - 数据版本号，用于乐观锁控制 [示例: 1, 1]
- create_ts (timestamp without time zone) - 记录创建时间戳 [示例: 2021-05-20 09:51:58.718000, 2021-05-20 09:42:03.341000]
- created_by (character varying(50)) - 创建人用户名 [示例: admin, admin]
- update_ts (timestamp without time zone) - 记录最后更新时间戳 [示例: 2021-05-20 09:51:58.718000, 2021-05-20 09:42:03.341000]
- updated_by (character varying(50)) - 最后更新人用户名 [示例: admin]
- delete_ts (timestamp without time zone) - 逻辑删除时间戳（NULL表示未删除） [示例: null]
- deleted_by (character varying(50)) - 逻辑删除操作人用户名 [示例: null]
- company_name (character varying(255)) - 公司名称 [示例: 上饶分公司, 宜春分公司]
- company_no (character varying(255)) - 公司编码 [示例: H03, H02]
## 字段补充说明：
- 主键约束 bss_company_pkey: id