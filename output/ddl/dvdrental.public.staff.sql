-- ====================================
-- Database: dvdrental
-- Table: public.staff
-- Comment: 员工信息表，存储门店员工的基本资料、联系方式及账户信息
-- Generated: 2026-01-06 12:15:49
-- ====================================

CREATE TABLE IF NOT EXISTS public.staff (
    staff_id INTEGER(32) NOT NULL DEFAULT nextval('staff_staff_id_seq'::regclass),
    first_name CHARACTER VARYING(45) NOT NULL,
    last_name CHARACTER VARYING(45) NOT NULL,
    address_id SMALLINT(16) NOT NULL,
    email CHARACTER VARYING(50),
    store_id SMALLINT(16) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    username CHARACTER VARYING(16) NOT NULL,
    password CHARACTER VARYING(40),
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    picture BYTEA,
    CONSTRAINT staff_pkey PRIMARY KEY (staff_id),
    CONSTRAINT staff_address_id_fkey FOREIGN KEY (address_id) REFERENCES public.address (address_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- Column Comments
COMMENT ON COLUMN public.staff.staff_id IS '员工唯一标识ID';
COMMENT ON COLUMN public.staff.first_name IS '员工名字';
COMMENT ON COLUMN public.staff.last_name IS '员工姓氏';
COMMENT ON COLUMN public.staff.address_id IS '地址关联ID';
COMMENT ON COLUMN public.staff.email IS '员工电子邮箱';
COMMENT ON COLUMN public.staff.store_id IS '所属门店ID';
COMMENT ON COLUMN public.staff.active IS '是否在职（True-在职，False-离职）';
COMMENT ON COLUMN public.staff.username IS '登录用户名';
COMMENT ON COLUMN public.staff.password IS '登录密码（加密存储）';
COMMENT ON COLUMN public.staff.last_update IS '最后更新时间';
COMMENT ON COLUMN public.staff.picture IS '员工照片（二进制数据）';

-- Table Comment
COMMENT ON TABLE public.staff IS '员工信息表，存储门店员工的基本资料、联系方式及账户信息';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.staff",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "staff_id": "1",
        "first_name": "Mike",
        "last_name": "Hillyer",
        "address_id": "3",
        "email": "Mike.Hillyer@sakilastaff.com",
        "store_id": "1",
        "active": "True",
        "username": "Mike",
        "password": "8cb2237d0679ca88db6464eac60da96345513964",
        "last_update": "2006-05-16 16:13:11.793280",
        "picture": "b'\\x89PNG\\r\\nZ\\n'"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "staff_id": "2",
        "first_name": "Jon",
        "last_name": "Stephens",
        "address_id": "4",
        "email": "Jon.Stephens@sakilastaff.com",
        "store_id": "2",
        "active": "True",
        "username": "Jon",
        "password": "8cb2237d0679ca88db6464eac60da96345513964",
        "last_update": "2006-05-16 16:13:11.793280",
        "picture": null
      }
    }
  ]
}
*/