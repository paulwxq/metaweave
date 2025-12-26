# 表间关系发现报告

生成时间: 2025-12-26 23:38:23
关系总数: 10

## 统计摘要

- 外键直通: 2
- 推断关系: 8
- 复合键关系: 3
- 单列关系: 7
- 高置信度 (≥0.9): 8
- 中置信度 (0.8-0.9): 0

## 关系详情

### 1. public.employee.dept_id → public.department.dept_id

- **类型**: 单列
- **源列**: `dept_id`
- **目标列**: `dept_id`
- **关系类型**: foreign_key

### 2. public.order_item.[order_date, order_id] → public.order_header.[order_date, order_id]

- **类型**: 复合键
- **源列**: `order_date, order_id`
- **目标列**: `order_date, order_id`
- **关系类型**: foreign_key

### 3. public.dim_store.company_id → public.dim_company.company_id

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

### 4. public.fact_store_sales_day.product_type_id → public.dim_product_type.product_type_id

- **类型**: 单列
- **源列**: `product_type_id`
- **目标列**: `product_type_id`
- **关系类型**: inferred
- **置信度**: 1.000 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 1.000
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 5. public.fact_store_sales_month.product_type_id → public.dim_product_type.product_type_id

- **类型**: 单列
- **源列**: `product_type_id`
- **目标列**: `product_type_id`
- **关系类型**: inferred
- **置信度**: 1.000 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 1.000
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 6. public.dim_store.region_id → public.dim_region.region_id

- **类型**: 单列
- **源列**: `region_id`
- **目标列**: `region_id`
- **关系类型**: inferred
- **置信度**: 1.000 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 1.000
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 7. public.fact_store_sales_day.store_id → public.dim_store.store_id

- **类型**: 单列
- **源列**: `store_id`
- **目标列**: `store_id`
- **关系类型**: inferred
- **置信度**: 1.000 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 1.000
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 8. public.fact_store_sales_month.store_id → public.dim_store.store_id

- **类型**: 单列
- **源列**: `store_id`
- **目标列**: `store_id`
- **关系类型**: inferred
- **置信度**: 1.000 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 1.000
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 9. public.maintenance_work_order.[equipment_id, config_version] → public.equipment_config.[equipment_id, config_version]

- **类型**: 复合键
- **源列**: `equipment_id, config_version`
- **目标列**: `equipment_id, config_version`
- **关系类型**: inferred
- **置信度**: 0.950 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.500
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 10. public.maintenance_work_order.[product_line_code, subsystem_code, fault_code] → public.fault_catalog.[product_line_code, subsystem_code, fault_code]

- **类型**: 复合键
- **源列**: `product_line_code, subsystem_code, fault_code`
- **目标列**: `product_line_code, subsystem_code, fault_code`
- **关系类型**: inferred
- **置信度**: 0.950 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.500
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted
