-- ====================================
-- Database: highway_db
-- Table: public.bss_section_route_area_link
-- Comment: 路段路由与服务区的关联关系表，记录路段路由所属的服务区ID
-- Generated: 2026-03-19 11:51:52
-- ====================================

CREATE TABLE IF NOT EXISTS public.bss_section_route_area_link (
    section_route_id CHARACTER VARYING(32) NOT NULL,
    service_area_id CHARACTER VARYING(32) NOT NULL,
    CONSTRAINT bss_section_route_area_link_pkey PRIMARY KEY (section_route_id, service_area_id)
);

-- Column Comments
COMMENT ON COLUMN public.bss_section_route_area_link.section_route_id IS '路线id';
COMMENT ON COLUMN public.bss_section_route_area_link.service_area_id IS '服务区id';

-- Indexes
CREATE INDEX fk_bss_section_area_link ON public.bss_section_route_area_link(service_area_id);

-- Table Comment
COMMENT ON TABLE public.bss_section_route_area_link IS '路段路由与服务区的关联关系表，记录路段路由所属的服务区ID';

/* SAMPLE_RECORDS
{
  "version": 1,
  "table": "public.bss_section_route_area_link",
  "records": [
    {
      "label": "Record 1",
      "data": {
        "section_route_id": "v8elrsfs5f7lt7jl8a6p87smfzesn3rz",
        "service_area_id": "08e01d7402abd1d6a4d9fdd5df855ef8"
      }
    },
    {
      "label": "Record 2",
      "data": {
        "section_route_id": "hxzi2iim238e3s1eajjt1enmh9o4h3wp",
        "service_area_id": "091662311d2c737029445442ff198c4c"
      }
    },
    {
      "label": "Record 3",
      "data": {
        "section_route_id": "59x441yb58kyopu38juna3avtvpztign",
        "service_area_id": "0b70f74d0516fa5316dd5cb848ffaae9"
      }
    },
    {
      "label": "Record 4",
      "data": {
        "section_route_id": "m4qmswd08ajhcw9q0uypvhajzrzx7rxr",
        "service_area_id": "104253161ec311f96c3367e42c97525c"
      }
    },
    {
      "label": "Record 5",
      "data": {
        "section_route_id": "tvyjygi5q745pxb697eiaj2sfie6m5be",
        "service_area_id": "15d16d34f3f9d35f3a77852a8a4f8916"
      }
    }
  ]
}
*/