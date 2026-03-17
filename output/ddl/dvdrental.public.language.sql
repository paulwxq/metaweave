-- ====================================
-- Database: dvdrental
-- Table: public.language
-- Comment: 语言信息表，存储系统支持的语言名称及更新时间
-- Generated: 2026-03-17 08:19:53
-- ====================================

CREATE TABLE IF NOT EXISTS public.language (
    language_id INTEGER(32) NOT NULL DEFAULT nextval('language_language_id_seq'::regclass),
    name CHARACTER(20) NOT NULL,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT language_pkey PRIMARY KEY (language_id)
);

-- Column Comments
COMMENT ON COLUMN public.language.language_id IS '语言唯一标识ID';
COMMENT ON COLUMN public.language.name IS '语言名称';
COMMENT ON COLUMN public.language.last_update IS '最后更新时间';

-- Table Comment
COMMENT ON TABLE public.language IS '语言信息表，存储系统支持的语言名称及更新时间';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.language",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "language_id": "1",
        "name": "English             ",
        "last_update": "2006-02-15 10:02:19"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "language_id": "2",
        "name": "Italian             ",
        "last_update": "2006-02-15 10:02:19"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "language_id": "3",
        "name": "Japanese            ",
        "last_update": "2006-02-15 10:02:19"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "language_id": "4",
        "name": "Mandarin            ",
        "last_update": "2006-02-15 10:02:19"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "language_id": "5",
        "name": "French              ",
        "last_update": "2006-02-15 10:02:19"
      }
    }
  ]
}
*/