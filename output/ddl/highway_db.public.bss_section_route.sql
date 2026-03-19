-- ====================================
-- Database: highway_db
-- Table: public.bss_section_route
-- Comment: 路段与路线关联表，存储路段名称、所属路线及唯一编码信息
-- Generated: 2026-03-19 11:51:54
-- ====================================

CREATE TABLE IF NOT EXISTS public.bss_section_route (
    id CHARACTER VARYING(32) NOT NULL,
    version INTEGER(32) NOT NULL,
    create_ts TIMESTAMP WITHOUT TIME ZONE,
    created_by CHARACTER VARYING(50),
    update_ts TIMESTAMP WITHOUT TIME ZONE,
    updated_by CHARACTER VARYING(50),
    delete_ts TIMESTAMP WITHOUT TIME ZONE,
    deleted_by CHARACTER VARYING(50),
    section_name CHARACTER VARYING(255),
    route_name CHARACTER VARYING(255),
    code CHARACTER VARYING(255),
    CONSTRAINT bss_section_route_pkey PRIMARY KEY (id)
);

-- Column Comments
COMMENT ON COLUMN public.bss_section_route.id IS '路段路由记录唯一标识ID';
COMMENT ON COLUMN public.bss_section_route.version IS '数据版本号，用于乐观锁控制';
COMMENT ON COLUMN public.bss_section_route.create_ts IS '记录创建时间戳';
COMMENT ON COLUMN public.bss_section_route.created_by IS '创建人用户名';
COMMENT ON COLUMN public.bss_section_route.update_ts IS '记录最后更新时间戳';
COMMENT ON COLUMN public.bss_section_route.updated_by IS '最后更新人用户名';
COMMENT ON COLUMN public.bss_section_route.delete_ts IS '逻辑删除时间戳（为空表示未删除）';
COMMENT ON COLUMN public.bss_section_route.deleted_by IS '逻辑删除人用户名';
COMMENT ON COLUMN public.bss_section_route.section_name IS '路段名称';
COMMENT ON COLUMN public.bss_section_route.route_name IS '路线名称';
COMMENT ON COLUMN public.bss_section_route.code IS '编号';

-- Table Comment
COMMENT ON TABLE public.bss_section_route IS '路段与路线关联表，存储路段名称、所属路线及唯一编码信息';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.bss_section_route",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "id": "04ri3j67a806uw2c6o6dwdtz4knexczh",
        "version": "1",
        "create_ts": "2021-10-29 19:43:50",
        "created_by": "admin",
        "update_ts": null,
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "section_name": "昌栗",
        "route_name": "昌栗",
        "code": "SR0001"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "id": "0g5mnefxxtukql2cq6acul7phgskowy7",
        "version": "1",
        "create_ts": "2021-10-29 19:43:50",
        "created_by": "admin",
        "update_ts": null,
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "section_name": "昌宁",
        "route_name": "昌韶",
        "code": "SR0002"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "id": "1eff406e9b9211ec8ee6fa163eaf653f",
        "version": "0",
        "create_ts": "2022-03-04 16:07:16",
        "created_by": null,
        "update_ts": null,
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "section_name": "昌九",
        "route_name": "/",
        "code": "SR0147"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "id": "2sop3gahzo0wz6q586y241d98w6pkxd5",
        "version": "1",
        "create_ts": "2021-10-29 19:43:50",
        "created_by": "admin",
        "update_ts": null,
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "section_name": "泰井",
        "route_name": "泰井",
        "code": "SR0003"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "id": "30824fa99b9211ec8ee6fa163eaf653f",
        "version": "0",
        "create_ts": "2022-03-04 16:07:58",
        "created_by": null,
        "update_ts": null,
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "section_name": "杭瑞",
        "route_name": "/",
        "code": "SR0148"
      }
    }
  ]
}
*/