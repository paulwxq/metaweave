-- ====================================
-- Database: dvdrental
-- Table: public.rental
-- Comment: 租赁记录表，存储影片租借的起止时间、租借人、库存项及经办员工信息
-- Generated: 2026-03-17 08:20:01
-- ====================================

CREATE TABLE IF NOT EXISTS public.rental (
    rental_id INTEGER(32) NOT NULL DEFAULT nextval('rental_rental_id_seq'::regclass),
    rental_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    inventory_id INTEGER(32) NOT NULL,
    customer_id SMALLINT(16) NOT NULL,
    return_date TIMESTAMP WITHOUT TIME ZONE,
    staff_id SMALLINT(16) NOT NULL,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT rental_pkey PRIMARY KEY (rental_id),
    CONSTRAINT rental_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customer (customer_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT rental_inventory_id_fkey FOREIGN KEY (inventory_id) REFERENCES public.inventory (inventory_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT rental_staff_id_key FOREIGN KEY (staff_id) REFERENCES public.staff (staff_id)
);

-- Column Comments
COMMENT ON COLUMN public.rental.rental_id IS '租赁记录唯一标识ID';
COMMENT ON COLUMN public.rental.rental_date IS '租赁发生时间戳';
COMMENT ON COLUMN public.rental.inventory_id IS '影片库存记录ID';
COMMENT ON COLUMN public.rental.customer_id IS '租赁客户唯一标识ID';
COMMENT ON COLUMN public.rental.return_date IS '影片归还时间戳（可为空）';
COMMENT ON COLUMN public.rental.staff_id IS '处理租赁业务的员工ID';
COMMENT ON COLUMN public.rental.last_update IS '记录最后更新时间戳';

-- Indexes
CREATE INDEX idx_fk_inventory_id ON public.rental(inventory_id);

-- Table Comment
COMMENT ON TABLE public.rental IS '租赁记录表，存储影片租借的起止时间、租借人、库存项及经办员工信息';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.rental",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "rental_id": "2",
        "rental_date": "2005-05-24 22:54:33",
        "inventory_id": "1525",
        "customer_id": "459",
        "return_date": "2005-05-28 19:40:33",
        "staff_id": "1",
        "last_update": "2006-02-16 02:30:53"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "rental_id": "3",
        "rental_date": "2005-05-24 23:03:39",
        "inventory_id": "1711",
        "customer_id": "408",
        "return_date": "2005-06-01 22:12:39",
        "staff_id": "1",
        "last_update": "2006-02-16 02:30:53"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "rental_id": "4",
        "rental_date": "2005-05-24 23:04:41",
        "inventory_id": "2452",
        "customer_id": "333",
        "return_date": "2005-06-03 01:43:41",
        "staff_id": "2",
        "last_update": "2006-02-16 02:30:53"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "rental_id": "5",
        "rental_date": "2005-05-24 23:05:21",
        "inventory_id": "2079",
        "customer_id": "222",
        "return_date": "2005-06-02 04:33:21",
        "staff_id": "1",
        "last_update": "2006-02-16 02:30:53"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "rental_id": "6",
        "rental_date": "2005-05-24 23:08:07",
        "inventory_id": "2792",
        "customer_id": "549",
        "return_date": "2005-05-27 01:32:07",
        "staff_id": "1",
        "last_update": "2006-02-16 02:30:53"
      }
    }
  ]
}
*/