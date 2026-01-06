-- ====================================
-- Database: dvdrental
-- Table: public.film_category
-- Comment: 电影分类关联表，记录电影与所属分类的对应关系
-- Generated: 2026-01-06 10:55:14
-- ====================================

CREATE TABLE IF NOT EXISTS public.film_category (
    film_id SMALLINT(16) NOT NULL,
    category_id SMALLINT(16) NOT NULL,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT film_category_pkey PRIMARY KEY (film_id, category_id),
    CONSTRAINT film_category_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.category (category_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT film_category_film_id_fkey FOREIGN KEY (film_id) REFERENCES public.film (film_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- Column Comments
COMMENT ON COLUMN public.film_category.film_id IS '电影唯一标识ID';
COMMENT ON COLUMN public.film_category.category_id IS '影片分类唯一标识ID';
COMMENT ON COLUMN public.film_category.last_update IS '最后更新时间戳';

-- Table Comment
COMMENT ON TABLE public.film_category IS '电影分类关联表，记录电影与所属分类的对应关系';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.film_category",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "film_id": "1",
        "category_id": "6",
        "last_update": "2006-02-15 10:07:09"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "film_id": "2",
        "category_id": "11",
        "last_update": "2006-02-15 10:07:09"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "film_id": "3",
        "category_id": "6",
        "last_update": "2006-02-15 10:07:09"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "film_id": "4",
        "category_id": "11",
        "last_update": "2006-02-15 10:07:09"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "film_id": "5",
        "category_id": "8",
        "last_update": "2006-02-15 10:07:09"
      }
    }
  ]
}
*/