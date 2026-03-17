-- ====================================
-- Database: dvdrental
-- Table: public.actor
-- Comment: 演员信息表，存储电影演员的姓名、唯一标识及最后更新时间
-- Generated: 2026-03-17 16:29:29
-- ====================================

CREATE TABLE IF NOT EXISTS public.actor (
    actor_id INTEGER(32) NOT NULL DEFAULT nextval('actor_actor_id_seq'::regclass),
    first_name CHARACTER VARYING(45) NOT NULL,
    last_name CHARACTER VARYING(45) NOT NULL,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT actor_pkey PRIMARY KEY (actor_id)
);

-- Column Comments
COMMENT ON COLUMN public.actor.actor_id IS '演员唯一标识ID';
COMMENT ON COLUMN public.actor.first_name IS '演员名字';
COMMENT ON COLUMN public.actor.last_name IS '演员姓氏';
COMMENT ON COLUMN public.actor.last_update IS '记录最后更新时间';

-- Indexes
CREATE INDEX idx_actor_last_name ON public.actor(last_name);

-- Table Comment
COMMENT ON TABLE public.actor IS '演员信息表，存储电影演员的姓名、唯一标识及最后更新时间';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.actor",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "actor_id": "1",
        "first_name": "Penelope",
        "last_name": "Guiness",
        "last_update": "2013-05-26 14:47:57.620000"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "actor_id": "2",
        "first_name": "Nick",
        "last_name": "Wahlberg",
        "last_update": "2013-05-26 14:47:57.620000"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "actor_id": "3",
        "first_name": "Ed",
        "last_name": "Chase",
        "last_update": "2013-05-26 14:47:57.620000"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "actor_id": "4",
        "first_name": "Jennifer",
        "last_name": "Davis",
        "last_update": "2013-05-26 14:47:57.620000"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "actor_id": "5",
        "first_name": "Johnny",
        "last_name": "Lollobrigida",
        "last_update": "2013-05-26 14:47:57.620000"
      }
    }
  ]
}
*/