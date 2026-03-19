-- ====================================
-- Database: highway_db
-- Table: public.bss_company
-- Comment: 公司信息表，存储企业分公司名称、编号及基础审计信息
-- Generated: 2026-03-20 01:21:08
-- ====================================

CREATE TABLE IF NOT EXISTS public.bss_company (
    id CHARACTER VARYING(32) NOT NULL,
    version INTEGER(32) NOT NULL,
    create_ts TIMESTAMP WITHOUT TIME ZONE,
    created_by CHARACTER VARYING(50),
    update_ts TIMESTAMP WITHOUT TIME ZONE,
    updated_by CHARACTER VARYING(50),
    delete_ts TIMESTAMP WITHOUT TIME ZONE,
    deleted_by CHARACTER VARYING(50),
    company_name CHARACTER VARYING(255),
    company_no CHARACTER VARYING(255),
    CONSTRAINT bss_company_pkey PRIMARY KEY (id)
);

-- Column Comments
COMMENT ON COLUMN public.bss_company.id IS '公司唯一标识ID（UUID格式）';
COMMENT ON COLUMN public.bss_company.version IS '数据版本号，用于乐观锁控制';
COMMENT ON COLUMN public.bss_company.create_ts IS '记录创建时间戳';
COMMENT ON COLUMN public.bss_company.created_by IS '创建人用户名';
COMMENT ON COLUMN public.bss_company.update_ts IS '记录最后更新时间戳';
COMMENT ON COLUMN public.bss_company.updated_by IS '最后更新人用户名';
COMMENT ON COLUMN public.bss_company.delete_ts IS '逻辑删除时间戳（NULL表示未删除）';
COMMENT ON COLUMN public.bss_company.deleted_by IS '逻辑删除操作人用户名';
COMMENT ON COLUMN public.bss_company.company_name IS '公司名称';
COMMENT ON COLUMN public.bss_company.company_no IS '公司编码';

-- Table Comment
COMMENT ON TABLE public.bss_company IS '公司信息表，存储企业分公司名称、编号及基础审计信息';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.bss_company",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "id": "30675d85ba5044c31acfa243b9d16334",
        "version": "1",
        "create_ts": "2021-05-20 09:51:58.718000",
        "created_by": "admin",
        "update_ts": "2021-05-20 09:51:58.718000",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "company_name": "上饶分公司",
        "company_no": "H03"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "id": "47ed0bb37f5a85f3d9245e4854959b81",
        "version": "1",
        "create_ts": "2021-05-20 09:42:03.341000",
        "created_by": "admin",
        "update_ts": "2021-05-20 09:42:03.341000",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "company_name": "宜春分公司",
        "company_no": "H02"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "id": "78efbf20d592d3ca938fd32303bb5fd8",
        "version": "1",
        "create_ts": "2021-05-20 09:53:29.261000",
        "created_by": "admin",
        "update_ts": "2021-05-20 09:53:29.261000",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "company_name": "景德镇分公司",
        "company_no": "H07"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "id": "b1629f07c8d9ac81494fbc1de61f1ea5",
        "version": "1",
        "create_ts": "2021-05-20 09:53:44.926000",
        "created_by": "admin",
        "update_ts": "2021-05-20 09:53:44.926000",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "company_name": "吉安分公司",
        "company_no": "H08"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "id": "ce5e6f553513dad393694e1fa663aaf4",
        "version": "2",
        "create_ts": "2021-05-20 09:43:04.960000",
        "created_by": "admin",
        "update_ts": "2021-05-20 09:52:26.461000",
        "updated_by": "admin",
        "delete_ts": null,
        "deleted_by": null,
        "company_name": "赣州分公司",
        "company_no": "H04"
      }
    }
  ]
}
*/