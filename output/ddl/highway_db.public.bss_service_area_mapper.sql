-- ====================================
-- Database: highway_db
-- Table: public.bss_service_area_mapper
-- Comment: 服务区信息映射表，关联不同来源系统中的服务区名称、编号与唯一标识
-- Generated: 2026-03-17 23:00:05
-- ====================================

CREATE TABLE IF NOT EXISTS public.bss_service_area_mapper (
    id CHARACTER VARYING(32) NOT NULL,
    version INTEGER(32) NOT NULL,
    create_ts TIMESTAMP WITHOUT TIME ZONE,
    created_by CHARACTER VARYING(50),
    update_ts TIMESTAMP WITHOUT TIME ZONE,
    updated_by CHARACTER VARYING(50),
    delete_ts TIMESTAMP WITHOUT TIME ZONE,
    deleted_by CHARACTER VARYING(50),
    service_name CHARACTER VARYING(255),
    service_no CHARACTER VARYING(255),
    service_area_id CHARACTER VARYING(32),
    source_system_type CHARACTER VARYING(50),
    source_type INTEGER(32),
    CONSTRAINT bss_service_area_mapper_pkey PRIMARY KEY (id)
);

-- Column Comments
COMMENT ON COLUMN public.bss_service_area_mapper.id IS '服务区域映射记录唯一标识ID';
COMMENT ON COLUMN public.bss_service_area_mapper.version IS '数据版本号，用于乐观锁控制';
COMMENT ON COLUMN public.bss_service_area_mapper.create_ts IS '记录创建时间戳';
COMMENT ON COLUMN public.bss_service_area_mapper.created_by IS '创建人用户名';
COMMENT ON COLUMN public.bss_service_area_mapper.update_ts IS '记录最后更新时间戳';
COMMENT ON COLUMN public.bss_service_area_mapper.updated_by IS '最后更新人用户名';
COMMENT ON COLUMN public.bss_service_area_mapper.delete_ts IS '逻辑删除时间戳（NULL表示未删除）';
COMMENT ON COLUMN public.bss_service_area_mapper.deleted_by IS '逻辑删除人用户名';
COMMENT ON COLUMN public.bss_service_area_mapper.service_name IS '服务区名称';
COMMENT ON COLUMN public.bss_service_area_mapper.service_no IS '服务区编码';
COMMENT ON COLUMN public.bss_service_area_mapper.service_area_id IS '服务区id';
COMMENT ON COLUMN public.bss_service_area_mapper.source_system_type IS '数据来源类别名称';
COMMENT ON COLUMN public.bss_service_area_mapper.source_type IS '数据来源类别id';

-- Indexes
CREATE INDEX idx_bss_service_area_mapper_on_service_area ON public.bss_service_area_mapper(service_area_id);

-- Table Comment
COMMENT ON TABLE public.bss_service_area_mapper IS '服务区信息映射表，关联不同来源系统中的服务区名称、编号与唯一标识';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.bss_service_area_mapper",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "id": "00e1e893909211ed8ee6fa163eaf653f",
        "version": "1",
        "create_ts": "2023-01-10 10:54:03",
        "created_by": null,
        "update_ts": "2023-01-10 10:54:07",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "service_name": "信丰西服务区",
        "service_no": "1067",
        "service_area_id": "97cd6cd516a551409a4d453a58f9e170",
        "source_system_type": "驿美",
        "source_type": "3"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "id": "013867f5962211ed8ee6fa163eaf653f",
        "version": "1",
        "create_ts": "2023-01-17 12:47:29",
        "created_by": null,
        "update_ts": "2023-01-17 12:47:32",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "service_name": "南康北服务区",
        "service_no": "1062",
        "service_area_id": "fdbdd042962011ed8ee6fa163eaf653f",
        "source_system_type": "驿购",
        "source_type": "1"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "id": "0546e5da606d11ec8ee6fa163eaf653f",
        "version": "1",
        "create_ts": "2021-12-19 09:43:09",
        "created_by": "admin",
        "update_ts": "2021-12-19 09:43:09",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "service_name": "永丰服务区",
        "service_no": "1008",
        "service_area_id": "091662311d2c737029445442ff198c4c",
        "source_system_type": "驿购",
        "source_type": "1"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "id": "0546e9a0606d11ec8ee6fa163eaf653f",
        "version": "1",
        "create_ts": "2021-12-19 09:43:09",
        "created_by": "admin",
        "update_ts": "2021-12-19 09:43:09",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "service_name": "银湾桥服务区",
        "service_no": "1015",
        "service_area_id": "0b70f74d0516fa5316dd5cb848ffaae9",
        "source_system_type": "驿购",
        "source_type": "1"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "id": "0546ea30606d11ec8ee6fa163eaf653f",
        "version": "1",
        "create_ts": "2021-12-19 09:43:09",
        "created_by": "admin",
        "update_ts": "2021-12-19 09:43:09",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "service_name": "七里岗服务区",
        "service_no": "1004",
        "service_area_id": "17461166e7fa3ecda03534a5795ce985",
        "source_system_type": "驿购",
        "source_type": "1"
      }
    }
  ]
}
*/