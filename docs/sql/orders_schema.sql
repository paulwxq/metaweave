-- orders 数据库结构导出（建表 / 约束 / 索引 / 物化视图）
--
-- 来源：PostgreSQL 17.4 数据库 `orders`（schema: public）
-- 导出：pg_dump --schema-only --clean --if-exists --no-owner --no-privileges
--
-- 还原到另一台 PostgreSQL（建议 17+）的顺序：
--   1. createdb <target_db>
--   2. psql -d <target_db> -v ON_ERROR_STOP=1 -f orders_schema.sql
--   3. psql -d <target_db> -v ON_ERROR_STOP=1 -f orders_data.sql
-- 也可直接执行同目录 restore.sh。
--
-- 本文件包含：表、主键、外键、普通索引、物化视图定义及 MV 唯一索引。
-- 物化视图以 WITH NO DATA 创建，数据在导入表数据后由 orders_data.sql 末尾 REFRESH。
--

--
-- PostgreSQL database dump
--

\restrict 25p7KMD1dc6U2sBMldm7Id8eSeTHXSuehkgR9t4QexigjaaR7OZjlddm9LWI2Tu

-- Dumped from database version 17.4
-- Dumped by pg_dump version 17.11 (Debian 17.11-0+deb13u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE IF EXISTS ONLY public.screenings DROP CONSTRAINT IF EXISTS screenings_hall_id_fkey;
DROP INDEX IF EXISTS public.uq_mv_category_sales_category_id;
DROP INDEX IF EXISTS public.idx_screenings_start_time;
ALTER TABLE IF EXISTS ONLY public.screenings DROP CONSTRAINT IF EXISTS screenings_pkey;
ALTER TABLE IF EXISTS ONLY public.cinema_halls DROP CONSTRAINT IF EXISTS cinema_halls_pkey;
DROP TABLE IF EXISTS public.users;
DROP TABLE IF EXISTS public.screenings;
DROP MATERIALIZED VIEW IF EXISTS public.mv_category_sales;
DROP TABLE IF EXISTS public.products;
DROP TABLE IF EXISTS public.orders;
DROP TABLE IF EXISTS public.cinema_halls;
DROP TABLE IF EXISTS public.categories;
SET default_table_access_method = heap;

--
-- Name: categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.categories (
    category_id integer NOT NULL,
    category_name character varying(100) NOT NULL
);


--
-- Name: cinema_halls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cinema_halls (
    hall_id integer NOT NULL,
    hall_name character varying(50) NOT NULL,
    seat_count integer
);


--
-- Name: orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orders (
    order_id integer NOT NULL,
    order_date date,
    user_id integer,
    product_id integer,
    quantity integer,
    amount numeric(10,2)
);


--
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    product_id integer NOT NULL,
    product_name character varying(100) NOT NULL,
    category_id integer
);


--
-- Name: mv_category_sales; Type: MATERIALIZED VIEW; Schema: public; Owner: -
--

CREATE MATERIALIZED VIEW public.mv_category_sales AS
 SELECT p.category_id,
    sum(o.quantity) AS total_quantity,
    sum(o.amount) AS total_amount
   FROM (public.orders o
     JOIN public.products p ON ((p.product_id = o.product_id)))
  GROUP BY p.category_id
  WITH NO DATA;


--
-- Name: screenings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.screenings (
    screening_id integer NOT NULL,
    hall_id integer NOT NULL,
    start_time timestamp without time zone NOT NULL,
    movie_title character varying(100)
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    user_id integer NOT NULL,
    user_name character varying(50) NOT NULL
);


--
-- Name: cinema_halls cinema_halls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cinema_halls
    ADD CONSTRAINT cinema_halls_pkey PRIMARY KEY (hall_id);


--
-- Name: screenings screenings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.screenings
    ADD CONSTRAINT screenings_pkey PRIMARY KEY (screening_id);


--
-- Name: idx_screenings_start_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_screenings_start_time ON public.screenings USING btree (start_time);


--
-- Name: uq_mv_category_sales_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_mv_category_sales_category_id ON public.mv_category_sales USING btree (category_id);


--
-- Name: screenings screenings_hall_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.screenings
    ADD CONSTRAINT screenings_hall_id_fkey FOREIGN KEY (hall_id) REFERENCES public.cinema_halls(hall_id);


--
-- PostgreSQL database dump complete
--

\unrestrict 25p7KMD1dc6U2sBMldm7Id8eSeTHXSuehkgR9t4QexigjaaR7OZjlddm9LWI2Tu

