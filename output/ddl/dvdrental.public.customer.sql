-- ====================================
-- Database: dvdrental
-- Table: public.customer
-- Comment: 客户信息表，存储客户的个人资料、联系方式及账户状态
-- Generated: 2026-01-06 10:55:11
-- ====================================

CREATE TABLE IF NOT EXISTS public.customer (
    customer_id INTEGER(32) NOT NULL DEFAULT nextval('customer_customer_id_seq'::regclass),
    store_id SMALLINT(16) NOT NULL,
    first_name CHARACTER VARYING(45) NOT NULL,
    last_name CHARACTER VARYING(45) NOT NULL,
    email CHARACTER VARYING(50),
    address_id SMALLINT(16) NOT NULL,
    activebool BOOLEAN NOT NULL DEFAULT true,
    create_date DATE NOT NULL DEFAULT ('now'::text)::date,
    last_update TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    active INTEGER(32),
    CONSTRAINT customer_pkey PRIMARY KEY (customer_id),
    CONSTRAINT customer_address_id_fkey FOREIGN KEY (address_id) REFERENCES public.address (address_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- Column Comments
COMMENT ON COLUMN public.customer.customer_id IS '客户唯一标识ID';
COMMENT ON COLUMN public.customer.store_id IS '所属门店的ID';
COMMENT ON COLUMN public.customer.first_name IS '客户名字';
COMMENT ON COLUMN public.customer.last_name IS '客户姓氏';
COMMENT ON COLUMN public.customer.email IS '客户电子邮箱地址';
COMMENT ON COLUMN public.customer.address_id IS '关联地址的ID';
COMMENT ON COLUMN public.customer.activebool IS '是否激活账户（True-是，False-否）';
COMMENT ON COLUMN public.customer.create_date IS '客户创建日期';
COMMENT ON COLUMN public.customer.last_update IS '最后更新时间戳';
COMMENT ON COLUMN public.customer.active IS '活跃状态（1-活跃，0-非活跃）';

-- Indexes
CREATE INDEX idx_fk_address_id ON public.customer(address_id);
CREATE INDEX idx_fk_store_id ON public.customer(store_id);
CREATE INDEX idx_last_name ON public.customer(last_name);

-- Table Comment
COMMENT ON TABLE public.customer IS '客户信息表，存储客户的个人资料、联系方式及账户状态';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.customer",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "customer_id": "524",
        "store_id": "1",
        "first_name": "Jared",
        "last_name": "Ely",
        "email": "jared.ely@sakilacustomer.org",
        "address_id": "530",
        "activebool": "True",
        "create_date": "2006-02-14",
        "last_update": "2013-05-26 14:49:45.738000",
        "active": "1"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "customer_id": "1",
        "store_id": "1",
        "first_name": "Mary",
        "last_name": "Smith",
        "email": "mary.smith@sakilacustomer.org",
        "address_id": "5",
        "activebool": "True",
        "create_date": "2006-02-14",
        "last_update": "2013-05-26 14:49:45.738000",
        "active": "1"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "customer_id": "2",
        "store_id": "1",
        "first_name": "Patricia",
        "last_name": "Johnson",
        "email": "patricia.johnson@sakilacustomer.org",
        "address_id": "6",
        "activebool": "True",
        "create_date": "2006-02-14",
        "last_update": "2013-05-26 14:49:45.738000",
        "active": "1"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "customer_id": "3",
        "store_id": "1",
        "first_name": "Linda",
        "last_name": "Williams",
        "email": "linda.williams@sakilacustomer.org",
        "address_id": "7",
        "activebool": "True",
        "create_date": "2006-02-14",
        "last_update": "2013-05-26 14:49:45.738000",
        "active": "1"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "customer_id": "4",
        "store_id": "2",
        "first_name": "Barbara",
        "last_name": "Jones",
        "email": "barbara.jones@sakilacustomer.org",
        "address_id": "8",
        "activebool": "True",
        "create_date": "2006-02-14",
        "last_update": "2013-05-26 14:49:45.738000",
        "active": "1"
      }
    }
  ]
}
*/