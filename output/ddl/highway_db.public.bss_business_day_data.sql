-- ====================================
-- Database: highway_db
-- Table: public.bss_business_day_data
-- Comment: 服务区日营业数据表，记录各服务区按支付渠道（微信、支付宝等）划分的订单量与收款金额
-- Generated: 2026-03-19 11:51:53
-- ====================================

CREATE TABLE IF NOT EXISTS public.bss_business_day_data (
    id CHARACTER VARYING(32) NOT NULL,
    version INTEGER(32) NOT NULL,
    create_ts TIMESTAMP WITHOUT TIME ZONE,
    created_by CHARACTER VARYING(50),
    update_ts TIMESTAMP WITHOUT TIME ZONE,
    updated_by CHARACTER VARYING(50),
    delete_ts TIMESTAMP WITHOUT TIME ZONE,
    deleted_by CHARACTER VARYING(50),
    oper_date DATE,
    service_no CHARACTER VARYING(255),
    service_name CHARACTER VARYING(255),
    branch_no CHARACTER VARYING(255),
    branch_name CHARACTER VARYING(255),
    wx NUMERIC(19,4),
    wx_order INTEGER(32),
    zfb NUMERIC(19,4),
    zf_order INTEGER(32),
    rmb NUMERIC(19,4),
    rmb_order INTEGER(32),
    xs NUMERIC(19,4),
    xs_order INTEGER(32),
    jd NUMERIC(19,4),
    jd_order INTEGER(32),
    order_sum INTEGER(32),
    pay_sum NUMERIC(19,4),
    source_type INTEGER(32),
    CONSTRAINT bss_business_day_data_pkey PRIMARY KEY (id)
);

-- Column Comments
COMMENT ON COLUMN public.bss_business_day_data.id IS '业务日数据记录唯一标识ID';
COMMENT ON COLUMN public.bss_business_day_data.version IS '数据版本号，用于乐观锁控制';
COMMENT ON COLUMN public.bss_business_day_data.create_ts IS '记录创建时间戳';
COMMENT ON COLUMN public.bss_business_day_data.created_by IS '创建人用户名';
COMMENT ON COLUMN public.bss_business_day_data.update_ts IS '记录最后更新时间戳';
COMMENT ON COLUMN public.bss_business_day_data.updated_by IS '最后更新人用户名';
COMMENT ON COLUMN public.bss_business_day_data.delete_ts IS '逻辑删除时间戳（NULL表示未删除）';
COMMENT ON COLUMN public.bss_business_day_data.deleted_by IS '逻辑删除人用户名';
COMMENT ON COLUMN public.bss_business_day_data.oper_date IS '统计日期';
COMMENT ON COLUMN public.bss_business_day_data.service_no IS '服务区编码';
COMMENT ON COLUMN public.bss_business_day_data.service_name IS '服务区名称';
COMMENT ON COLUMN public.bss_business_day_data.branch_no IS '档口编码';
COMMENT ON COLUMN public.bss_business_day_data.branch_name IS '档口名称';
COMMENT ON COLUMN public.bss_business_day_data.wx IS '微信支付金额（单位：元）';
COMMENT ON COLUMN public.bss_business_day_data.wx_order IS '微信订单数量';
COMMENT ON COLUMN public.bss_business_day_data.zfb IS '支付宝支付金额（单位：元）';
COMMENT ON COLUMN public.bss_business_day_data.zf_order IS '支付宝订单数量';
COMMENT ON COLUMN public.bss_business_day_data.rmb IS '现金支付金额（单位：元）';
COMMENT ON COLUMN public.bss_business_day_data.rmb_order IS '现金支付订单数量';
COMMENT ON COLUMN public.bss_business_day_data.xs IS '刷卡支付金额（单位：元）';
COMMENT ON COLUMN public.bss_business_day_data.xs_order IS '行吧支付数量';
COMMENT ON COLUMN public.bss_business_day_data.jd IS '京东支付金额（单位：元）';
COMMENT ON COLUMN public.bss_business_day_data.jd_order IS '金豆支付数量';
COMMENT ON COLUMN public.bss_business_day_data.order_sum IS '订单总数';
COMMENT ON COLUMN public.bss_business_day_data.pay_sum IS '当日总支付金额（单位：元，为各渠道之和）';
COMMENT ON COLUMN public.bss_business_day_data.source_type IS '数据来源类别';

-- Indexes
CREATE INDEX idx_branch_no ON public.bss_business_day_data(branch_no);
CREATE INDEX idx_oper_date ON public.bss_business_day_data(oper_date);

-- Table Comment
COMMENT ON TABLE public.bss_business_day_data IS '服务区日营业数据表，记录各服务区按支付渠道（微信、支付宝等）划分的订单量与收款金额';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.bss_business_day_data",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "id": "00827DFF993D415488EA1F07CAE6C440",
        "version": "1",
        "create_ts": "2023-04-02 08:31:51",
        "created_by": null,
        "update_ts": "2023-04-02 08:31:51",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "oper_date": "2023-04-01",
        "service_no": "1028",
        "service_name": "宜春服务区",
        "branch_no": "1",
        "branch_name": "宜春南区",
        "wx": "4790.0",
        "wx_order": "253.0",
        "zfb": "229.0",
        "zf_order": "15.0",
        "rmb": "1058.5",
        "rmb_order": "56.0",
        "xs": "0.0",
        "xs_order": "0.0",
        "jd": "0.0",
        "jd_order": "0.0",
        "order_sum": "324.0",
        "pay_sum": "6077.5",
        "source_type": "1"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "id": "00e799048b8cbb8ee758eac9c8b4b820",
        "version": "1",
        "create_ts": "2023-04-02 02:30:08",
        "created_by": "xingba",
        "update_ts": "2023-04-02 02:30:08",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "oper_date": "2023-04-01",
        "service_no": "H0501",
        "service_name": "庐山服务区",
        "branch_no": "H05016",
        "branch_name": "庐山鲜徕客东区",
        "wx": "2523.0",
        "wx_order": "133.0",
        "zfb": "0.0",
        "zf_order": "0.0",
        "rmb": "124.0",
        "rmb_order": "12.0",
        "xs": "40.0",
        "xs_order": "1.0",
        "jd": "0.0",
        "jd_order": "0.0",
        "order_sum": "146.0",
        "pay_sum": "2687.0",
        "source_type": "0"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "id": "019a5915c2f624800be71a2dd3e172e2",
        "version": "1",
        "create_ts": "2023-04-02 02:30:09",
        "created_by": "xingba",
        "update_ts": "2023-04-02 02:30:09",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "oper_date": "2023-04-01",
        "service_no": "H0804",
        "service_name": "永丰南服务区(新)",
        "branch_no": "H0804B",
        "branch_name": "永丰南餐饮西区(新)",
        "wx": "2820.0",
        "wx_order": "40.0",
        "zfb": "0.0",
        "zf_order": "0.0",
        "rmb": "245.0",
        "rmb_order": "4.0",
        "xs": "0.0",
        "xs_order": "0.0",
        "jd": "0.0",
        "jd_order": "0.0",
        "order_sum": "44.0",
        "pay_sum": "3065.0",
        "source_type": "0"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "id": "019DC1B2C42E4AEFA5C834021A3B2E51",
        "version": "1",
        "create_ts": "2023-04-02 08:31:51",
        "created_by": null,
        "update_ts": "2023-04-02 08:31:51",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "oper_date": "2023-04-01",
        "service_no": "1027",
        "service_name": "上高服务区",
        "branch_no": "1",
        "branch_name": "上高东区",
        "wx": "4135.0",
        "wx_order": "181.0",
        "zfb": "216.0",
        "zf_order": "14.0",
        "rmb": "405.5",
        "rmb_order": "18.0",
        "xs": "0.0",
        "xs_order": "0.0",
        "jd": "0.0",
        "jd_order": "0.0",
        "order_sum": "213.0",
        "pay_sum": "4756.5",
        "source_type": "1"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "id": "01d77aad56535689ebbb33bd1c35b0b5",
        "version": "1",
        "create_ts": "2023-04-02 02:30:07",
        "created_by": "xingba",
        "update_ts": "2023-04-02 02:30:07",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "oper_date": "2023-04-01",
        "service_no": "H0301",
        "service_name": "上饶服务区",
        "branch_no": "H0301C",
        "branch_name": "上饶如意菜饭北区",
        "wx": "2880.0",
        "wx_order": "139.0",
        "zfb": "75.0",
        "zf_order": "4.0",
        "rmb": "180.0",
        "rmb_order": "12.0",
        "xs": "0.0",
        "xs_order": "0.0",
        "jd": "0.0",
        "jd_order": "0.0",
        "order_sum": "155.0",
        "pay_sum": "3135.0",
        "source_type": "0"
      }
    }
  ]
}
*/