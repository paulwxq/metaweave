-- ====================================
-- Database: dvdrental
-- Table: public.store
-- Comment: 门店信息表，存储门店及其管理员和地址信息
-- Generated: 2026-01-06 10:55:22
-- ====================================

CREATE TABLE IF NOT EXISTS public.store (
    store_id INTEGER(32) NOT NULL DEFAULT nextval('store_store_id_seq'::regclass),
    manager_staff_id SMALLINT(16) NOT NULL,
    address_id SMALLINT(16) NOT NULL,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT store_pkey PRIMARY KEY (store_id),
    CONSTRAINT store_address_id_fkey FOREIGN KEY (address_id) REFERENCES public.address (address_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT store_manager_staff_id_fkey FOREIGN KEY (manager_staff_id) REFERENCES public.staff (staff_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- Column Comments
COMMENT ON COLUMN public.store.store_id IS '门店唯一标识ID';
COMMENT ON COLUMN public.store.manager_staff_id IS '门店经理员工ID';
COMMENT ON COLUMN public.store.address_id IS '门店地址关联ID';
COMMENT ON COLUMN public.store.last_update IS '最后更新时间戳';

-- Table Comment
COMMENT ON TABLE public.store IS '门店信息表，存储门店及其管理员和地址信息';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.store",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "store_id": "1",
        "manager_staff_id": "1",
        "address_id": "1",
        "last_update": "2006-02-15 09:57:12"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "store_id": "2",
        "manager_staff_id": "2",
        "address_id": "2",
        "last_update": "2006-02-15 09:57:12"
      }
    }
  ]
}
*/