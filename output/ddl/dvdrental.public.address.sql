-- ====================================
-- Database: dvdrental
-- Table: public.address
-- Comment: 地址信息表，存储客户或机构的详细联系地址及区域归属
-- Generated: 2026-01-06 10:55:03
-- ====================================

CREATE TABLE IF NOT EXISTS public.address (
    address_id INTEGER(32) NOT NULL DEFAULT nextval('address_address_id_seq'::regclass),
    address CHARACTER VARYING(50) NOT NULL,
    address2 CHARACTER VARYING(50),
    district CHARACTER VARYING(20) NOT NULL,
    city_id SMALLINT(16) NOT NULL,
    postal_code CHARACTER VARYING(10),
    phone CHARACTER VARYING(20) NOT NULL,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT address_pkey PRIMARY KEY (address_id),
    CONSTRAINT fk_address_city FOREIGN KEY (city_id) REFERENCES public.city (city_id)
);

-- Column Comments
COMMENT ON COLUMN public.address.address_id IS '地址唯一标识ID';
COMMENT ON COLUMN public.address.address IS '详细地址信息';
COMMENT ON COLUMN public.address.address2 IS '补充地址信息';
COMMENT ON COLUMN public.address.district IS '所属行政区或地区';
COMMENT ON COLUMN public.address.city_id IS '城市唯一标识ID';
COMMENT ON COLUMN public.address.postal_code IS '邮政编码';
COMMENT ON COLUMN public.address.phone IS '联系电话';
COMMENT ON COLUMN public.address.last_update IS '最后更新时间';

-- Indexes
CREATE INDEX idx_fk_city_id ON public.address(city_id);

-- Table Comment
COMMENT ON TABLE public.address IS '地址信息表，存储客户或机构的详细联系地址及区域归属';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.address",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "address_id": "1",
        "address": "47 MySakila Drive",
        "address2": null,
        "district": "Alberta",
        "city_id": "300",
        "postal_code": "",
        "phone": "",
        "last_update": "2006-02-15 09:45:30"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "address_id": "2",
        "address": "28 MySQL Boulevard",
        "address2": null,
        "district": "QLD",
        "city_id": "576",
        "postal_code": "",
        "phone": "",
        "last_update": "2006-02-15 09:45:30"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "address_id": "3",
        "address": "23 Workhaven Lane",
        "address2": null,
        "district": "Alberta",
        "city_id": "300",
        "postal_code": "",
        "phone": "14033335568",
        "last_update": "2006-02-15 09:45:30"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "address_id": "4",
        "address": "1411 Lillydale Drive",
        "address2": null,
        "district": "QLD",
        "city_id": "576",
        "postal_code": "",
        "phone": "6172235589",
        "last_update": "2006-02-15 09:45:30"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "address_id": "5",
        "address": "1913 Hanoi Way",
        "address2": "",
        "district": "Nagasaki",
        "city_id": "463",
        "postal_code": "35200",
        "phone": "28303384290",
        "last_update": "2006-02-15 09:45:30"
      }
    }
  ]
}
*/