# 表间关系发现报告
database: highway_db
生成方式: rel_llm
生成时间: 2026-03-18 12:47:16
关系总数: 21

## 统计摘要
- 外键直通: 0
- 推断关系: 21
- 复合键关系: 0
- 单列关系: 21
- 高置信度 (≥0.9): 17
- 中置信度 (0.8-0.9): 3

## 关系详情
### 1. public.bss_business_day_data.branch_no → public.bss_branch.branch_no
- **类型**: 单列
- **源列**: `branch_no`
- **目标列**: `branch_no`
- **关系类型**: inferred
- **置信度**: 0.850 (中)
- **评分明细**:
  - inclusion_rate: 0.806
  - jaccard_index: 0.566
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 2. public.bss_car_day_count.service_area_id → public.bss_branch.service_area_id
- **类型**: 单列
- **源列**: `service_area_id`
- **目标列**: `service_area_id`
- **关系类型**: inferred
- **置信度**: 0.942 (高)
- **评分明细**:
  - inclusion_rate: 0.915
  - jaccard_index: 0.887
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 3. public.bss_branch.company_id → public.bss_company.id
- **类型**: 单列
- **源列**: `company_id`
- **目标列**: `id`
- **关系类型**: inferred
- **置信度**: 0.942 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.889
  - name_similarity: 0.764
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 4. public.bss_branch.section_route_id → public.bss_section_route.id
- **类型**: 单列
- **源列**: `section_route_id`
- **目标列**: `id`
- **关系类型**: inferred
- **置信度**: 0.908 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.833
  - name_similarity: 0.623
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 5. public.bss_branch.service_area_id → public.bss_section_route_area_link.service_area_id
- **类型**: 单列
- **源列**: `service_area_id`
- **目标列**: `service_area_id`
- **关系类型**: inferred
- **置信度**: 0.926 (高)
- **评分明细**:
  - inclusion_rate: 0.888
  - jaccard_index: 0.878
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 6. public.bss_branch.section_route_id → public.bss_section_route_area_link.section_route_id
- **类型**: 单列
- **源列**: `section_route_id`
- **目标列**: `section_route_id`
- **关系类型**: inferred
- **置信度**: 0.924 (高)
- **评分明细**:
  - inclusion_rate: 0.889
  - jaccard_index: 0.851
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 7. public.bss_branch.service_area_id → public.bss_service_area.id
- **类型**: 单列
- **源列**: `service_area_id`
- **目标列**: `id`
- **关系类型**: inferred
- **置信度**: 0.903 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.742
  - name_similarity: 0.642
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 8. public.bss_branch.company_id → public.bss_service_area.company_id
- **类型**: 单列
- **源列**: `company_id`
- **目标列**: `company_id`
- **关系类型**: inferred
- **置信度**: 1.000 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 1.000
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 9. public.bss_branch.service_area_id → public.bss_service_area_mapper.service_area_id
- **类型**: 单列
- **源列**: `service_area_id`
- **目标列**: `service_area_id`
- **关系类型**: inferred
- **置信度**: 0.967 (高)
- **评分明细**:
  - inclusion_rate: 0.989
  - jaccard_index: 0.733
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 10. public.bss_business_day_data.service_no → public.bss_service_area.service_area_no
- **类型**: 单列
- **源列**: `service_no`
- **目标列**: `service_area_no`
- **关系类型**: inferred
- **置信度**: 0.667 (低)
- **评分明细**:
  - inclusion_rate: 0.535
  - jaccard_index: 0.460
  - name_similarity: 0.884
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 11. public.bss_business_day_data.service_no → public.bss_service_area_mapper.service_no
- **类型**: 单列
- **源列**: `service_no`
- **目标列**: `service_no`
- **关系类型**: inferred
- **置信度**: 0.942 (高)
- **评分明细**:
  - inclusion_rate: 0.977
  - jaccard_index: 0.548
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 12. public.bss_business_day_data.service_name → public.bss_service_area_mapper.service_name
- **类型**: 单列
- **源列**: `service_name`
- **目标列**: `service_name`
- **关系类型**: inferred
- **置信度**: 0.949 (高)
- **评分明细**:
  - inclusion_rate: 0.958
  - jaccard_index: 0.719
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 13. public.bss_car_day_count.service_area_id → public.bss_section_route_area_link.service_area_id
- **类型**: 单列
- **源列**: `service_area_id`
- **目标列**: `service_area_id`
- **关系类型**: inferred
- **置信度**: 0.895 (中)
- **评分明细**:
  - inclusion_rate: 0.840
  - jaccard_index: 0.832
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 14. public.bss_car_day_count.service_area_id → public.bss_service_area.id
- **类型**: 单列
- **源列**: `service_area_id`
- **目标列**: `id`
- **关系类型**: inferred
- **置信度**: 0.907 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.783
  - name_similarity: 0.642
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 15. public.bss_car_day_count.service_area_id → public.bss_service_area_mapper.service_area_id
- **类型**: 单列
- **源列**: `service_area_id`
- **目标列**: `service_area_id`
- **关系类型**: inferred
- **置信度**: 0.979 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.790
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 16. public.bss_car_day_count.service_area_id → public.bss_service_area.id
- **类型**: 单列
- **源列**: `service_area_id`
- **目标列**: `id`
- **关系类型**: inferred
- **置信度**: 0.907 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.783
  - name_similarity: 0.642
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 17. public.bss_service_area.company_id → public.bss_company.id
- **类型**: 单列
- **源列**: `company_id`
- **目标列**: `id`
- **关系类型**: inferred
- **置信度**: 0.942 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.889
  - name_similarity: 0.764
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 18. public.bss_section_route_area_link.section_route_id → public.bss_section_route.id
- **类型**: 单列
- **源列**: `section_route_id`
- **目标列**: `id`
- **关系类型**: inferred
- **置信度**: 0.902 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.778
  - name_similarity: 0.623
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 19. public.bss_section_route_area_link.service_area_id → public.bss_service_area.id
- **类型**: 单列
- **源列**: `service_area_id`
- **目标列**: `id`
- **关系类型**: inferred
- **置信度**: 0.895 (中)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.667
  - name_similarity: 0.642
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 20. public.bss_section_route_area_link.service_area_id → public.bss_service_area_mapper.service_area_id
- **类型**: 单列
- **源列**: `service_area_id`
- **目标列**: `service_area_id`
- **关系类型**: inferred
- **置信度**: 0.967 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.672
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 21. public.bss_service_area_mapper.service_area_id → public.bss_service_area.id
- **类型**: 单列
- **源列**: `service_area_id`
- **目标列**: `id`
- **关系类型**: inferred
- **置信度**: 0.928 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.992
  - name_similarity: 0.642
  - type_compatibility: 1.000
- **推断方法**: llm_assisted
