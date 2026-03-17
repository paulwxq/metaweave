// import_all.dvdrental.cypher
// Neo4j 元数据导入脚本（global 模式，包含所有表和关系）
// 生成时间: 2026-03-17T08:21:14.661577
// 统计: 15 张表, 86 个列, 18 个关系

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
    "id": "dvdrental.public.actor",
    "database": "dvdrental",
    "full_name": "public.actor",
    "schema": "public",
    "name": "actor",
    "comment": "演员信息表，存储电影演员的姓名及最后更新时间",
    "pk": [
      "actor_id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "last_name"
      ]
    ],
    "table_domains": [
      "内容分类与演职人员"
    ],
    "table_category": "dim"
  },
  {
    "id": "dvdrental.public.address",
    "database": "dvdrental",
    "full_name": "public.address",
    "schema": "public",
    "name": "address",
    "comment": "地址信息表，存储客户或实体的详细地理位置及联系方式",
    "pk": [
      "address_id"
    ],
    "uk": [],
    "fk": [
      [
        "city_id"
      ]
    ],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "city_id"
      ]
    ],
    "table_domains": [
      "地理信息管理"
    ],
    "table_category": "dim"
  },
  {
    "id": "dvdrental.public.category",
    "database": "dvdrental",
    "full_name": "public.category",
    "schema": "public",
    "name": "category",
    "comment": "电影分类表，存储影片类别名称及最后更新时间",
    "pk": [
      "category_id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [],
    "table_domains": [
      "内容分类与演职人员"
    ],
    "table_category": "dim"
  },
  {
    "id": "dvdrental.public.city",
    "database": "dvdrental",
    "full_name": "public.city",
    "schema": "public",
    "name": "city",
    "comment": "城市信息表，存储全球城市名称、所属国家及更新时间",
    "pk": [
      "city_id"
    ],
    "uk": [],
    "fk": [
      [
        "country_id"
      ]
    ],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "country_id"
      ]
    ],
    "table_domains": [
      "地理信息管理"
    ],
    "table_category": "dim"
  },
  {
    "id": "dvdrental.public.country",
    "database": "dvdrental",
    "full_name": "public.country",
    "schema": "public",
    "name": "country",
    "comment": "国家信息表，存储世界各国名称及最后更新时间",
    "pk": [
      "country_id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [],
    "table_domains": [
      "地理信息管理"
    ],
    "table_category": "dim"
  },
  {
    "id": "dvdrental.public.customer",
    "database": "dvdrental",
    "full_name": "public.customer",
    "schema": "public",
    "name": "customer",
    "comment": "客户信息表，存储客户的姓名、联系方式、地址及账户状态等基本信息",
    "pk": [
      "customer_id"
    ],
    "uk": [],
    "fk": [
      [
        "address_id"
      ]
    ],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "address_id"
      ],
      [
        "store_id"
      ],
      [
        "last_name"
      ]
    ],
    "table_domains": [
      "客户与账户管理"
    ],
    "table_category": "dim"
  },
  {
    "id": "dvdrental.public.film",
    "database": "dvdrental",
    "full_name": "public.film",
    "schema": "public",
    "name": "film",
    "comment": "电影信息表，存储影片标题、描述、年份、语言、租借参数、时长、分级等元数据",
    "pk": [
      "film_id"
    ],
    "uk": [],
    "fk": [
      [
        "language_id"
      ]
    ],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "fulltext"
      ],
      [
        "language_id"
      ],
      [
        "title"
      ]
    ],
    "table_domains": [
      "影片内容资产"
    ],
    "table_category": "dim"
  },
  {
    "id": "dvdrental.public.film_actor",
    "database": "dvdrental",
    "full_name": "public.film_actor",
    "schema": "public",
    "name": "film_actor",
    "comment": "电影与演员的关联表，记录演员参演电影的关系及更新时间",
    "pk": [
      "actor_id",
      "film_id"
    ],
    "uk": [],
    "fk": [
      [
        "actor_id"
      ],
      [
        "film_id"
      ]
    ],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "film_id"
      ]
    ],
    "table_domains": [
      "内容分类与演职人员"
    ],
    "table_category": "bridge"
  },
  {
    "id": "dvdrental.public.film_category",
    "database": "dvdrental",
    "full_name": "public.film_category",
    "schema": "public",
    "name": "film_category",
    "comment": "电影分类关联表，记录电影与分类之间的多对多关系",
    "pk": [
      "film_id",
      "category_id"
    ],
    "uk": [],
    "fk": [
      [
        "category_id"
      ],
      [
        "film_id"
      ]
    ],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [],
    "table_domains": [
      "内容分类与演职人员"
    ],
    "table_category": "bridge"
  },
  {
    "id": "dvdrental.public.inventory",
    "database": "dvdrental",
    "full_name": "public.inventory",
    "schema": "public",
    "name": "inventory",
    "comment": "库存记录表，存储影片在各门店的库存数量及最后更新时间",
    "pk": [
      "inventory_id"
    ],
    "uk": [],
    "fk": [
      [
        "film_id"
      ]
    ],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "store_id",
        "film_id"
      ]
    ],
    "table_domains": [
      "租赁交易与履约"
    ],
    "table_category": "fact"
  },
  {
    "id": "dvdrental.public.language",
    "database": "dvdrental",
    "full_name": "public.language",
    "schema": "public",
    "name": "language",
    "comment": "语言信息表，存储系统支持的语言名称及更新时间",
    "pk": [
      "language_id"
    ],
    "uk": [],
    "fk": [],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [],
    "table_domains": [
      "影片内容资产"
    ],
    "table_category": "dim"
  },
  {
    "id": "dvdrental.public.payment",
    "database": "dvdrental",
    "full_name": "public.payment",
    "schema": "public",
    "name": "payment",
    "comment": "支付记录表，存储客户租赁服务的付款明细及交易时间",
    "pk": [
      "payment_id"
    ],
    "uk": [],
    "fk": [
      [
        "customer_id"
      ],
      [
        "rental_id"
      ],
      [
        "staff_id"
      ]
    ],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "customer_id"
      ],
      [
        "rental_id"
      ],
      [
        "staff_id"
      ]
    ],
    "table_domains": [
      "财务结算"
    ],
    "table_category": "fact"
  },
  {
    "id": "dvdrental.public.rental",
    "database": "dvdrental",
    "full_name": "public.rental",
    "schema": "public",
    "name": "rental",
    "comment": "租赁记录表，存储影片租借的起止时间、租借人、库存项及经办员工信息",
    "pk": [
      "rental_id"
    ],
    "uk": [],
    "fk": [
      [
        "customer_id"
      ],
      [
        "inventory_id"
      ],
      [
        "staff_id"
      ]
    ],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [
      [
        "inventory_id"
      ]
    ],
    "table_domains": [
      "租赁交易与履约"
    ],
    "table_category": "fact"
  },
  {
    "id": "dvdrental.public.staff",
    "database": "dvdrental",
    "full_name": "public.staff",
    "schema": "public",
    "name": "staff",
    "comment": "员工信息表，存储门店员工的基本资料、联系方式、账户凭证及状态",
    "pk": [
      "staff_id"
    ],
    "uk": [],
    "fk": [
      [
        "address_id"
      ]
    ],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [],
    "table_domains": [
      "门店与组织架构"
    ],
    "table_category": "dim"
  },
  {
    "id": "dvdrental.public.store",
    "database": "dvdrental",
    "full_name": "public.store",
    "schema": "public",
    "name": "store",
    "comment": "门店信息表，存储门店编号、负责人、地址及最后更新时间",
    "pk": [
      "store_id"
    ],
    "uk": [],
    "fk": [
      [
        "address_id"
      ],
      [
        "manager_staff_id"
      ]
    ],
    "logic_pk": [],
    "logic_fk": [],
    "logic_uk": [],
    "indexes": [],
    "table_domains": [
      "门店与组织架构"
    ],
    "table_category": "dim"
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
    "id": "dvdrental.public.actor.actor_id",
    "database": "dvdrental",
    "full_name": "public.actor.actor_id",
    "schema": "public",
    "table": "actor",
    "name": "actor_id",
    "comment": "演员唯一标识ID",
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
    "id": "dvdrental.public.actor.first_name",
    "database": "dvdrental",
    "full_name": "public.actor.first_name",
    "schema": "public",
    "table": "actor",
    "name": "first_name",
    "comment": "演员名字",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.64,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.actor.last_name",
    "database": "dvdrental",
    "full_name": "public.actor.last_name",
    "schema": "public",
    "table": "actor",
    "name": "last_name",
    "comment": "演员姓氏",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.605,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.actor.last_update",
    "database": "dvdrental",
    "full_name": "public.actor.last_update",
    "schema": "public",
    "table": "actor",
    "name": "last_update",
    "comment": "记录最后更新时间",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.005,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.address.address_id",
    "database": "dvdrental",
    "full_name": "public.address.address_id",
    "schema": "public",
    "table": "address",
    "name": "address_id",
    "comment": "地址唯一标识ID",
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
    "id": "dvdrental.public.address.address",
    "database": "dvdrental",
    "full_name": "public.address.address",
    "schema": "public",
    "table": "address",
    "name": "address",
    "comment": "详细街道地址",
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
    "id": "dvdrental.public.address.address2",
    "database": "dvdrental",
    "full_name": "public.address.address2",
    "schema": "public",
    "table": "address",
    "name": "address2",
    "comment": "补充地址（如公寓号、楼层等）",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0017,
    "null_rate": 0.0066
  },
  {
    "id": "dvdrental.public.address.district",
    "database": "dvdrental",
    "full_name": "public.address.district",
    "schema": "public",
    "table": "address",
    "name": "district",
    "comment": "所属行政区/区名",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.6269,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.address.city_id",
    "database": "dvdrental",
    "full_name": "public.address.city_id",
    "schema": "public",
    "table": "address",
    "name": "city_id",
    "comment": "所属城市的唯一标识ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.9934,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.address.postal_code",
    "database": "dvdrental",
    "full_name": "public.address.postal_code",
    "schema": "public",
    "table": "address",
    "name": "postal_code",
    "comment": "邮政编码",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.99,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.address.phone",
    "database": "dvdrental",
    "full_name": "public.address.phone",
    "schema": "public",
    "table": "address",
    "name": "phone",
    "comment": "联系电话",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.9983,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.address.last_update",
    "database": "dvdrental",
    "full_name": "public.address.last_update",
    "schema": "public",
    "table": "address",
    "name": "last_update",
    "comment": "最后更新时间",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0017,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.category.category_id",
    "database": "dvdrental",
    "full_name": "public.category.category_id",
    "schema": "public",
    "table": "category",
    "name": "category_id",
    "comment": "分类唯一标识ID",
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
    "id": "dvdrental.public.category.name",
    "database": "dvdrental",
    "full_name": "public.category.name",
    "schema": "public",
    "table": "category",
    "name": "name",
    "comment": "分类名称（如动作、动画、儿童等）",
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
    "id": "dvdrental.public.category.last_update",
    "database": "dvdrental",
    "full_name": "public.category.last_update",
    "schema": "public",
    "table": "category",
    "name": "last_update",
    "comment": "最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0625,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.city.city_id",
    "database": "dvdrental",
    "full_name": "public.city.city_id",
    "schema": "public",
    "table": "city",
    "name": "city_id",
    "comment": "城市唯一标识ID",
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
    "id": "dvdrental.public.city.city",
    "database": "dvdrental",
    "full_name": "public.city.city",
    "schema": "public",
    "table": "city",
    "name": "city",
    "comment": "城市名称",
    "data_type": "character varying",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.9983,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.city.country_id",
    "database": "dvdrental",
    "full_name": "public.city.country_id",
    "schema": "public",
    "table": "city",
    "name": "country_id",
    "comment": "所属国家唯一标识ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.1817,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.city.last_update",
    "database": "dvdrental",
    "full_name": "public.city.last_update",
    "schema": "public",
    "table": "city",
    "name": "last_update",
    "comment": "最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0017,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.country.country_id",
    "database": "dvdrental",
    "full_name": "public.country.country_id",
    "schema": "public",
    "table": "country",
    "name": "country_id",
    "comment": "国家唯一标识ID",
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
    "id": "dvdrental.public.country.country",
    "database": "dvdrental",
    "full_name": "public.country.country",
    "schema": "public",
    "table": "country",
    "name": "country",
    "comment": "国家名称",
    "data_type": "character varying",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.country.last_update",
    "database": "dvdrental",
    "full_name": "public.country.last_update",
    "schema": "public",
    "table": "country",
    "name": "last_update",
    "comment": "最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0092,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.customer.customer_id",
    "database": "dvdrental",
    "full_name": "public.customer.customer_id",
    "schema": "public",
    "table": "customer",
    "name": "customer_id",
    "comment": "客户唯一标识ID",
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
    "id": "dvdrental.public.customer.store_id",
    "database": "dvdrental",
    "full_name": "public.customer.store_id",
    "schema": "public",
    "table": "customer",
    "name": "store_id",
    "comment": "所属门店ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0033,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.customer.first_name",
    "database": "dvdrental",
    "full_name": "public.customer.first_name",
    "schema": "public",
    "table": "customer",
    "name": "first_name",
    "comment": "客户名字",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.9866,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.customer.last_name",
    "database": "dvdrental",
    "full_name": "public.customer.last_name",
    "schema": "public",
    "table": "customer",
    "name": "last_name",
    "comment": "客户姓氏",
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
    "id": "dvdrental.public.customer.email",
    "database": "dvdrental",
    "full_name": "public.customer.email",
    "schema": "public",
    "table": "customer",
    "name": "email",
    "comment": "客户电子邮箱地址",
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
    "id": "dvdrental.public.customer.address_id",
    "database": "dvdrental",
    "full_name": "public.customer.address_id",
    "schema": "public",
    "table": "customer",
    "name": "address_id",
    "comment": "关联地址ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.customer.activebool",
    "database": "dvdrental",
    "full_name": "public.customer.activebool",
    "schema": "public",
    "table": "customer",
    "name": "activebool",
    "comment": "账户激活状态（true-启用，false-禁用）",
    "data_type": "boolean",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0017,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.customer.create_date",
    "database": "dvdrental",
    "full_name": "public.customer.create_date",
    "schema": "public",
    "table": "customer",
    "name": "create_date",
    "comment": "客户记录创建日期",
    "data_type": "date",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0017,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.customer.last_update",
    "database": "dvdrental",
    "full_name": "public.customer.last_update",
    "schema": "public",
    "table": "customer",
    "name": "last_update",
    "comment": "最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0017,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.customer.active",
    "database": "dvdrental",
    "full_name": "public.customer.active",
    "schema": "public",
    "table": "customer",
    "name": "active",
    "comment": "活跃状态（1-活跃，0-非活跃）",
    "data_type": "integer",
    "semantic_role": "enum",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.0033,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film.film_id",
    "database": "dvdrental",
    "full_name": "public.film.film_id",
    "schema": "public",
    "table": "film",
    "name": "film_id",
    "comment": "电影唯一标识ID",
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
    "id": "dvdrental.public.film.title",
    "database": "dvdrental",
    "full_name": "public.film.title",
    "schema": "public",
    "table": "film",
    "name": "title",
    "comment": "电影标题",
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
    "id": "dvdrental.public.film.description",
    "database": "dvdrental",
    "full_name": "public.film.description",
    "schema": "public",
    "table": "film",
    "name": "description",
    "comment": "电影剧情简介",
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
    "id": "dvdrental.public.film.release_year",
    "database": "dvdrental",
    "full_name": "public.film.release_year",
    "schema": "public",
    "table": "film",
    "name": "release_year",
    "comment": "电影上映年份",
    "data_type": "integer",
    "semantic_role": "datetime",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": true,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.001,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film.language_id",
    "database": "dvdrental",
    "full_name": "public.film.language_id",
    "schema": "public",
    "table": "film",
    "name": "language_id",
    "comment": "电影语言ID（关联language表）",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.001,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film.rental_duration",
    "database": "dvdrental",
    "full_name": "public.film.rental_duration",
    "schema": "public",
    "table": "film",
    "name": "rental_duration",
    "comment": "租赁天数（单位：天）",
    "data_type": "smallint",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.005,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film.rental_rate",
    "database": "dvdrental",
    "full_name": "public.film.rental_rate",
    "schema": "public",
    "table": "film",
    "name": "rental_rate",
    "comment": "租赁单价（单位：美元）",
    "data_type": "numeric",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.003,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film.length",
    "database": "dvdrental",
    "full_name": "public.film.length",
    "schema": "public",
    "table": "film",
    "name": "length",
    "comment": "电影时长（单位：分钟）",
    "data_type": "smallint",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.14,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film.replacement_cost",
    "database": "dvdrental",
    "full_name": "public.film.replacement_cost",
    "schema": "public",
    "table": "film",
    "name": "replacement_cost",
    "comment": "丢失/损坏赔偿金额（单位：美元）",
    "data_type": "numeric",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.021,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film.rating",
    "database": "dvdrental",
    "full_name": "public.film.rating",
    "schema": "public",
    "table": "film",
    "name": "rating",
    "comment": "电影分级（如NC-17、R、PG等）",
    "data_type": "user-defined",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.005,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film.last_update",
    "database": "dvdrental",
    "full_name": "public.film.last_update",
    "schema": "public",
    "table": "film",
    "name": "last_update",
    "comment": "最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
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
    "id": "dvdrental.public.film.special_features",
    "database": "dvdrental",
    "full_name": "public.film.special_features",
    "schema": "public",
    "table": "film",
    "name": "special_features",
    "comment": "特别花絮（数组，如预告片、幕后花絮等）",
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
    "id": "dvdrental.public.film.fulltext",
    "database": "dvdrental",
    "full_name": "public.film.fulltext",
    "schema": "public",
    "table": "film",
    "name": "fulltext",
    "comment": "全文检索向量（用于标题和简介的全文搜索）",
    "data_type": "tsvector",
    "semantic_role": "complex",
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
    "id": "dvdrental.public.film_actor.actor_id",
    "database": "dvdrental",
    "full_name": "public.film_actor.actor_id",
    "schema": "public",
    "table": "film_actor",
    "name": "actor_id",
    "comment": "演员唯一标识ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 1,
    "uniqueness": 0.039,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film_actor.film_id",
    "database": "dvdrental",
    "full_name": "public.film_actor.film_id",
    "schema": "public",
    "table": "film_actor",
    "name": "film_id",
    "comment": "电影唯一标识ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 2,
    "uniqueness": 0.614,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film_actor.last_update",
    "database": "dvdrental",
    "full_name": "public.film_actor.last_update",
    "schema": "public",
    "table": "film_actor",
    "name": "last_update",
    "comment": "记录最后更新时间",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
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
    "id": "dvdrental.public.film_category.film_id",
    "database": "dvdrental",
    "full_name": "public.film_category.film_id",
    "schema": "public",
    "table": "film_category",
    "name": "film_id",
    "comment": "电影唯一标识ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 1,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film_category.category_id",
    "database": "dvdrental",
    "full_name": "public.film_category.category_id",
    "schema": "public",
    "table": "film_category",
    "name": "category_id",
    "comment": "电影分类唯一标识ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": true,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 2,
    "uniqueness": 0.016,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.film_category.last_update",
    "database": "dvdrental",
    "full_name": "public.film_category.last_update",
    "schema": "public",
    "table": "film_category",
    "name": "last_update",
    "comment": "最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
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
    "id": "dvdrental.public.inventory.inventory_id",
    "database": "dvdrental",
    "full_name": "public.inventory.inventory_id",
    "schema": "public",
    "table": "inventory",
    "name": "inventory_id",
    "comment": "库存记录唯一标识ID",
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
    "id": "dvdrental.public.inventory.film_id",
    "database": "dvdrental",
    "full_name": "public.inventory.film_id",
    "schema": "public",
    "table": "inventory",
    "name": "film_id",
    "comment": "电影ID，关联films表",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.207,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.inventory.store_id",
    "database": "dvdrental",
    "full_name": "public.inventory.store_id",
    "schema": "public",
    "table": "inventory",
    "name": "store_id",
    "comment": "门店ID，关联stores表",
    "data_type": "smallint",
    "semantic_role": "identifier",
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
    "id": "dvdrental.public.inventory.last_update",
    "database": "dvdrental",
    "full_name": "public.inventory.last_update",
    "schema": "public",
    "table": "inventory",
    "name": "last_update",
    "comment": "最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
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
    "id": "dvdrental.public.language.language_id",
    "database": "dvdrental",
    "full_name": "public.language.language_id",
    "schema": "public",
    "table": "language",
    "name": "language_id",
    "comment": "语言唯一标识ID",
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
    "id": "dvdrental.public.language.name",
    "database": "dvdrental",
    "full_name": "public.language.name",
    "schema": "public",
    "table": "language",
    "name": "name",
    "comment": "语言名称",
    "data_type": "character",
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
    "id": "dvdrental.public.language.last_update",
    "database": "dvdrental",
    "full_name": "public.language.last_update",
    "schema": "public",
    "table": "language",
    "name": "last_update",
    "comment": "最后更新时间",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.1667,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.payment.payment_id",
    "database": "dvdrental",
    "full_name": "public.payment.payment_id",
    "schema": "public",
    "table": "payment",
    "name": "payment_id",
    "comment": "支付记录唯一标识ID",
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
    "id": "dvdrental.public.payment.customer_id",
    "database": "dvdrental",
    "full_name": "public.payment.customer_id",
    "schema": "public",
    "table": "payment",
    "name": "customer_id",
    "comment": "关联客户ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.263,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.payment.staff_id",
    "database": "dvdrental",
    "full_name": "public.payment.staff_id",
    "schema": "public",
    "table": "payment",
    "name": "staff_id",
    "comment": "处理支付的员工ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.002,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.payment.rental_id",
    "database": "dvdrental",
    "full_name": "public.payment.rental_id",
    "schema": "public",
    "table": "payment",
    "name": "rental_id",
    "comment": "关联租赁记录ID",
    "data_type": "integer",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.payment.amount",
    "database": "dvdrental",
    "full_name": "public.payment.amount",
    "schema": "public",
    "table": "payment",
    "name": "amount",
    "comment": "支付金额（单位：元）",
    "data_type": "numeric",
    "semantic_role": "metric",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": true,
    "pk_position": 0,
    "uniqueness": 0.011,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.payment.payment_date",
    "database": "dvdrental",
    "full_name": "public.payment.payment_date",
    "schema": "public",
    "table": "payment",
    "name": "payment_date",
    "comment": "支付发生的时间戳",
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
    "id": "dvdrental.public.rental.rental_id",
    "database": "dvdrental",
    "full_name": "public.rental.rental_id",
    "schema": "public",
    "table": "rental",
    "name": "rental_id",
    "comment": "租赁记录唯一标识ID",
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
    "id": "dvdrental.public.rental.rental_date",
    "database": "dvdrental",
    "full_name": "public.rental.rental_date",
    "schema": "public",
    "table": "rental",
    "name": "rental_date",
    "comment": "租赁发生时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.999,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.rental.inventory_id",
    "database": "dvdrental",
    "full_name": "public.rental.inventory_id",
    "schema": "public",
    "table": "rental",
    "name": "inventory_id",
    "comment": "影片库存记录ID",
    "data_type": "integer",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.rental.customer_id",
    "database": "dvdrental",
    "full_name": "public.rental.customer_id",
    "schema": "public",
    "table": "rental",
    "name": "customer_id",
    "comment": "租赁客户唯一标识ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.486,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.rental.return_date",
    "database": "dvdrental",
    "full_name": "public.rental.return_date",
    "schema": "public",
    "table": "rental",
    "name": "return_date",
    "comment": "影片归还时间戳（可为空）",
    "data_type": "timestamp without time zone",
    "semantic_role": "audit",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.997,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.rental.staff_id",
    "database": "dvdrental",
    "full_name": "public.rental.staff_id",
    "schema": "public",
    "table": "rental",
    "name": "staff_id",
    "comment": "处理租赁业务的员工ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.002,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.rental.last_update",
    "database": "dvdrental",
    "full_name": "public.rental.last_update",
    "schema": "public",
    "table": "rental",
    "name": "last_update",
    "comment": "记录最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
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
    "id": "dvdrental.public.staff.staff_id",
    "database": "dvdrental",
    "full_name": "public.staff.staff_id",
    "schema": "public",
    "table": "staff",
    "name": "staff_id",
    "comment": "员工唯一标识ID",
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
    "id": "dvdrental.public.staff.first_name",
    "database": "dvdrental",
    "full_name": "public.staff.first_name",
    "schema": "public",
    "table": "staff",
    "name": "first_name",
    "comment": "员工名字（名）",
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
    "id": "dvdrental.public.staff.last_name",
    "database": "dvdrental",
    "full_name": "public.staff.last_name",
    "schema": "public",
    "table": "staff",
    "name": "last_name",
    "comment": "员工姓氏（姓）",
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
    "id": "dvdrental.public.staff.address_id",
    "database": "dvdrental",
    "full_name": "public.staff.address_id",
    "schema": "public",
    "table": "staff",
    "name": "address_id",
    "comment": "员工地址信息ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.staff.email",
    "database": "dvdrental",
    "full_name": "public.staff.email",
    "schema": "public",
    "table": "staff",
    "name": "email",
    "comment": "员工工作邮箱地址",
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
    "id": "dvdrental.public.staff.store_id",
    "database": "dvdrental",
    "full_name": "public.staff.store_id",
    "schema": "public",
    "table": "staff",
    "name": "store_id",
    "comment": "所属门店ID",
    "data_type": "smallint",
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
    "id": "dvdrental.public.staff.active",
    "database": "dvdrental",
    "full_name": "public.staff.active",
    "schema": "public",
    "table": "staff",
    "name": "active",
    "comment": "员工启用状态（true-在职，false-离职）",
    "data_type": "boolean",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.5,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.staff.username",
    "database": "dvdrental",
    "full_name": "public.staff.username",
    "schema": "public",
    "table": "staff",
    "name": "username",
    "comment": "员工系统登录用户名",
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
    "id": "dvdrental.public.staff.password",
    "database": "dvdrental",
    "full_name": "public.staff.password",
    "schema": "public",
    "table": "staff",
    "name": "password",
    "comment": "员工密码（SHA1哈希值）",
    "data_type": "character varying",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.5,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.staff.last_update",
    "database": "dvdrental",
    "full_name": "public.staff.last_update",
    "schema": "public",
    "table": "staff",
    "name": "last_update",
    "comment": "记录最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.5,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.staff.picture",
    "database": "dvdrental",
    "full_name": "public.staff.picture",
    "schema": "public",
    "table": "staff",
    "name": "picture",
    "comment": "员工照片二进制数据",
    "data_type": "bytea",
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
    "id": "dvdrental.public.store.store_id",
    "database": "dvdrental",
    "full_name": "public.store.store_id",
    "schema": "public",
    "table": "store",
    "name": "store_id",
    "comment": "门店唯一标识ID",
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
    "id": "dvdrental.public.store.manager_staff_id",
    "database": "dvdrental",
    "full_name": "public.store.manager_staff_id",
    "schema": "public",
    "table": "store",
    "name": "manager_staff_id",
    "comment": "门店经理员工ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.store.address_id",
    "database": "dvdrental",
    "full_name": "public.store.address_id",
    "schema": "public",
    "table": "store",
    "name": "address_id",
    "comment": "门店地址信息ID",
    "data_type": "smallint",
    "semantic_role": "identifier",
    "is_pk": false,
    "is_uk": false,
    "is_fk": true,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 1.0,
    "null_rate": 0.0
  },
  {
    "id": "dvdrental.public.store.last_update",
    "database": "dvdrental",
    "full_name": "public.store.last_update",
    "schema": "public",
    "table": "store",
    "name": "last_update",
    "comment": "最后更新时间戳",
    "data_type": "timestamp without time zone",
    "semantic_role": "attribute",
    "is_pk": false,
    "is_uk": false,
    "is_fk": false,
    "is_time": false,
    "is_measure": false,
    "pk_position": 0,
    "uniqueness": 0.5,
    "null_rate": 0.0
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
    "table_full_name": "public.actor",
    "column_full_name": "public.actor.actor_id"
  },
  {
    "table_full_name": "public.actor",
    "column_full_name": "public.actor.first_name"
  },
  {
    "table_full_name": "public.actor",
    "column_full_name": "public.actor.last_name"
  },
  {
    "table_full_name": "public.actor",
    "column_full_name": "public.actor.last_update"
  },
  {
    "table_full_name": "public.address",
    "column_full_name": "public.address.address_id"
  },
  {
    "table_full_name": "public.address",
    "column_full_name": "public.address.address"
  },
  {
    "table_full_name": "public.address",
    "column_full_name": "public.address.address2"
  },
  {
    "table_full_name": "public.address",
    "column_full_name": "public.address.district"
  },
  {
    "table_full_name": "public.address",
    "column_full_name": "public.address.city_id"
  },
  {
    "table_full_name": "public.address",
    "column_full_name": "public.address.postal_code"
  },
  {
    "table_full_name": "public.address",
    "column_full_name": "public.address.phone"
  },
  {
    "table_full_name": "public.address",
    "column_full_name": "public.address.last_update"
  },
  {
    "table_full_name": "public.category",
    "column_full_name": "public.category.category_id"
  },
  {
    "table_full_name": "public.category",
    "column_full_name": "public.category.name"
  },
  {
    "table_full_name": "public.category",
    "column_full_name": "public.category.last_update"
  },
  {
    "table_full_name": "public.city",
    "column_full_name": "public.city.city_id"
  },
  {
    "table_full_name": "public.city",
    "column_full_name": "public.city.city"
  },
  {
    "table_full_name": "public.city",
    "column_full_name": "public.city.country_id"
  },
  {
    "table_full_name": "public.city",
    "column_full_name": "public.city.last_update"
  },
  {
    "table_full_name": "public.country",
    "column_full_name": "public.country.country_id"
  },
  {
    "table_full_name": "public.country",
    "column_full_name": "public.country.country"
  },
  {
    "table_full_name": "public.country",
    "column_full_name": "public.country.last_update"
  },
  {
    "table_full_name": "public.customer",
    "column_full_name": "public.customer.customer_id"
  },
  {
    "table_full_name": "public.customer",
    "column_full_name": "public.customer.store_id"
  },
  {
    "table_full_name": "public.customer",
    "column_full_name": "public.customer.first_name"
  },
  {
    "table_full_name": "public.customer",
    "column_full_name": "public.customer.last_name"
  },
  {
    "table_full_name": "public.customer",
    "column_full_name": "public.customer.email"
  },
  {
    "table_full_name": "public.customer",
    "column_full_name": "public.customer.address_id"
  },
  {
    "table_full_name": "public.customer",
    "column_full_name": "public.customer.activebool"
  },
  {
    "table_full_name": "public.customer",
    "column_full_name": "public.customer.create_date"
  },
  {
    "table_full_name": "public.customer",
    "column_full_name": "public.customer.last_update"
  },
  {
    "table_full_name": "public.customer",
    "column_full_name": "public.customer.active"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.film_id"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.title"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.description"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.release_year"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.language_id"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.rental_duration"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.rental_rate"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.length"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.replacement_cost"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.rating"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.last_update"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.special_features"
  },
  {
    "table_full_name": "public.film",
    "column_full_name": "public.film.fulltext"
  },
  {
    "table_full_name": "public.film_actor",
    "column_full_name": "public.film_actor.actor_id"
  },
  {
    "table_full_name": "public.film_actor",
    "column_full_name": "public.film_actor.film_id"
  },
  {
    "table_full_name": "public.film_actor",
    "column_full_name": "public.film_actor.last_update"
  },
  {
    "table_full_name": "public.film_category",
    "column_full_name": "public.film_category.film_id"
  },
  {
    "table_full_name": "public.film_category",
    "column_full_name": "public.film_category.category_id"
  },
  {
    "table_full_name": "public.film_category",
    "column_full_name": "public.film_category.last_update"
  },
  {
    "table_full_name": "public.inventory",
    "column_full_name": "public.inventory.inventory_id"
  },
  {
    "table_full_name": "public.inventory",
    "column_full_name": "public.inventory.film_id"
  },
  {
    "table_full_name": "public.inventory",
    "column_full_name": "public.inventory.store_id"
  },
  {
    "table_full_name": "public.inventory",
    "column_full_name": "public.inventory.last_update"
  },
  {
    "table_full_name": "public.language",
    "column_full_name": "public.language.language_id"
  },
  {
    "table_full_name": "public.language",
    "column_full_name": "public.language.name"
  },
  {
    "table_full_name": "public.language",
    "column_full_name": "public.language.last_update"
  },
  {
    "table_full_name": "public.payment",
    "column_full_name": "public.payment.payment_id"
  },
  {
    "table_full_name": "public.payment",
    "column_full_name": "public.payment.customer_id"
  },
  {
    "table_full_name": "public.payment",
    "column_full_name": "public.payment.staff_id"
  },
  {
    "table_full_name": "public.payment",
    "column_full_name": "public.payment.rental_id"
  },
  {
    "table_full_name": "public.payment",
    "column_full_name": "public.payment.amount"
  },
  {
    "table_full_name": "public.payment",
    "column_full_name": "public.payment.payment_date"
  },
  {
    "table_full_name": "public.rental",
    "column_full_name": "public.rental.rental_id"
  },
  {
    "table_full_name": "public.rental",
    "column_full_name": "public.rental.rental_date"
  },
  {
    "table_full_name": "public.rental",
    "column_full_name": "public.rental.inventory_id"
  },
  {
    "table_full_name": "public.rental",
    "column_full_name": "public.rental.customer_id"
  },
  {
    "table_full_name": "public.rental",
    "column_full_name": "public.rental.return_date"
  },
  {
    "table_full_name": "public.rental",
    "column_full_name": "public.rental.staff_id"
  },
  {
    "table_full_name": "public.rental",
    "column_full_name": "public.rental.last_update"
  },
  {
    "table_full_name": "public.staff",
    "column_full_name": "public.staff.staff_id"
  },
  {
    "table_full_name": "public.staff",
    "column_full_name": "public.staff.first_name"
  },
  {
    "table_full_name": "public.staff",
    "column_full_name": "public.staff.last_name"
  },
  {
    "table_full_name": "public.staff",
    "column_full_name": "public.staff.address_id"
  },
  {
    "table_full_name": "public.staff",
    "column_full_name": "public.staff.email"
  },
  {
    "table_full_name": "public.staff",
    "column_full_name": "public.staff.store_id"
  },
  {
    "table_full_name": "public.staff",
    "column_full_name": "public.staff.active"
  },
  {
    "table_full_name": "public.staff",
    "column_full_name": "public.staff.username"
  },
  {
    "table_full_name": "public.staff",
    "column_full_name": "public.staff.password"
  },
  {
    "table_full_name": "public.staff",
    "column_full_name": "public.staff.last_update"
  },
  {
    "table_full_name": "public.staff",
    "column_full_name": "public.staff.picture"
  },
  {
    "table_full_name": "public.store",
    "column_full_name": "public.store.store_id"
  },
  {
    "table_full_name": "public.store",
    "column_full_name": "public.store.manager_staff_id"
  },
  {
    "table_full_name": "public.store",
    "column_full_name": "public.store.address_id"
  },
  {
    "table_full_name": "public.store",
    "column_full_name": "public.store.last_update"
  }
] AS hc
MATCH (t:Table {full_name: hc.table_full_name})
MATCH (c:Column {full_name: hc.column_full_name})
MERGE (t)-[:HAS_COLUMN]->(c);

// =====================================================================
// 5. 建立 JOIN_ON 关系
// =====================================================================

UNWIND [
  {
    "source_table": "public.address",
    "target_table": "public.city",
    "cardinality": "1:1",
    "constraint_name": "fk_address_city",
    "join_type": "INNER JOIN",
    "on": "SRC.city_id = DST.city_id",
    "source_columns": [
      "city_id"
    ],
    "target_columns": [
      "city_id"
    ],
    "src_full_name": "public.address",
    "dst_full_name": "public.city"
  },
  {
    "source_table": "public.city",
    "target_table": "public.country",
    "cardinality": "N:1",
    "constraint_name": "fk_city",
    "join_type": "INNER JOIN",
    "on": "SRC.country_id = DST.country_id",
    "source_columns": [
      "country_id"
    ],
    "target_columns": [
      "country_id"
    ],
    "src_full_name": "public.city",
    "dst_full_name": "public.country"
  },
  {
    "source_table": "public.customer",
    "target_table": "public.address",
    "cardinality": "1:1",
    "constraint_name": "customer_address_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.address_id = DST.address_id",
    "source_columns": [
      "address_id"
    ],
    "target_columns": [
      "address_id"
    ],
    "src_full_name": "public.customer",
    "dst_full_name": "public.address"
  },
  {
    "source_table": "public.film",
    "target_table": "public.language",
    "cardinality": "N:1",
    "constraint_name": "film_language_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.language_id = DST.language_id",
    "source_columns": [
      "language_id"
    ],
    "target_columns": [
      "language_id"
    ],
    "src_full_name": "public.film",
    "dst_full_name": "public.language"
  },
  {
    "source_table": "public.film_actor",
    "target_table": "public.actor",
    "cardinality": "N:1",
    "constraint_name": "film_actor_actor_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.actor_id = DST.actor_id",
    "source_columns": [
      "actor_id"
    ],
    "target_columns": [
      "actor_id"
    ],
    "src_full_name": "public.film_actor",
    "dst_full_name": "public.actor"
  },
  {
    "source_table": "public.film_actor",
    "target_table": "public.film",
    "cardinality": "N:1",
    "constraint_name": "film_actor_film_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.film_id = DST.film_id",
    "source_columns": [
      "film_id"
    ],
    "target_columns": [
      "film_id"
    ],
    "src_full_name": "public.film_actor",
    "dst_full_name": "public.film"
  },
  {
    "source_table": "public.film_category",
    "target_table": "public.category",
    "cardinality": "N:1",
    "constraint_name": "film_category_category_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.category_id = DST.category_id",
    "source_columns": [
      "category_id"
    ],
    "target_columns": [
      "category_id"
    ],
    "src_full_name": "public.film_category",
    "dst_full_name": "public.category"
  },
  {
    "source_table": "public.film_category",
    "target_table": "public.film",
    "cardinality": "1:1",
    "constraint_name": "film_category_film_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.film_id = DST.film_id",
    "source_columns": [
      "film_id"
    ],
    "target_columns": [
      "film_id"
    ],
    "src_full_name": "public.film_category",
    "dst_full_name": "public.film"
  },
  {
    "source_table": "public.inventory",
    "target_table": "public.film",
    "cardinality": "N:1",
    "constraint_name": "inventory_film_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.film_id = DST.film_id",
    "source_columns": [
      "film_id"
    ],
    "target_columns": [
      "film_id"
    ],
    "src_full_name": "public.inventory",
    "dst_full_name": "public.film"
  },
  {
    "source_table": "public.payment",
    "target_table": "public.customer",
    "cardinality": "N:1",
    "constraint_name": "payment_customer_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.customer_id = DST.customer_id",
    "source_columns": [
      "customer_id"
    ],
    "target_columns": [
      "customer_id"
    ],
    "src_full_name": "public.payment",
    "dst_full_name": "public.customer"
  },
  {
    "source_table": "public.payment",
    "target_table": "public.rental",
    "cardinality": "1:1",
    "constraint_name": "payment_rental_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.rental_id = DST.rental_id",
    "source_columns": [
      "rental_id"
    ],
    "target_columns": [
      "rental_id"
    ],
    "src_full_name": "public.payment",
    "dst_full_name": "public.rental"
  },
  {
    "source_table": "public.payment",
    "target_table": "public.staff",
    "cardinality": "N:1",
    "constraint_name": "payment_staff_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.staff_id = DST.staff_id",
    "source_columns": [
      "staff_id"
    ],
    "target_columns": [
      "staff_id"
    ],
    "src_full_name": "public.payment",
    "dst_full_name": "public.staff"
  },
  {
    "source_table": "public.rental",
    "target_table": "public.customer",
    "cardinality": "N:1",
    "constraint_name": "rental_customer_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.customer_id = DST.customer_id",
    "source_columns": [
      "customer_id"
    ],
    "target_columns": [
      "customer_id"
    ],
    "src_full_name": "public.rental",
    "dst_full_name": "public.customer"
  },
  {
    "source_table": "public.rental",
    "target_table": "public.inventory",
    "cardinality": "1:1",
    "constraint_name": "rental_inventory_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.inventory_id = DST.inventory_id",
    "source_columns": [
      "inventory_id"
    ],
    "target_columns": [
      "inventory_id"
    ],
    "src_full_name": "public.rental",
    "dst_full_name": "public.inventory"
  },
  {
    "source_table": "public.rental",
    "target_table": "public.staff",
    "cardinality": "N:1",
    "constraint_name": "rental_staff_id_key",
    "join_type": "INNER JOIN",
    "on": "SRC.staff_id = DST.staff_id",
    "source_columns": [
      "staff_id"
    ],
    "target_columns": [
      "staff_id"
    ],
    "src_full_name": "public.rental",
    "dst_full_name": "public.staff"
  },
  {
    "source_table": "public.staff",
    "target_table": "public.address",
    "cardinality": "1:1",
    "constraint_name": "staff_address_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.address_id = DST.address_id",
    "source_columns": [
      "address_id"
    ],
    "target_columns": [
      "address_id"
    ],
    "src_full_name": "public.staff",
    "dst_full_name": "public.address"
  },
  {
    "source_table": "public.store",
    "target_table": "public.address",
    "cardinality": "1:1",
    "constraint_name": "store_address_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.address_id = DST.address_id",
    "source_columns": [
      "address_id"
    ],
    "target_columns": [
      "address_id"
    ],
    "src_full_name": "public.store",
    "dst_full_name": "public.address"
  },
  {
    "source_table": "public.store",
    "target_table": "public.staff",
    "cardinality": "1:1",
    "constraint_name": "store_manager_staff_id_fkey",
    "join_type": "INNER JOIN",
    "on": "SRC.manager_staff_id = DST.staff_id",
    "source_columns": [
      "manager_staff_id"
    ],
    "target_columns": [
      "staff_id"
    ],
    "src_full_name": "public.store",
    "dst_full_name": "public.staff"
  }
] AS j
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
