-- ====================================
-- Database: dvdrental
-- Table: public.inventory
-- Comment: 库存记录表，存储影片在各门店的库存数量及最后更新时间
-- Generated: 2026-03-17 16:29:35
-- ====================================

CREATE TABLE IF NOT EXISTS public.inventory (
    inventory_id INTEGER(32) NOT NULL DEFAULT nextval('inventory_inventory_id_seq'::regclass),
    film_id SMALLINT(16) NOT NULL,
    store_id SMALLINT(16) NOT NULL,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT inventory_pkey PRIMARY KEY (inventory_id),
    CONSTRAINT inventory_film_id_fkey FOREIGN KEY (film_id) REFERENCES public.film (film_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- Column Comments
COMMENT ON COLUMN public.inventory.inventory_id IS '库存记录唯一标识ID';
COMMENT ON COLUMN public.inventory.film_id IS '电影ID，关联films表';
COMMENT ON COLUMN public.inventory.store_id IS '门店ID，关联stores表';
COMMENT ON COLUMN public.inventory.last_update IS '最后更新时间戳';

-- Indexes
CREATE INDEX idx_store_id_film_id ON public.inventory(store_id, film_id);

-- Table Comment
COMMENT ON TABLE public.inventory IS '库存记录表，存储影片在各门店的库存数量及最后更新时间';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.inventory",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "inventory_id": "1",
        "film_id": "1",
        "store_id": "1",
        "last_update": "2006-02-15 10:09:17"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "inventory_id": "2",
        "film_id": "1",
        "store_id": "1",
        "last_update": "2006-02-15 10:09:17"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "inventory_id": "3",
        "film_id": "1",
        "store_id": "1",
        "last_update": "2006-02-15 10:09:17"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "inventory_id": "4",
        "film_id": "1",
        "store_id": "1",
        "last_update": "2006-02-15 10:09:17"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "inventory_id": "5",
        "film_id": "1",
        "store_id": "2",
        "last_update": "2006-02-15 10:09:17"
      }
    }
  ]
}
*/