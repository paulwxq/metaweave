-- ====================================
-- Database: dvdrental
-- Table: public.country
-- Comment: 国家信息表，存储全球国家名称及其更新时间
-- Generated: 2026-01-06 10:55:08
-- ====================================

CREATE TABLE IF NOT EXISTS public.country (
    country_id INTEGER(32) NOT NULL DEFAULT nextval('country_country_id_seq'::regclass),
    country CHARACTER VARYING(50) NOT NULL,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT country_pkey PRIMARY KEY (country_id)
);

-- Column Comments
COMMENT ON COLUMN public.country.country_id IS '国家唯一标识ID';
COMMENT ON COLUMN public.country.country IS '国家名称';
COMMENT ON COLUMN public.country.last_update IS '最后更新时间';

-- Table Comment
COMMENT ON TABLE public.country IS '国家信息表，存储全球国家名称及其更新时间';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.country",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "country_id": "1",
        "country": "Afghanistan",
        "last_update": "2006-02-15 09:44:00"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "country_id": "2",
        "country": "Algeria",
        "last_update": "2006-02-15 09:44:00"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "country_id": "3",
        "country": "American Samoa",
        "last_update": "2006-02-15 09:44:00"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "country_id": "4",
        "country": "Angola",
        "last_update": "2006-02-15 09:44:00"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "country_id": "5",
        "country": "Anguilla",
        "last_update": "2006-02-15 09:44:00"
      }
    }
  ]
}
*/