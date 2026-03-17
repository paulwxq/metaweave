# public.bss_section_route_area_link（路段路由与服务区的关联关系表）
## 字段列表：
- section_route_id (character varying(32)) - 路线id [示例: v8elrsfs5f7lt7jl8a6p87smfzesn3rz, hxzi2iim238e3s1eajjt1enmh9o4h3wp]
- service_area_id (character varying(32)) - 服务区id [示例: 08e01d7402abd1d6a4d9fdd5df855ef8, 091662311d2c737029445442ff198c4c]
## 字段补充说明：
- 主键约束 bss_section_route_area_link_pkey: section_route_id, service_area_id
- 索引 fk_bss_section_area_link (btree): service_area_id