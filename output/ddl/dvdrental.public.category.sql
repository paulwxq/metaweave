-- ====================================
-- Database: dvdrental
-- Table: public.category
-- Comment: 电影分类表，存储影片分类名称及更新时间
-- Generated: 2026-01-06 10:55:03
-- ====================================

CREATE TABLE IF NOT EXISTS public.category (
    category_id INTEGER(32) NOT NULL DEFAULT nextval('category_category_id_seq'::regclass),
    name CHARACTER VARYING(25) NOT NULL,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT category_pkey PRIMARY KEY (category_id)
);

-- Column Comments
COMMENT ON COLUMN public.category.category_id IS '分类唯一标识ID';
COMMENT ON COLUMN public.category.name IS '分类名称';
COMMENT ON COLUMN public.category.last_update IS '最后更新时间';

-- Table Comment
COMMENT ON TABLE public.category IS '电影分类表，存储影片分类名称及更新时间';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.category",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "category_id": "1",
        "name": "Action",
        "last_update": "2006-02-15 09:46:27"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "category_id": "2",
        "name": "Animation",
        "last_update": "2006-02-15 09:46:27"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "category_id": "3",
        "name": "Children",
        "last_update": "2006-02-15 09:46:27"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "category_id": "4",
        "name": "Classics",
        "last_update": "2006-02-15 09:46:27"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "category_id": "5",
        "name": "Comedy",
        "last_update": "2006-02-15 09:46:27"
      }
    }
  ]
}
*/