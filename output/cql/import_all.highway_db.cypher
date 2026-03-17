// import_all.highway_db.cypher
// Neo4j 元数据导入脚本（global 模式，包含所有表和关系）
// 生成时间: 2026-03-17T23:00:53.624173
// 统计: 10 张表, 124 个列, 0 个关系

// =====================================================================
// 1. 创建唯一约束
// =====================================================================

	CREATE CONSTRAINT table_id IF NOT EXISTS FOR (t:Table) REQUIRE t.id IS UNIQUE;
	CREATE CONSTRAINT table_full_name IF NOT EXISTS FOR (t:Table) REQUIRE t.full_name IS UNIQUE;
	CREATE CONSTRAINT column_id IF NOT EXISTS FOR (c:Column) REQUIRE c.id IS UNIQUE;
	CREATE CONSTRAINT column_full_name IF NOT EXISTS FOR (c:Column) REQUIRE c.full_name IS UNIQUE;

// =====================================================================
// 2. 创建 Table 节点
// =====================================================================

	UNWIND [
  {
    "id": "highway_db.public.bss_branch",
    "database": "highway_db",
    "full_name": "public.bss_branch",
    "schema": "public",
    "name": "bss_branch",
    "comment": "高速公路服务区经营网点信息表，存储各餐饮、小吃等品牌分支网点的基本属性与归属关系",
    "pk": [],
    "uk": [],
    "fk": [],
    "logic_pk": [
      [
        "id"
      ]
    ],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "service_area_id"
      ],
      [
        "branch_no"
      ],
      [
        "company_id"
      ]
    ],
    "table_domains": [
      "经营主体与组织架构"
    ],
    "table_category": "dim"
  },
  {
    "id": "highway_db.public.bss_business_day_data",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data",
    "schema": "public",
    "name": "bss_business_day_data",
    "comment": "服务区各营业网点按日统计的多渠道（微信、支付宝、现金等）交易金额与订单数明细",
    "pk": [
      "id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "branch_no"
      ],
      [
        "oper_date"
      ]
    ],
    "table_domains": [
      "日度经营与客流分析"
    ],
    "table_category": "fact"
  },
  {
    "id": "highway_db.public.bss_car_day_count",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count",
    "schema": "public",
    "name": "bss_car_day_count",
    "comment": "按日统计各车型在服务区域的客户使用数量",
    "pk": [
      "id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "service_area_id"
      ]
    ],
    "table_domains": [
      "日度经营与客流分析"
    ],
    "table_category": "fact"
  },
  {
    "id": "highway_db.public.bss_company",
    "database": "highway_db",
    "full_name": "public.bss_company",
    "schema": "public",
    "name": "bss_company",
    "comment": "公司信息表，存储企业分公司名称、编号及基础审计信息",
    "pk": [
      "id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [],
    "table_domains": [
      "经营主体与组织架构"
    ],
    "table_category": "dim"
  },
  {
    "id": "highway_db.public.bss_section_route",
    "database": "highway_db",
    "full_name": "public.bss_section_route",
    "schema": "public",
    "name": "bss_section_route",
    "comment": "路段与路线关联表，存储路段名称、所属路线及唯一编码",
    "pk": [
      "id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [],
    "table_domains": [
      "服务区基础资产与地理拓扑"
    ],
    "table_category": "bridge"
  },
  {
    "id": "highway_db.public.bss_section_route_area_link",
    "database": "highway_db",
    "full_name": "public.bss_section_route_area_link",
    "schema": "public",
    "name": "bss_section_route_area_link",
    "comment": "路段路由与服务区的关联关系表",
    "pk": [
      "section_route_id",
      "service_area_id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "service_area_id"
      ]
    ],
    "table_domains": [
      "服务区基础资产与地理拓扑"
    ],
    "table_category": "bridge"
  },
  {
    "id": "highway_db.public.bss_service_area",
    "database": "highway_db",
    "full_name": "public.bss_service_area",
    "schema": "public",
    "name": "bss_service_area",
    "comment": "服务区信息表，存储高速公路服务区的名称、编号、位置、类型、状态及所属公司等基础信息",
    "pk": [
      "id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "company_id"
      ]
    ],
    "table_domains": [
      "服务区基础资产与地理拓扑"
    ],
    "table_category": "dim"
  },
  {
    "id": "highway_db.public.bss_service_area_mapper",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper",
    "schema": "public",
    "name": "bss_service_area_mapper",
    "comment": "服务区信息映射表，关联不同来源系统中的服务区名称、编号与唯一标识",
    "pk": [
      "id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "service_area_id"
      ]
    ],
    "table_domains": [
      "跨系统服务对象主数据映射"
    ],
    "table_category": "dim"
  },
  {
    "id": "highway_db.public.highway_metadata",
    "database": "highway_db",
    "full_name": "public.highway_metadata",
    "schema": "public",
    "name": "highway_metadata",
    "comment": "高速公路元数据表，存储高速公路主题数据的描述、关联表、问题及关键词等元信息",
    "pk": [
      "id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [],
    "table_domains": [
      "数据治理与元信息管理"
    ],
    "table_category": "dim"
  },
  {
    "id": "highway_db.public.qa_feedback",
    "database": "highway_db",
    "full_name": "public.qa_feedback",
    "schema": "public",
    "name": "qa_feedback",
    "comment": "用户对SQL查询结果的反馈记录，包含问题、生成SQL、点赞状态及是否用于训练数据",
    "pk": [
      "id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "create_time"
      ],
      [
        "is_in_training_data"
      ],
      [
        "is_thumb_up"
      ],
      [
        "user_id"
      ]
    ],
    "table_domains": [
      "_未分类_"
    ],
    "table_category": "fact"
  }
] AS t
	MERGE (n:Table {full_name: t.full_name})
	SET n.id       = t.id,
	    n.database = t.database,
	    n.schema   = t.schema,
	    n.name     = t.name,
	    n.comment  = t.comment,
	    n.pk       = t.pk,
	    n.uk       = t.uk,
    n.fk       = t.fk,
    n.logic_pk = t.logic_pk,
    n.logic_fk = t.logic_fk,
    n.logic_uk = t.logic_uk,
    n.indexes  = t.indexes,
    n.table_domains = t.table_domains,
    n.table_category = CASE
        WHEN t.table_category IS NOT NULL
            THEN t.table_category
        ELSE n.table_category
    END;

// =====================================================================
// 3. 创建 Column 节点
// =====================================================================

	UNWIND [
  {
    "id": "highway_db.public.bss_branch.id",
    "database": "highway_db",
    "full_name": "public.bss_branch.id",
    "schema": "public",
    "table": "bss_branch",
    "name": "id",
    "comment": "分支机构唯一标识ID",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_branch.version",
    "database": "highway_db",
    "full_name": "public.bss_branch.version",
    "schema": "public",
    "table": "bss_branch",
    "name": "version",
    "comment": "数据版本号，用于乐观锁控制",
    "data_type": "integer",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.003,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_branch.create_ts",
    "database": "highway_db",
    "full_name": "public.bss_branch.create_ts",
    "schema": "public",
    "table": "bss_branch",
    "name": "create_ts",
    "comment": "记录创建时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.417,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_branch.created_by",
    "database": "highway_db",
    "full_name": "public.bss_branch.created_by",
    "schema": "public",
    "table": "bss_branch",
    "name": "created_by",
    "comment": "创建人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.005,
    "null_rate": 0.021
  },
  {
    "id": "highway_db.public.bss_branch.update_ts",
    "database": "highway_db",
    "full_name": "public.bss_branch.update_ts",
    "schema": "public",
    "table": "bss_branch",
    "name": "update_ts",
    "comment": "记录最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.068,
    "null_rate": 0.116
  },
  {
    "id": "highway_db.public.bss_branch.updated_by",
    "database": "highway_db",
    "full_name": "public.bss_branch.updated_by",
    "schema": "public",
    "table": "bss_branch",
    "name": "updated_by",
    "comment": "最后更新人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.003,
    "null_rate": 0.46
  },
  {
    "id": "highway_db.public.bss_branch.delete_ts",
    "database": "highway_db",
    "full_name": "public.bss_branch.delete_ts",
    "schema": "public",
    "table": "bss_branch",
    "name": "delete_ts",
    "comment": "逻辑删除时间戳（NULL表示未删除）",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_branch.deleted_by",
    "database": "highway_db",
    "full_name": "public.bss_branch.deleted_by",
    "schema": "public",
    "table": "bss_branch",
    "name": "deleted_by",
    "comment": "逻辑删除操作人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.001,
    "null_rate": 0.981
  },
  {
    "id": "highway_db.public.bss_branch.branch_name",
    "database": "highway_db",
    "full_name": "public.bss_branch.branch_name",
    "schema": "public",
    "table": "bss_branch",
    "name": "branch_name",
    "comment": "档口名称",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.803,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_branch.branch_no",
    "database": "highway_db",
    "full_name": "public.bss_branch.branch_no",
    "schema": "public",
    "table": "bss_branch",
    "name": "branch_no",
    "comment": "档口编码",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.955,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_branch.service_area_id",
    "database": "highway_db",
    "full_name": "public.bss_branch.service_area_id",
    "schema": "public",
    "table": "bss_branch",
    "name": "service_area_id",
    "comment": "服务区id",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.089,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_branch.company_id",
    "database": "highway_db",
    "full_name": "public.bss_branch.company_id",
    "schema": "public",
    "table": "bss_branch",
    "name": "company_id",
    "comment": "公司id",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.008,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_branch.classify",
    "database": "highway_db",
    "full_name": "public.bss_branch.classify",
    "schema": "public",
    "table": "bss_branch",
    "name": "classify",
    "comment": "品类",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.005,
    "null_rate": 0.001
  },
  {
    "id": "highway_db.public.bss_branch.product_brand",
    "database": "highway_db",
    "full_name": "public.bss_branch.product_brand",
    "schema": "public",
    "table": "bss_branch",
    "name": "product_brand",
    "comment": "品牌",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.195,
    "null_rate": 0.001
  },
  {
    "id": "highway_db.public.bss_branch.category",
    "database": "highway_db",
    "full_name": "public.bss_branch.category",
    "schema": "public",
    "table": "bss_branch",
    "name": "category",
    "comment": "类别",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.038,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_branch.section_route_id",
    "database": "highway_db",
    "full_name": "public.bss_branch.section_route_id",
    "schema": "public",
    "table": "bss_branch",
    "name": "section_route_id",
    "comment": "线路id",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.045,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_branch.direction",
    "database": "highway_db",
    "full_name": "public.bss_branch.direction",
    "schema": "public",
    "table": "bss_branch",
    "name": "direction",
    "comment": "服务区方向",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.006,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_branch.is_manual_entry",
    "database": "highway_db",
    "full_name": "public.bss_branch.is_manual_entry",
    "schema": "public",
    "table": "bss_branch",
    "name": "is_manual_entry",
    "comment": "是否手工录入数据：0：系统自动  1：手工录入",
    "data_type": "integer",
    "semantic_role": "enum",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.002,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_branch.co_company",
    "database": "highway_db",
    "full_name": "public.bss_branch.co_company",
    "schema": "public",
    "table": "bss_branch",
    "name": "co_company",
    "comment": "合作单位",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.106,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_business_day_data.id",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.id",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "id",
    "comment": "业务日数据记录唯一标识ID",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 1,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_business_day_data.version",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.version",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "version",
    "comment": "数据版本号，用于乐观锁控制",
    "data_type": "integer",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.001,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_business_day_data.create_ts",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.create_ts",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "create_ts",
    "comment": "记录创建时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.084,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_business_day_data.created_by",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.created_by",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "created_by",
    "comment": "创建人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.001,
    "null_rate": 0.586
  },
  {
    "id": "highway_db.public.bss_business_day_data.update_ts",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.update_ts",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "update_ts",
    "comment": "记录最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.026,
    "null_rate": 0.058
  },
  {
    "id": "highway_db.public.bss_business_day_data.updated_by",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.updated_by",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "updated_by",
    "comment": "最后更新人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_business_day_data.delete_ts",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.delete_ts",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "delete_ts",
    "comment": "逻辑删除时间戳（为空表示未删除）",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_business_day_data.deleted_by",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.deleted_by",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "deleted_by",
    "comment": "逻辑删除人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_business_day_data.oper_date",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.oper_date",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "oper_date",
    "comment": "统计日期",
    "data_type": "date",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.002,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_business_day_data.service_no",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.service_no",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "service_no",
    "comment": "服务区编码",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.17,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_business_day_data.service_name",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.service_name",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "service_name",
    "comment": "服务区名称",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.096,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_business_day_data.branch_no",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.branch_no",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "branch_no",
    "comment": "档口编码",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.777,
    "null_rate": 0.004
  },
  {
    "id": "highway_db.public.bss_business_day_data.branch_name",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.branch_name",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "branch_name",
    "comment": "档口名称",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.709,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_business_day_data.wx",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.wx",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "wx",
    "comment": "微信支付金额（单位：元）",
    "data_type": "numeric",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.562,
    "null_rate": 0.386
  },
  {
    "id": "highway_db.public.bss_business_day_data.wx_order",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.wx_order",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "wx_order",
    "comment": "微信订单数量",
    "data_type": "integer",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.255,
    "null_rate": 0.386
  },
  {
    "id": "highway_db.public.bss_business_day_data.zfb",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.zfb",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "zfb",
    "comment": "支付宝支付金额（单位：元）",
    "data_type": "numeric",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.236,
    "null_rate": 0.386
  },
  {
    "id": "highway_db.public.bss_business_day_data.zf_order",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.zf_order",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "zf_order",
    "comment": "支付宝订单数量",
    "data_type": "integer",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.057,
    "null_rate": 0.386
  },
  {
    "id": "highway_db.public.bss_business_day_data.rmb",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.rmb",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "rmb",
    "comment": "现金支付金额（单位：元）",
    "data_type": "numeric",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.363,
    "null_rate": 0.386
  },
  {
    "id": "highway_db.public.bss_business_day_data.rmb_order",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.rmb_order",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "rmb_order",
    "comment": "现金支付订单数量",
    "data_type": "integer",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.071,
    "null_rate": 0.386
  },
  {
    "id": "highway_db.public.bss_business_day_data.xs",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.xs",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "xs",
    "comment": "信用卡支付金额（单位：元）",
    "data_type": "numeric",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.034,
    "null_rate": 0.386
  },
  {
    "id": "highway_db.public.bss_business_day_data.xs_order",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.xs_order",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "xs_order",
    "comment": "行吧支付数量",
    "data_type": "integer",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.015,
    "null_rate": 0.386
  },
  {
    "id": "highway_db.public.bss_business_day_data.jd",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.jd",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "jd",
    "comment": "京东支付金额（单位：元）",
    "data_type": "numeric",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.001,
    "null_rate": 0.386
  },
  {
    "id": "highway_db.public.bss_business_day_data.jd_order",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.jd_order",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "jd_order",
    "comment": "金豆支付数量",
    "data_type": "integer",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.001,
    "null_rate": 0.386
  },
  {
    "id": "highway_db.public.bss_business_day_data.order_sum",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.order_sum",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "order_sum",
    "comment": "订单总数",
    "data_type": "integer",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.276,
    "null_rate": 0.386
  },
  {
    "id": "highway_db.public.bss_business_day_data.pay_sum",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.pay_sum",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "pay_sum",
    "comment": "当日总支付金额（单位：元）",
    "data_type": "numeric",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.738,
    "null_rate": 0.049
  },
  {
    "id": "highway_db.public.bss_business_day_data.source_type",
    "database": "highway_db",
    "full_name": "public.bss_business_day_data.source_type",
    "schema": "public",
    "table": "bss_business_day_data",
    "name": "source_type",
    "comment": "数据来源类别",
    "data_type": "integer",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.004,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.id",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.id",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "id",
    "comment": "汽车日统计记录唯一标识ID",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 1,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.version",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.version",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "version",
    "comment": "数据版本号，用于乐观锁控制",
    "data_type": "integer",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.001,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.create_ts",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.create_ts",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "create_ts",
    "comment": "记录创建时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.243,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.created_by",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.created_by",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "created_by",
    "comment": "创建人用户名或系统标识",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.update_ts",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.update_ts",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "update_ts",
    "comment": "记录最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.243,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.updated_by",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.updated_by",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "updated_by",
    "comment": "最后更新人用户名或系统标识",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.delete_ts",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.delete_ts",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "delete_ts",
    "comment": "逻辑删除时间戳（为空表示未删除）",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.deleted_by",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.deleted_by",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "deleted_by",
    "comment": "逻辑删除人用户名或系统标识",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.customer_count",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.customer_count",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "customer_count",
    "comment": "车辆数量",
    "data_type": "bigint",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.668,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.car_type",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.car_type",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "car_type",
    "comment": "车辆类别",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.004,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.count_date",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.count_date",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "count_date",
    "comment": "统计日期",
    "data_type": "date",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.046,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_car_day_count.service_area_id",
    "database": "highway_db",
    "full_name": "public.bss_car_day_count.service_area_id",
    "schema": "public",
    "table": "bss_car_day_count",
    "name": "service_area_id",
    "comment": "服务区id",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.094,
    "null_rate": 0.583
  },
  {
    "id": "highway_db.public.bss_company.id",
    "database": "highway_db",
    "full_name": "public.bss_company.id",
    "schema": "public",
    "table": "bss_company",
    "name": "id",
    "comment": "公司唯一标识ID（UUID格式）",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 1,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_company.version",
    "database": "highway_db",
    "full_name": "public.bss_company.version",
    "schema": "public",
    "table": "bss_company",
    "name": "version",
    "comment": "数据版本号，用于乐观锁控制",
    "data_type": "integer",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.2222,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_company.create_ts",
    "database": "highway_db",
    "full_name": "public.bss_company.create_ts",
    "schema": "public",
    "table": "bss_company",
    "name": "create_ts",
    "comment": "记录创建时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_company.created_by",
    "database": "highway_db",
    "full_name": "public.bss_company.created_by",
    "schema": "public",
    "table": "bss_company",
    "name": "created_by",
    "comment": "创建人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.1111,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_company.update_ts",
    "database": "highway_db",
    "full_name": "public.bss_company.update_ts",
    "schema": "public",
    "table": "bss_company",
    "name": "update_ts",
    "comment": "记录最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_company.updated_by",
    "database": "highway_db",
    "full_name": "public.bss_company.updated_by",
    "schema": "public",
    "table": "bss_company",
    "name": "updated_by",
    "comment": "最后更新人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.1111,
    "null_rate": 0.8889
  },
  {
    "id": "highway_db.public.bss_company.delete_ts",
    "database": "highway_db",
    "full_name": "public.bss_company.delete_ts",
    "schema": "public",
    "table": "bss_company",
    "name": "delete_ts",
    "comment": "逻辑删除时间戳（NULL表示未删除）",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_company.deleted_by",
    "database": "highway_db",
    "full_name": "public.bss_company.deleted_by",
    "schema": "public",
    "table": "bss_company",
    "name": "deleted_by",
    "comment": "逻辑删除操作人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_company.company_name",
    "database": "highway_db",
    "full_name": "public.bss_company.company_name",
    "schema": "public",
    "table": "bss_company",
    "name": "company_name",
    "comment": "公司名称",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_company.company_no",
    "database": "highway_db",
    "full_name": "public.bss_company.company_no",
    "schema": "public",
    "table": "bss_company",
    "name": "company_no",
    "comment": "公司编码",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_section_route.id",
    "database": "highway_db",
    "full_name": "public.bss_section_route.id",
    "schema": "public",
    "table": "bss_section_route",
    "name": "id",
    "comment": "路段路由记录唯一标识ID",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 1,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_section_route.version",
    "database": "highway_db",
    "full_name": "public.bss_section_route.version",
    "schema": "public",
    "table": "bss_section_route",
    "name": "version",
    "comment": "数据版本号，用于乐观锁控制",
    "data_type": "integer",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.037,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_section_route.create_ts",
    "database": "highway_db",
    "full_name": "public.bss_section_route.create_ts",
    "schema": "public",
    "table": "bss_section_route",
    "name": "create_ts",
    "comment": "记录创建时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.2037,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_section_route.created_by",
    "database": "highway_db",
    "full_name": "public.bss_section_route.created_by",
    "schema": "public",
    "table": "bss_section_route",
    "name": "created_by",
    "comment": "创建人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0185,
    "null_rate": 0.1481
  },
  {
    "id": "highway_db.public.bss_section_route.update_ts",
    "database": "highway_db",
    "full_name": "public.bss_section_route.update_ts",
    "schema": "public",
    "table": "bss_section_route",
    "name": "update_ts",
    "comment": "记录最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_section_route.updated_by",
    "database": "highway_db",
    "full_name": "public.bss_section_route.updated_by",
    "schema": "public",
    "table": "bss_section_route",
    "name": "updated_by",
    "comment": "最后更新人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_section_route.delete_ts",
    "database": "highway_db",
    "full_name": "public.bss_section_route.delete_ts",
    "schema": "public",
    "table": "bss_section_route",
    "name": "delete_ts",
    "comment": "逻辑删除时间戳（为空表示未删除）",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_section_route.deleted_by",
    "database": "highway_db",
    "full_name": "public.bss_section_route.deleted_by",
    "schema": "public",
    "table": "bss_section_route",
    "name": "deleted_by",
    "comment": "逻辑删除人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_section_route.section_name",
    "database": "highway_db",
    "full_name": "public.bss_section_route.section_name",
    "schema": "public",
    "table": "bss_section_route",
    "name": "section_name",
    "comment": "路段名称",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.8333,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_section_route.route_name",
    "database": "highway_db",
    "full_name": "public.bss_section_route.route_name",
    "schema": "public",
    "table": "bss_section_route",
    "name": "route_name",
    "comment": "路线名称",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.5926,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_section_route.code",
    "database": "highway_db",
    "full_name": "public.bss_section_route.code",
    "schema": "public",
    "table": "bss_section_route",
    "name": "code",
    "comment": "编号",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.963,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_section_route_area_link.section_route_id",
    "database": "highway_db",
    "full_name": "public.bss_section_route_area_link.section_route_id",
    "schema": "public",
    "table": "bss_section_route_area_link",
    "name": "section_route_id",
    "comment": "路线id",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 1,
    "uniqueness": 0.525,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_section_route_area_link.service_area_id",
    "database": "highway_db",
    "full_name": "public.bss_section_route_area_link.service_area_id",
    "schema": "public",
    "table": "bss_section_route_area_link",
    "name": "service_area_id",
    "comment": "服务区id",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 2,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area.id",
    "database": "highway_db",
    "full_name": "public.bss_service_area.id",
    "schema": "public",
    "table": "bss_service_area",
    "name": "id",
    "comment": "服务区域唯一标识ID",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 1,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area.version",
    "database": "highway_db",
    "full_name": "public.bss_service_area.version",
    "schema": "public",
    "table": "bss_service_area",
    "name": "version",
    "comment": "数据版本号，用于乐观锁控制",
    "data_type": "integer",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0583,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area.create_ts",
    "database": "highway_db",
    "full_name": "public.bss_service_area.create_ts",
    "schema": "public",
    "table": "bss_service_area",
    "name": "create_ts",
    "comment": "记录创建时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.7083,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area.created_by",
    "database": "highway_db",
    "full_name": "public.bss_service_area.created_by",
    "schema": "public",
    "table": "bss_service_area",
    "name": "created_by",
    "comment": "创建人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0083,
    "null_rate": 0.0333
  },
  {
    "id": "highway_db.public.bss_service_area.update_ts",
    "database": "highway_db",
    "full_name": "public.bss_service_area.update_ts",
    "schema": "public",
    "table": "bss_service_area",
    "name": "update_ts",
    "comment": "记录最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.375,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area.updated_by",
    "database": "highway_db",
    "full_name": "public.bss_service_area.updated_by",
    "schema": "public",
    "table": "bss_service_area",
    "name": "updated_by",
    "comment": "最后更新人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0083,
    "null_rate": 0.0333
  },
  {
    "id": "highway_db.public.bss_service_area.delete_ts",
    "database": "highway_db",
    "full_name": "public.bss_service_area.delete_ts",
    "schema": "public",
    "table": "bss_service_area",
    "name": "delete_ts",
    "comment": "逻辑删除时间戳（NULL表示未删除）",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_service_area.deleted_by",
    "database": "highway_db",
    "full_name": "public.bss_service_area.deleted_by",
    "schema": "public",
    "table": "bss_service_area",
    "name": "deleted_by",
    "comment": "逻辑删除操作人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0083,
    "null_rate": 0.9917
  },
  {
    "id": "highway_db.public.bss_service_area.service_area_name",
    "database": "highway_db",
    "full_name": "public.bss_service_area.service_area_name",
    "schema": "public",
    "table": "bss_service_area",
    "name": "service_area_name",
    "comment": "服务区名称",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area.service_area_no",
    "database": "highway_db",
    "full_name": "public.bss_service_area.service_area_no",
    "schema": "public",
    "table": "bss_service_area",
    "name": "service_area_no",
    "comment": "服务区编码",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.9917,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area.company_id",
    "database": "highway_db",
    "full_name": "public.bss_service_area.company_id",
    "schema": "public",
    "table": "bss_service_area",
    "name": "company_id",
    "comment": "公司id",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0667,
    "null_rate": 0.1833
  },
  {
    "id": "highway_db.public.bss_service_area.service_position",
    "database": "highway_db",
    "full_name": "public.bss_service_area.service_position",
    "schema": "public",
    "table": "bss_service_area",
    "name": "service_position",
    "comment": "服务区经纬度",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.9917,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area.service_area_type",
    "database": "highway_db",
    "full_name": "public.bss_service_area.service_area_type",
    "schema": "public",
    "table": "bss_service_area",
    "name": "service_area_type",
    "comment": "服务区类型",
    "data_type": "character varying",
    "semantic_role": "enum",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0167,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area.service_state",
    "database": "highway_db",
    "full_name": "public.bss_service_area.service_state",
    "schema": "public",
    "table": "bss_service_area",
    "name": "service_state",
    "comment": "服务区状态",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.025,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.id",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.id",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "id",
    "comment": "服务区域映射记录唯一标识ID",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 1,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.version",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.version",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "version",
    "comment": "数据版本号，用于乐观锁控制",
    "data_type": "integer",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0095,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.create_ts",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.create_ts",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "create_ts",
    "comment": "记录创建时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.6183,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.created_by",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.created_by",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "created_by",
    "comment": "创建人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0063,
    "null_rate": 0.1073
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.update_ts",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.update_ts",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "update_ts",
    "comment": "记录最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.3596,
    "null_rate": 0.0946
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.updated_by",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.updated_by",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "updated_by",
    "comment": "最后更新人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0032,
    "null_rate": 0.7287
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.delete_ts",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.delete_ts",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "delete_ts",
    "comment": "逻辑删除时间戳（NULL表示未删除）",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.deleted_by",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.deleted_by",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "deleted_by",
    "comment": "逻辑删除人用户名",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 1.0
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.service_name",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.service_name",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "service_name",
    "comment": "服务区名称",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.3912,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.service_no",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.service_no",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "service_no",
    "comment": "服务区编码",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.9432,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.service_area_id",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.service_area_id",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "service_area_id",
    "comment": "服务区id",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.3754,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.source_system_type",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.source_system_type",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "source_system_type",
    "comment": "数据来源类别名称",
    "data_type": "character varying",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0158,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.bss_service_area_mapper.source_type",
    "database": "highway_db",
    "full_name": "public.bss_service_area_mapper.source_type",
    "schema": "public",
    "table": "bss_service_area_mapper",
    "name": "source_type",
    "comment": "数据来源类别id",
    "data_type": "integer",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0158,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.highway_metadata.id",
    "database": "highway_db",
    "full_name": "public.highway_metadata.id",
    "schema": "public",
    "table": "highway_metadata",
    "name": "id",
    "comment": "元数据记录唯一标识ID",
    "data_type": "integer",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 1,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.highway_metadata.topic_code",
    "database": "highway_db",
    "full_name": "public.highway_metadata.topic_code",
    "schema": "public",
    "table": "highway_metadata",
    "name": "topic_code",
    "comment": "主题编码（如日营收、车流量等）",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.highway_metadata.topic_name",
    "database": "highway_db",
    "full_name": "public.highway_metadata.topic_name",
    "schema": "public",
    "table": "highway_metadata",
    "name": "topic_name",
    "comment": "主题中文名称",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.highway_metadata.description",
    "database": "highway_db",
    "full_name": "public.highway_metadata.description",
    "schema": "public",
    "table": "highway_metadata",
    "name": "description",
    "comment": "主题业务描述与分析口径说明",
    "data_type": "text",
    "semantic_role": "description",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.highway_metadata.related_tables",
    "database": "highway_db",
    "full_name": "public.highway_metadata.related_tables",
    "schema": "public",
    "table": "highway_metadata",
    "name": "related_tables",
    "comment": "关联的源数据表名数组",
    "data_type": "array",
    "semantic_role": "complex",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.highway_metadata.questions",
    "database": "highway_db",
    "full_name": "public.highway_metadata.questions",
    "schema": "public",
    "table": "highway_metadata",
    "name": "questions",
    "comment": "常见业务问题及对应SQL查询语句",
    "data_type": "jsonb",
    "semantic_role": "complex",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.highway_metadata.keywords",
    "database": "highway_db",
    "full_name": "public.highway_metadata.keywords",
    "schema": "public",
    "table": "highway_metadata",
    "name": "keywords",
    "comment": "主题相关关键词数组",
    "data_type": "array",
    "semantic_role": "complex",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.highway_metadata.theme_tag",
    "database": "highway_db",
    "full_name": "public.highway_metadata.theme_tag",
    "schema": "public",
    "table": "highway_metadata",
    "name": "theme_tag",
    "comment": "主题分类标签（如交易分析、流量分析等）",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.highway_metadata.update_ts",
    "database": "highway_db",
    "full_name": "public.highway_metadata.update_ts",
    "schema": "public",
    "table": "highway_metadata",
    "name": "update_ts",
    "comment": "元数据最后更新时间",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.qa_feedback.id",
    "database": "highway_db",
    "full_name": "public.qa_feedback.id",
    "schema": "public",
    "table": "qa_feedback",
    "name": "id",
    "comment": "反馈记录唯一标识ID",
    "data_type": "integer",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 1,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.qa_feedback.question",
    "database": "highway_db",
    "full_name": "public.qa_feedback.question",
    "schema": "public",
    "table": "qa_feedback",
    "name": "question",
    "comment": "用户提出的自然语言问题",
    "data_type": "text",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.8,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.qa_feedback.sql",
    "database": "highway_db",
    "full_name": "public.qa_feedback.sql",
    "schema": "public",
    "table": "qa_feedback",
    "name": "sql",
    "comment": "系统生成的对应SQL查询语句",
    "data_type": "text",
    "semantic_role": "description",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.8,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.qa_feedback.is_thumb_up",
    "database": "highway_db",
    "full_name": "public.qa_feedback.is_thumb_up",
    "schema": "public",
    "table": "qa_feedback",
    "name": "is_thumb_up",
    "comment": "用户是否点赞（True-是，False-否）",
    "data_type": "boolean",
    "semantic_role": "enum",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.1,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.qa_feedback.user_id",
    "database": "highway_db",
    "full_name": "public.qa_feedback.user_id",
    "schema": "public",
    "table": "qa_feedback",
    "name": "user_id",
    "comment": "提交反馈的用户账号标识",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.9,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.qa_feedback.create_time",
    "database": "highway_db",
    "full_name": "public.qa_feedback.create_time",
    "schema": "public",
    "table": "qa_feedback",
    "name": "create_time",
    "comment": "反馈记录创建时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.qa_feedback.is_in_training_data",
    "database": "highway_db",
    "full_name": "public.qa_feedback.is_in_training_data",
    "schema": "public",
    "table": "qa_feedback",
    "name": "is_in_training_data",
    "comment": "是否已纳入训练数据集（True-是，False-否）",
    "data_type": "boolean",
    "semantic_role": "enum",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.1,
    "null_rate": 0.0
  },
  {
    "id": "highway_db.public.qa_feedback.update_time",
    "database": "highway_db",
    "full_name": "public.qa_feedback.update_time",
    "schema": "public",
    "table": "qa_feedback",
    "name": "update_time",
    "comment": "反馈记录最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.1,
    "null_rate": 0.8
  }
] AS c
	MERGE (n:Column {full_name: c.full_name})
	SET n.id           = c.id,
	    n.database     = c.database,
	    n.schema       = c.schema,
	    n.table        = c.table,
	    n.name         = c.name,
	    n.comment      = c.comment,
	    n.data_type    = c.data_type,
	    n.semantic_role= c.semantic_role,
    n.is_pk        = c.is_pk,
    n.is_uk        = c.is_uk,
    n.is_fk        = c.is_fk,
    n.is_time      = c.is_time,
    n.is_measure   = c.is_measure,
    n.pk_position  = c.pk_position,
    n.uniqueness   = c.uniqueness,
    n.null_rate    = c.null_rate;

// =====================================================================
// 4. 建立 HAS_COLUMN 关系
// =====================================================================

UNWIND [
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.id"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.version"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.create_ts"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.created_by"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.update_ts"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.updated_by"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.delete_ts"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.deleted_by"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.branch_name"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.branch_no"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.service_area_id"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.company_id"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.classify"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.product_brand"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.category"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.section_route_id"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.direction"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.is_manual_entry"
  },
  {
    "table_full_name": "public.bss_branch",
    "column_full_name": "public.bss_branch.co_company"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.id"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.version"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.create_ts"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.created_by"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.update_ts"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.updated_by"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.delete_ts"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.deleted_by"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.oper_date"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.service_no"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.service_name"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.branch_no"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.branch_name"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.wx"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.wx_order"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.zfb"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.zf_order"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.rmb"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.rmb_order"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.xs"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.xs_order"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.jd"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.jd_order"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.order_sum"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.pay_sum"
  },
  {
    "table_full_name": "public.bss_business_day_data",
    "column_full_name": "public.bss_business_day_data.source_type"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.id"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.version"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.create_ts"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.created_by"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.update_ts"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.updated_by"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.delete_ts"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.deleted_by"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.customer_count"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.car_type"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.count_date"
  },
  {
    "table_full_name": "public.bss_car_day_count",
    "column_full_name": "public.bss_car_day_count.service_area_id"
  },
  {
    "table_full_name": "public.bss_company",
    "column_full_name": "public.bss_company.id"
  },
  {
    "table_full_name": "public.bss_company",
    "column_full_name": "public.bss_company.version"
  },
  {
    "table_full_name": "public.bss_company",
    "column_full_name": "public.bss_company.create_ts"
  },
  {
    "table_full_name": "public.bss_company",
    "column_full_name": "public.bss_company.created_by"
  },
  {
    "table_full_name": "public.bss_company",
    "column_full_name": "public.bss_company.update_ts"
  },
  {
    "table_full_name": "public.bss_company",
    "column_full_name": "public.bss_company.updated_by"
  },
  {
    "table_full_name": "public.bss_company",
    "column_full_name": "public.bss_company.delete_ts"
  },
  {
    "table_full_name": "public.bss_company",
    "column_full_name": "public.bss_company.deleted_by"
  },
  {
    "table_full_name": "public.bss_company",
    "column_full_name": "public.bss_company.company_name"
  },
  {
    "table_full_name": "public.bss_company",
    "column_full_name": "public.bss_company.company_no"
  },
  {
    "table_full_name": "public.bss_section_route",
    "column_full_name": "public.bss_section_route.id"
  },
  {
    "table_full_name": "public.bss_section_route",
    "column_full_name": "public.bss_section_route.version"
  },
  {
    "table_full_name": "public.bss_section_route",
    "column_full_name": "public.bss_section_route.create_ts"
  },
  {
    "table_full_name": "public.bss_section_route",
    "column_full_name": "public.bss_section_route.created_by"
  },
  {
    "table_full_name": "public.bss_section_route",
    "column_full_name": "public.bss_section_route.update_ts"
  },
  {
    "table_full_name": "public.bss_section_route",
    "column_full_name": "public.bss_section_route.updated_by"
  },
  {
    "table_full_name": "public.bss_section_route",
    "column_full_name": "public.bss_section_route.delete_ts"
  },
  {
    "table_full_name": "public.bss_section_route",
    "column_full_name": "public.bss_section_route.deleted_by"
  },
  {
    "table_full_name": "public.bss_section_route",
    "column_full_name": "public.bss_section_route.section_name"
  },
  {
    "table_full_name": "public.bss_section_route",
    "column_full_name": "public.bss_section_route.route_name"
  },
  {
    "table_full_name": "public.bss_section_route",
    "column_full_name": "public.bss_section_route.code"
  },
  {
    "table_full_name": "public.bss_section_route_area_link",
    "column_full_name": "public.bss_section_route_area_link.section_route_id"
  },
  {
    "table_full_name": "public.bss_section_route_area_link",
    "column_full_name": "public.bss_section_route_area_link.service_area_id"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.id"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.version"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.create_ts"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.created_by"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.update_ts"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.updated_by"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.delete_ts"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.deleted_by"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.service_area_name"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.service_area_no"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.company_id"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.service_position"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.service_area_type"
  },
  {
    "table_full_name": "public.bss_service_area",
    "column_full_name": "public.bss_service_area.service_state"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.id"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.version"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.create_ts"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.created_by"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.update_ts"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.updated_by"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.delete_ts"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.deleted_by"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.service_name"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.service_no"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.service_area_id"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.source_system_type"
  },
  {
    "table_full_name": "public.bss_service_area_mapper",
    "column_full_name": "public.bss_service_area_mapper.source_type"
  },
  {
    "table_full_name": "public.highway_metadata",
    "column_full_name": "public.highway_metadata.id"
  },
  {
    "table_full_name": "public.highway_metadata",
    "column_full_name": "public.highway_metadata.topic_code"
  },
  {
    "table_full_name": "public.highway_metadata",
    "column_full_name": "public.highway_metadata.topic_name"
  },
  {
    "table_full_name": "public.highway_metadata",
    "column_full_name": "public.highway_metadata.description"
  },
  {
    "table_full_name": "public.highway_metadata",
    "column_full_name": "public.highway_metadata.related_tables"
  },
  {
    "table_full_name": "public.highway_metadata",
    "column_full_name": "public.highway_metadata.questions"
  },
  {
    "table_full_name": "public.highway_metadata",
    "column_full_name": "public.highway_metadata.keywords"
  },
  {
    "table_full_name": "public.highway_metadata",
    "column_full_name": "public.highway_metadata.theme_tag"
  },
  {
    "table_full_name": "public.highway_metadata",
    "column_full_name": "public.highway_metadata.update_ts"
  },
  {
    "table_full_name": "public.qa_feedback",
    "column_full_name": "public.qa_feedback.id"
  },
  {
    "table_full_name": "public.qa_feedback",
    "column_full_name": "public.qa_feedback.question"
  },
  {
    "table_full_name": "public.qa_feedback",
    "column_full_name": "public.qa_feedback.sql"
  },
  {
    "table_full_name": "public.qa_feedback",
    "column_full_name": "public.qa_feedback.is_thumb_up"
  },
  {
    "table_full_name": "public.qa_feedback",
    "column_full_name": "public.qa_feedback.user_id"
  },
  {
    "table_full_name": "public.qa_feedback",
    "column_full_name": "public.qa_feedback.create_time"
  },
  {
    "table_full_name": "public.qa_feedback",
    "column_full_name": "public.qa_feedback.is_in_training_data"
  },
  {
    "table_full_name": "public.qa_feedback",
    "column_full_name": "public.qa_feedback.update_time"
  }
] AS hc
MATCH (t:Table {full_name: hc.table_full_name})
MATCH (c:Column {full_name: hc.column_full_name})
MERGE (t)-[:HAS_COLUMN]->(c);

// =====================================================================
// 5. 建立 JOIN_ON 关系
// =====================================================================

UNWIND [] AS j
MATCH (src:Table {full_name: j.src_full_name})
MATCH (dst:Table {full_name: j.dst_full_name})
MERGE (src)-[r:JOIN_ON]->(dst)
SET r.cardinality     = j.cardinality,
    r.constraint_name = j.constraint_name,
    r.join_type       = coalesce(j.join_type, 'INNER JOIN'),
    r.on              = j.on,
    r.source_columns  = j.source_columns,
    r.target_columns  = j.target_columns,
    r.source_table    = j.source_table,
    r.target_table    = j.target_table;
