-- ====================================
-- Database: dvdrental
-- Table: public.film_actor
-- Comment: 演员影片关联表，记录演员参演的电影及最后更新时间
-- Generated: 2026-01-06 12:15:36
-- ====================================

CREATE TABLE IF NOT EXISTS public.film_actor (
    actor_id SMALLINT(16) NOT NULL,
    film_id SMALLINT(16) NOT NULL,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT film_actor_pkey PRIMARY KEY (actor_id, film_id),
    CONSTRAINT film_actor_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.actor (actor_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT film_actor_film_id_fkey FOREIGN KEY (film_id) REFERENCES public.film (film_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- Column Comments
COMMENT ON COLUMN public.film_actor.actor_id IS '演员唯一标识ID';
COMMENT ON COLUMN public.film_actor.film_id IS '电影唯一标识ID';
COMMENT ON COLUMN public.film_actor.last_update IS '最后更新时间戳';

-- Indexes
CREATE INDEX idx_fk_film_id ON public.film_actor(film_id);

-- Table Comment
COMMENT ON TABLE public.film_actor IS '演员影片关联表，记录演员参演的电影及最后更新时间';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.film_actor",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "actor_id": "1",
        "film_id": "1",
        "last_update": "2006-02-15 10:05:03"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "actor_id": "1",
        "film_id": "23",
        "last_update": "2006-02-15 10:05:03"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "actor_id": "1",
        "film_id": "25",
        "last_update": "2006-02-15 10:05:03"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "actor_id": "1",
        "film_id": "106",
        "last_update": "2006-02-15 10:05:03"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "actor_id": "1",
        "film_id": "140",
        "last_update": "2006-02-15 10:05:03"
      }
    }
  ]
}
*/