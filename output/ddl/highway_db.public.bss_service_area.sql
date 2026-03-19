-- ====================================
-- Database: highway_db
-- Table: public.bss_service_area
-- Comment: 服务区信息表，存储高速公路服务区的名称、编号、位置、类型、状态及所属公司等基础信息
-- Generated: 2026-03-20 01:21:12
-- ====================================

CREATE TABLE IF NOT EXISTS public.bss_service_area (
    id CHARACTER VARYING(32) NOT NULL,
    version INTEGER(32) NOT NULL,
    create_ts TIMESTAMP WITHOUT TIME ZONE,
    created_by CHARACTER VARYING(50),
    update_ts TIMESTAMP WITHOUT TIME ZONE,
    updated_by CHARACTER VARYING(50),
    delete_ts TIMESTAMP WITHOUT TIME ZONE,
    deleted_by CHARACTER VARYING(50),
    service_area_name CHARACTER VARYING(255),
    service_area_no CHARACTER VARYING(255),
    company_id CHARACTER VARYING(32),
    service_position CHARACTER VARYING(255),
    service_area_type CHARACTER VARYING(50),
    service_state CHARACTER VARYING(50),
    CONSTRAINT bss_service_area_pkey PRIMARY KEY (id)
);

-- Column Comments
COMMENT ON COLUMN public.bss_service_area.id IS '服务区域唯一标识ID';
COMMENT ON COLUMN public.bss_service_area.version IS '数据版本号，用于乐观锁控制';
COMMENT ON COLUMN public.bss_service_area.create_ts IS '记录创建时间戳';
COMMENT ON COLUMN public.bss_service_area.created_by IS '创建人用户名';
COMMENT ON COLUMN public.bss_service_area.update_ts IS '记录最后更新时间戳';
COMMENT ON COLUMN public.bss_service_area.updated_by IS '最后更新人用户名';
COMMENT ON COLUMN public.bss_service_area.delete_ts IS '逻辑删除时间戳（为空表示未删除）';
COMMENT ON COLUMN public.bss_service_area.deleted_by IS '逻辑删除操作人用户名';
COMMENT ON COLUMN public.bss_service_area.service_area_name IS '服务区名称';
COMMENT ON COLUMN public.bss_service_area.service_area_no IS '服务区编码';
COMMENT ON COLUMN public.bss_service_area.company_id IS '公司id';
COMMENT ON COLUMN public.bss_service_area.service_position IS '服务区经纬度';
COMMENT ON COLUMN public.bss_service_area.service_area_type IS '服务区类型';
COMMENT ON COLUMN public.bss_service_area.service_state IS '服务区状态';

-- Indexes
CREATE INDEX idx_bss_service_area_on_company ON public.bss_service_area(company_id);

-- Table Comment
COMMENT ON TABLE public.bss_service_area IS '服务区信息表，存储高速公路服务区的名称、编号、位置、类型、状态及所属公司等基础信息';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.bss_service_area",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "id": "0271d68ef93de9684b7ad8c7aae600b6",
        "version": "3",
        "create_ts": "2021-05-21 13:26:40.589000",
        "created_by": "admin",
        "update_ts": "2021-07-10 15:41:28.795000",
        "updated_by": "admin",
        "delete_ts": null,
        "deleted_by": null,
        "service_area_name": "白鹭湖停车区",
        "service_area_no": "H0814",
        "company_id": "b1629f07c8d9ac81494fbc1de61f1ea5",
        "service_position": "114.574721,26.825584",
        "service_area_type": "信息化服务区",
        "service_state": "开放"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "id": "08e01d7402abd1d6a4d9fdd5df855ef8",
        "version": "6",
        "create_ts": "2021-05-20 19:51:46.314000",
        "created_by": "admin",
        "update_ts": "2021-07-11 09:33:08.455000",
        "updated_by": "admin",
        "delete_ts": null,
        "deleted_by": null,
        "service_area_name": "南昌南服务区",
        "service_area_no": "H0105",
        "company_id": "ee9bf1180a2b45003f96e597a4b7f15a",
        "service_position": "115.910549,28.396355",
        "service_area_type": "信息化服务区",
        "service_state": "开放"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "id": "091662311d2c737029445442ff198c4c",
        "version": "4",
        "create_ts": "2021-05-20 19:51:46.351000",
        "created_by": "admin",
        "update_ts": "2021-07-10 15:41:28.797000",
        "updated_by": "admin",
        "delete_ts": null,
        "deleted_by": null,
        "service_area_name": "永丰服务区",
        "service_area_no": "H0806",
        "company_id": "b1629f07c8d9ac81494fbc1de61f1ea5",
        "service_position": "115.362656,27.227814",
        "service_area_type": "信息化服务区",
        "service_state": "开放"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "id": "09e1612ea5ae9077fcc13d1b3dceb73e",
        "version": "3",
        "create_ts": "2021-05-21 13:30:48.732000",
        "created_by": "admin",
        "update_ts": "2021-07-10 15:41:53.752000",
        "updated_by": "admin",
        "delete_ts": null,
        "deleted_by": null,
        "service_area_name": "铅山服务区",
        "service_area_no": "Q0103",
        "company_id": null,
        "service_position": "117.796075,28.175742",
        "service_area_type": "信息化服务区",
        "service_state": "开放"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "id": "0b70f74d0516fa5316dd5cb848ffaae9",
        "version": "4",
        "create_ts": "2021-05-20 19:51:46.353000",
        "created_by": "admin",
        "update_ts": "2021-07-10 15:41:28.797000",
        "updated_by": "admin",
        "delete_ts": null,
        "deleted_by": null,
        "service_area_name": "银湾桥服务区",
        "service_area_no": "H0811",
        "company_id": "b1629f07c8d9ac81494fbc1de61f1ea5",
        "service_position": "114.857064,27.240747",
        "service_area_type": "信息化服务区",
        "service_state": "开放"
      }
    }
  ]
}
*/