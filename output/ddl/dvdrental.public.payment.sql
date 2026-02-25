-- ====================================
-- Database: dvdrental
-- Table: public.payment
-- Comment: 支付记录表，存储客户租赁订单的付款金额及时间信息
-- Generated: 2026-01-06 12:15:45
-- ====================================

CREATE TABLE IF NOT EXISTS public.payment (
    payment_id INTEGER(32) NOT NULL DEFAULT nextval('payment_payment_id_seq'::regclass),
    customer_id SMALLINT(16) NOT NULL,
    staff_id SMALLINT(16) NOT NULL,
    rental_id INTEGER(32) NOT NULL,
    amount NUMERIC(5,2) NOT NULL,
    payment_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    CONSTRAINT payment_pkey PRIMARY KEY (payment_id),
    CONSTRAINT payment_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customer (customer_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT payment_rental_id_fkey FOREIGN KEY (rental_id) REFERENCES public.rental (rental_id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT payment_staff_id_fkey FOREIGN KEY (staff_id) REFERENCES public.staff (staff_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- Column Comments
COMMENT ON COLUMN public.payment.payment_id IS '支付记录唯一标识ID';
COMMENT ON COLUMN public.payment.customer_id IS '客户唯一标识ID';
COMMENT ON COLUMN public.payment.staff_id IS '员工唯一标识ID';
COMMENT ON COLUMN public.payment.rental_id IS '租赁订单唯一标识ID';
COMMENT ON COLUMN public.payment.amount IS '支付金额';
COMMENT ON COLUMN public.payment.payment_date IS '支付发生的时间';

-- Indexes
CREATE INDEX idx_fk_customer_id ON public.payment(customer_id);
CREATE INDEX idx_fk_rental_id ON public.payment(rental_id);
CREATE INDEX idx_fk_staff_id ON public.payment(staff_id);

-- Table Comment
COMMENT ON TABLE public.payment IS '支付记录表，存储客户租赁订单的付款金额及时间信息';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.payment",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "payment_id": "17503",
        "customer_id": "341",
        "staff_id": "2",
        "rental_id": "1520",
        "amount": "7.99",
        "payment_date": "2007-02-15 22:25:46.996577"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "payment_id": "17504",
        "customer_id": "341",
        "staff_id": "1",
        "rental_id": "1778",
        "amount": "1.99",
        "payment_date": "2007-02-16 17:23:14.996577"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "payment_id": "17505",
        "customer_id": "341",
        "staff_id": "1",
        "rental_id": "1849",
        "amount": "7.99",
        "payment_date": "2007-02-16 22:41:45.996577"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "payment_id": "17506",
        "customer_id": "341",
        "staff_id": "2",
        "rental_id": "2829",
        "amount": "2.99",
        "payment_date": "2007-02-19 19:39:56.996577"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "payment_id": "17507",
        "customer_id": "341",
        "staff_id": "2",
        "rental_id": "3130",
        "amount": "7.99",
        "payment_date": "2007-02-20 17:31:48.996577"
      }
    }
  ]
}
*/