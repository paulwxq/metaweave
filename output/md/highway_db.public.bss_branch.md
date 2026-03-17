# public.bss_branch（高速公路服务区经营网点信息表，存储各餐饮、小吃等品牌分支网点的基本属性与归属关系）
## 字段列表：
- id (character varying(32)) - 分支机构唯一标识ID [示例: 00904903cae681aab7a494c3e88e5acd, 01a3df15b454fa7b5f176125af0c57d8]
- version (integer(32)) - 数据版本号，用于乐观锁控制 [示例: 1, 1]
- create_ts (timestamp without time zone) - 记录创建时间戳 [示例: 2021-10-15 09:46:45.010000, 2021-05-20 19:53:58.977000]
- created_by (character varying(50)) - 创建人用户名 [示例: admin, admin]
- update_ts (timestamp without time zone) - 记录最后更新时间戳 [示例: 2021-10-15 09:46:45.010000, 2021-11-07 20:26:10]
- updated_by (character varying(50)) - 最后更新人用户名 [示例: updated by importSQL, updated by importSQL]
- delete_ts (timestamp without time zone) - 逻辑删除时间戳（NULL表示未删除） [示例: null]
- deleted_by (character varying(50)) - 逻辑删除操作人用户名 [示例: null]
- branch_name (character varying(255)) - 档口名称 [示例: 于都驿美餐饮南区, 南城餐饮西区]
- branch_no (character varying(255)) - 档口编码 [示例: 003585, H0601B]
- service_area_id (character varying(32)) - 服务区id [示例: c7e2f26df373e9cb75bd24ddba57f27f, 8eb8ec693642354a62d640c7f1c2365c]
- company_id (character varying(32)) - 公司id [示例: ce5e6f553513dad393694e1fa663aaf4, e6c060f05306a03f978e2b952a551744]
- classify (character varying(256)) - 品类 [示例: 餐饮, 餐饮]
- product_brand (character varying(256)) - 品牌 [示例: 驿美餐饮, 小圆满（自助餐）]
- category (character varying(256)) - 类别 [示例: 餐饮, 中餐]
- section_route_id (character varying(32)) - 线路id [示例: lvkcuu94d4487c42z7qltsvxcyz0iqu5, wnejyryq6zvtdy6axgvz6jutv8n6vc3r]
- direction (character varying(256)) - 服务区方向 [示例: 南区, 西区]
- is_manual_entry (integer(32)) - 是否手工录入数据：0：系统自动  1：手工录入 [示例: 0, 0]
- co_company (character varying(256)) - 合作单位 [示例: 江西驿美餐饮管理有限责任公司, 嘉兴市同辉高速公路服务区经营管理有限公司]
## 字段补充说明：
- 索引 idx_area_id (btree): service_area_id
- 索引 idx_brach_no (btree): branch_no
- 索引 idx_company_id (btree): company_id