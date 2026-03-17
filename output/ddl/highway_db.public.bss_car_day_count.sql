-- ====================================
-- Database: highway_db
-- Table: public.bss_car_day_count
-- Comment: 按日统计各车型在服务区域的客户使用数量
-- Generated: 2026-03-17 23:00:01
-- ====================================

CREATE TABLE IF NOT EXISTS public.bss_car_day_count (
    id CHARACTER VARYING(32) NOT NULL,
    version INTEGER(32) NOT NULL,
    create_ts TIMESTAMP WITHOUT TIME ZONE,
    created_by CHARACTER VARYING(50),
    update_ts TIMESTAMP WITHOUT TIME ZONE,
    updated_by CHARACTER VARYING(50),
    delete_ts TIMESTAMP WITHOUT TIME ZONE,
    deleted_by CHARACTER VARYING(50),
    customer_count BIGINT(64),
    car_type CHARACTER VARYING(100),
    count_date DATE,
    service_area_id CHARACTER VARYING(32),
    CONSTRAINT bss_car_day_count_pkey PRIMARY KEY (id)
);

-- Column Comments
COMMENT ON COLUMN public.bss_car_day_count.id IS '汽车日统计记录唯一标识ID';
COMMENT ON COLUMN public.bss_car_day_count.version IS '数据版本号，用于乐观锁控制';
COMMENT ON COLUMN public.bss_car_day_count.create_ts IS '记录创建时间戳';
COMMENT ON COLUMN public.bss_car_day_count.created_by IS '创建人用户名或系统标识';
COMMENT ON COLUMN public.bss_car_day_count.update_ts IS '记录最后更新时间戳';
COMMENT ON COLUMN public.bss_car_day_count.updated_by IS '最后更新人用户名或系统标识';
COMMENT ON COLUMN public.bss_car_day_count.delete_ts IS '逻辑删除时间戳（为空表示未删除）';
COMMENT ON COLUMN public.bss_car_day_count.deleted_by IS '逻辑删除人用户名或系统标识';
COMMENT ON COLUMN public.bss_car_day_count.customer_count IS '车辆数量';
COMMENT ON COLUMN public.bss_car_day_count.car_type IS '车辆类别';
COMMENT ON COLUMN public.bss_car_day_count.count_date IS '统计日期';
COMMENT ON COLUMN public.bss_car_day_count.service_area_id IS '服务区id';

-- Indexes
CREATE INDEX idx_bss_car_day_count_on_service_area ON public.bss_car_day_count(service_area_id);

-- Table Comment
COMMENT ON TABLE public.bss_car_day_count IS '按日统计各车型在服务区域的客户使用数量';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.bss_car_day_count",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "id": "00022c1c99ff11ec86d4fa163ec0f8fc",
        "version": "1",
        "create_ts": "2022-03-02 16:01:43",
        "created_by": null,
        "update_ts": "2022-03-02 16:01:43",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "customer_count": "1114",
        "car_type": "其他",
        "count_date": "2022-03-02",
        "service_area_id": null
      }
    },
    {
      "label": "Record 2",
      "data": {
        "id": "00022caa99ff11ec86d4fa163ec0f8fc",
        "version": "1",
        "create_ts": "2022-03-02 16:01:43",
        "created_by": null,
        "update_ts": "2022-03-02 16:01:43",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "customer_count": "295",
        "car_type": "其他",
        "count_date": "2022-03-02",
        "service_area_id": null
      }
    },
    {
      "label": "Record 3",
      "data": {
        "id": "00022ded99ff11ec86d4fa163ec0f8fc",
        "version": "1",
        "create_ts": "2022-03-02 16:01:43",
        "created_by": null,
        "update_ts": "2022-03-02 16:01:43",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "customer_count": "550",
        "car_type": "其他",
        "count_date": "2022-03-02",
        "service_area_id": null
      }
    },
    {
      "label": "Record 4",
      "data": {
        "id": "00022e8499ff11ec86d4fa163ec0f8fc",
        "version": "1",
        "create_ts": "2022-03-02 16:01:43",
        "created_by": null,
        "update_ts": "2022-03-02 16:01:43",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "customer_count": "1050",
        "car_type": "其他",
        "count_date": "2022-03-02",
        "service_area_id": null
      }
    },
    {
      "label": "Record 5",
      "data": {
        "id": "0002331999ff11ec86d4fa163ec0f8fc",
        "version": "1",
        "create_ts": "2022-03-02 16:01:43",
        "created_by": null,
        "update_ts": "2022-03-02 16:01:43",
        "updated_by": null,
        "delete_ts": null,
        "deleted_by": null,
        "customer_count": "993",
        "car_type": "其他",
        "count_date": "2022-03-02",
        "service_area_id": null
      }
    }
  ]
}
*/