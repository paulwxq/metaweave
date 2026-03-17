-- ====================================
-- Database: dvdrental
-- Table: public.city
-- Comment: 城市信息表，存储全球城市名称、所属国家及最后更新时间
-- Generated: 2026-03-17 16:29:29
-- ====================================

CREATE TABLE IF NOT EXISTS public.city (
    city_id INTEGER(32) NOT NULL DEFAULT nextval('city_city_id_seq'::regclass),
    city CHARACTER VARYING(50) NOT NULL,
    country_id SMALLINT(16) NOT NULL,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT city_pkey PRIMARY KEY (city_id),
    CONSTRAINT fk_city FOREIGN KEY (country_id) REFERENCES public.country (country_id)
);

-- Column Comments
COMMENT ON COLUMN public.city.city_id IS '城市唯一标识ID';
COMMENT ON COLUMN public.city.city IS '城市名称';
COMMENT ON COLUMN public.city.country_id IS '所属国家ID';
COMMENT ON COLUMN public.city.last_update IS '最后更新时间';

-- Indexes
CREATE INDEX idx_fk_country_id ON public.city(country_id);

-- Table Comment
COMMENT ON TABLE public.city IS '城市信息表，存储全球城市名称、所属国家及最后更新时间';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.city",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "city_id": "1",
        "city": "A Corua (La Corua)",
        "country_id": "87",
        "last_update": "2006-02-15 09:45:25"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "city_id": "2",
        "city": "Abha",
        "country_id": "82",
        "last_update": "2006-02-15 09:45:25"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "city_id": "3",
        "city": "Abu Dhabi",
        "country_id": "101",
        "last_update": "2006-02-15 09:45:25"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "city_id": "4",
        "city": "Acua",
        "country_id": "60",
        "last_update": "2006-02-15 09:45:25"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "city_id": "5",
        "city": "Adana",
        "country_id": "97",
        "last_update": "2006-02-15 09:45:25"
      }
    }
  ]
}
*/