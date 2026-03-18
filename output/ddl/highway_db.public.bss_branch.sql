-- ====================================
-- Database: highway_db
-- Table: public.bss_branch
-- Comment: 高速公路服务区餐饮及小吃分支网点信息表
-- Generated: 2026-03-18 06:59:16
-- ====================================

CREATE TABLE IF NOT EXISTS public.bss_branch (
    id CHARACTER VARYING(32) NOT NULL,
    version INTEGER(32) NOT NULL,
    create_ts TIMESTAMP WITHOUT TIME ZONE,
    created_by CHARACTER VARYING(50),
    update_ts TIMESTAMP WITHOUT TIME ZONE,
    updated_by CHARACTER VARYING(50),
    delete_ts TIMESTAMP WITHOUT TIME ZONE,
    deleted_by CHARACTER VARYING(50),
    branch_name CHARACTER VARYING(255),
    branch_no CHARACTER VARYING(255),
    service_area_id CHARACTER VARYING(32),
    company_id CHARACTER VARYING(32),
    classify CHARACTER VARYING(256),
    product_brand CHARACTER VARYING(256),
    category CHARACTER VARYING(256),
    section_route_id CHARACTER VARYING(32),
    direction CHARACTER VARYING(256),
    is_manual_entry INTEGER(32) DEFAULT 0,
    co_company CHARACTER VARYING(256)
);

-- Column Comments
COMMENT ON COLUMN public.bss_branch.id IS '分支机构唯一标识ID';
COMMENT ON COLUMN public.bss_branch.version IS '数据版本号，用于乐观锁控制';
COMMENT ON COLUMN public.bss_branch.create_ts IS '记录创建时间戳';
COMMENT ON COLUMN public.bss_branch.created_by IS '创建人用户名';
COMMENT ON COLUMN public.bss_branch.update_ts IS '记录最后更新时间戳';
COMMENT ON COLUMN public.bss_branch.updated_by IS '最后更新人用户名';
COMMENT ON COLUMN public.bss_branch.delete_ts IS '逻辑删除时间戳（NULL表示未删除）';
COMMENT ON COLUMN public.bss_branch.deleted_by IS '逻辑删除操作人用户名';
COMMENT ON COLUMN public.bss_branch.branch_name IS '档口名称';
COMMENT ON COLUMN public.bss_branch.branch_no IS '档口编码';
COMMENT ON COLUMN public.bss_branch.service_area_id IS '服务区id';
COMMENT ON COLUMN public.bss_branch.company_id IS '公司id';
COMMENT ON COLUMN public.bss_branch.classify IS '品类';
COMMENT ON COLUMN public.bss_branch.product_brand IS '品牌';
COMMENT ON COLUMN public.bss_branch.category IS '类别';
COMMENT ON COLUMN public.bss_branch.section_route_id IS '线路id';
COMMENT ON COLUMN public.bss_branch.direction IS '服务区方向';
COMMENT ON COLUMN public.bss_branch.is_manual_entry IS '是否手工录入数据：0：系统自动  1：手工录入';
COMMENT ON COLUMN public.bss_branch.co_company IS '合作单位';

-- Indexes
CREATE INDEX idx_area_id ON public.bss_branch(service_area_id);
CREATE INDEX idx_brach_no ON public.bss_branch(branch_no);
CREATE INDEX idx_company_id ON public.bss_branch(company_id);

-- Table Comment
COMMENT ON TABLE public.bss_branch IS '高速公路服务区餐饮及小吃分支网点信息表';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.bss_branch",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "id": "00904903cae681aab7a494c3e88e5acd",
        "version": "1",
        "create_ts": "2021-10-15 09:46:45.010000",
        "created_by": "admin",
        "update_ts": "2021-10-15 09:46:45.010000",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "branch_name": "于都驿美餐饮南区",
        "branch_no": "003585",
        "service_area_id": "c7e2f26df373e9cb75bd24ddba57f27f",
        "company_id": "ce5e6f553513dad393694e1fa663aaf4",
        "classify": "餐饮",
        "product_brand": "驿美餐饮",
        "category": "餐饮",
        "section_route_id": "lvkcuu94d4487c42z7qltsvxcyz0iqu5",
        "direction": "南区",
        "is_manual_entry": "0",
        "co_company": "江西驿美餐饮管理有限责任公司"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "id": "01a3df15b454fa7b5f176125af0c57d8",
        "version": "1",
        "create_ts": "2021-05-20 19:53:58.977000",
        "created_by": "admin",
        "update_ts": "2021-11-07 20:26:10",
        "updated_by": "updated by importSQL",
        "delete_ts": null,
        "deleted_by": null,
        "branch_name": "南城餐饮西区",
        "branch_no": "H0601B",
        "service_area_id": "8eb8ec693642354a62d640c7f1c2365c",
        "company_id": "e6c060f05306a03f978e2b952a551744",
        "classify": "餐饮",
        "product_brand": "小圆满（自助餐）",
        "category": "中餐",
        "section_route_id": "wnejyryq6zvtdy6axgvz6jutv8n6vc3r",
        "direction": "西区",
        "is_manual_entry": "0",
        "co_company": "嘉兴市同辉高速公路服务区经营管理有限公司"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "id": "01bc4c3d00750860a898a295a77b388e",
        "version": "1",
        "create_ts": "2021-05-20 19:53:58.938000",
        "created_by": "admin",
        "update_ts": "2021-11-07 20:26:14",
        "updated_by": "updated by importSQL",
        "delete_ts": null,
        "deleted_by": null,
        "branch_name": "龙虎山小吃北区",
        "branch_no": "H03106",
        "service_area_id": "7a060d137a63111d652183007d9f0eaf",
        "company_id": "30675d85ba5044c31acfa243b9d16334",
        "classify": "小吃",
        "product_brand": "百色百味",
        "category": "小吃",
        "section_route_id": "tvyjygi5q745pxb697eiaj2sfie6m5be",
        "direction": "北区",
        "is_manual_entry": "0",
        "co_company": "嘉兴力天高速公路服务区经营管理有限公司"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "id": "01c5d0986490a649db8e906aa1e1748c",
        "version": "1",
        "create_ts": "2021-05-20 19:53:58.902000",
        "created_by": "admin",
        "update_ts": "2021-11-07 20:26:10",
        "updated_by": "updated by importSQL",
        "delete_ts": null,
        "deleted_by": null,
        "branch_name": "金溪水果店西区",
        "branch_no": "H0605E",
        "service_area_id": "935aec946d0b107f5fb825ce8923d559",
        "company_id": "e6c060f05306a03f978e2b952a551744",
        "classify": "其他",
        "product_brand": "半斗米水果",
        "category": "水果",
        "section_route_id": "wnejyryq6zvtdy6axgvz6jutv8n6vc3r",
        "direction": "西区",
        "is_manual_entry": "0",
        "co_company": "杭州半斗米水果连锁有限公司"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "id": "02005b4d89cd97e6e312c75d4d50ed37",
        "version": "1",
        "create_ts": "2021-05-20 19:53:58.900000",
        "created_by": "admin",
        "update_ts": "2021-11-07 20:26:11",
        "updated_by": "updated by importSQL",
        "delete_ts": null,
        "deleted_by": null,
        "branch_name": "吉安西小吃南区",
        "branch_no": "H08123",
        "service_area_id": "fb498760acfc18315032c2a442e69de4",
        "company_id": "b1629f07c8d9ac81494fbc1de61f1ea5",
        "classify": "小吃",
        "product_brand": "润仟祥",
        "category": "小吃",
        "section_route_id": "e9um53e7q6oklqftlekyf8yh1dxqwen4",
        "direction": "南区",
        "is_manual_entry": "0",
        "co_company": "上高县通达服务管理有限公司"
      }
    }
  ]
}
*/