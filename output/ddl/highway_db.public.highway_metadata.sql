-- ====================================
-- Database: highway_db
-- Table: public.highway_metadata
-- Comment: 高速公路元数据表，存储高速公路主题数据的描述、关联表、问题及关键词等元信息
-- Generated: 2026-03-17 23:00:08
-- ====================================

CREATE TABLE IF NOT EXISTS public.highway_metadata (
    id INTEGER(32) NOT NULL DEFAULT nextval('highway_metadata_id_seq'::regclass),
    topic_code CHARACTER VARYING(50) NOT NULL,
    topic_name CHARACTER VARYING(255) NOT NULL,
    description TEXT,
    related_tables ARRAY,
    questions JSONB,
    keywords ARRAY,
    theme_tag CHARACTER VARYING(50),
    update_ts TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT highway_metadata_pkey PRIMARY KEY (id)
);

-- Column Comments
COMMENT ON COLUMN public.highway_metadata.id IS '元数据记录唯一标识ID';
COMMENT ON COLUMN public.highway_metadata.topic_code IS '主题编码（如日营收、车流量等）';
COMMENT ON COLUMN public.highway_metadata.topic_name IS '主题中文名称';
COMMENT ON COLUMN public.highway_metadata.description IS '主题业务描述与分析口径说明';
COMMENT ON COLUMN public.highway_metadata.related_tables IS '关联的源数据表名数组';
COMMENT ON COLUMN public.highway_metadata.questions IS '常见业务问题及对应SQL查询语句';
COMMENT ON COLUMN public.highway_metadata.keywords IS '主题相关关键词数组';
COMMENT ON COLUMN public.highway_metadata.theme_tag IS '主题分类标签（如交易分析、流量分析等）';
COMMENT ON COLUMN public.highway_metadata.update_ts IS '元数据最后更新时间';

-- Table Comment
COMMENT ON TABLE public.highway_metadata IS '高速公路元数据表，存储高速公路主题数据的描述、关联表、问题及关键词等元信息';