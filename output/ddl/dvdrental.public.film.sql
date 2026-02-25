-- ====================================
-- Database: dvdrental
-- Table: public.film
-- Comment: 电影信息表，存储影片的基本信息、租赁属性和播放详情
-- Generated: 2026-01-06 12:15:38
-- ====================================

CREATE TABLE IF NOT EXISTS public.film (
    film_id INTEGER(32) NOT NULL DEFAULT nextval('film_film_id_seq'::regclass),
    title CHARACTER VARYING(255) NOT NULL,
    description TEXT,
    release_year INTEGER(32),
    language_id SMALLINT(16) NOT NULL,
    rental_duration SMALLINT(16) NOT NULL DEFAULT 3,
    rental_rate NUMERIC(4,2) NOT NULL DEFAULT 4.99,
    length SMALLINT(16),
    replacement_cost NUMERIC(5,2) NOT NULL DEFAULT 19.99,
    rating USER-DEFINED DEFAULT 'G'::mpaa_rating,
    last_update TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    special_features ARRAY,
    fulltext TSVECTOR NOT NULL,
    CONSTRAINT film_pkey PRIMARY KEY (film_id),
    CONSTRAINT film_language_id_fkey FOREIGN KEY (language_id) REFERENCES public.language (language_id) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- Column Comments
COMMENT ON COLUMN public.film.film_id IS '电影唯一标识ID';
COMMENT ON COLUMN public.film.title IS '电影标题';
COMMENT ON COLUMN public.film.description IS '电影剧情描述';
COMMENT ON COLUMN public.film.release_year IS '电影发布年份';
COMMENT ON COLUMN public.film.language_id IS '语言种类ID';
COMMENT ON COLUMN public.film.rental_duration IS '租借时长（天）';
COMMENT ON COLUMN public.film.rental_rate IS '租借费用';
COMMENT ON COLUMN public.film.length IS '电影时长（分钟）';
COMMENT ON COLUMN public.film.replacement_cost IS '替换成本（丢失赔偿价）';
COMMENT ON COLUMN public.film.rating IS '电影分级（如PG、R等）';
COMMENT ON COLUMN public.film.last_update IS '记录最后更新时间';
COMMENT ON COLUMN public.film.special_features IS '特别收录内容（如花絮、预告片等）';
COMMENT ON COLUMN public.film.fulltext IS '全文检索向量字段';

-- Indexes
CREATE INDEX film_fulltext_idx ON public.film(fulltext);
CREATE INDEX idx_fk_language_id ON public.film(language_id);
CREATE INDEX idx_title ON public.film(title);

-- Table Comment
COMMENT ON TABLE public.film IS '电影信息表，存储影片的基本信息、租赁属性和播放详情';