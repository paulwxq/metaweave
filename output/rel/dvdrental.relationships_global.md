# 表间关系发现报告
database: dvdrental
生成方式: rel_llm
生成时间: 2026-01-06 10:58:59
关系总数: 26

## 统计摘要
- 外键直通: 18
- 推断关系: 8
- 复合键关系: 0
- 单列关系: 26
- 高置信度 (≥0.9): 6
- 中置信度 (0.8-0.9): 1

## 关系详情
### 1. public.address.city_id → public.city.city_id
- **类型**: 单列
- **源列**: `city_id`
- **目标列**: `city_id`
- **关系类型**: foreign_key

### 2. public.city.country_id → public.country.country_id
- **类型**: 单列
- **源列**: `country_id`
- **目标列**: `country_id`
- **关系类型**: foreign_key

### 3. public.customer.address_id → public.address.address_id
- **类型**: 单列
- **源列**: `address_id`
- **目标列**: `address_id`
- **关系类型**: foreign_key

### 4. public.film.language_id → public.language.language_id
- **类型**: 单列
- **源列**: `language_id`
- **目标列**: `language_id`
- **关系类型**: foreign_key

### 5. public.film_actor.actor_id → public.actor.actor_id
- **类型**: 单列
- **源列**: `actor_id`
- **目标列**: `actor_id`
- **关系类型**: foreign_key

### 6. public.film_actor.film_id → public.film.film_id
- **类型**: 单列
- **源列**: `film_id`
- **目标列**: `film_id`
- **关系类型**: foreign_key

### 7. public.film_category.category_id → public.category.category_id
- **类型**: 单列
- **源列**: `category_id`
- **目标列**: `category_id`
- **关系类型**: foreign_key

### 8. public.film_category.film_id → public.film.film_id
- **类型**: 单列
- **源列**: `film_id`
- **目标列**: `film_id`
- **关系类型**: foreign_key

### 9. public.inventory.film_id → public.film.film_id
- **类型**: 单列
- **源列**: `film_id`
- **目标列**: `film_id`
- **关系类型**: foreign_key

### 10. public.payment.customer_id → public.customer.customer_id
- **类型**: 单列
- **源列**: `customer_id`
- **目标列**: `customer_id`
- **关系类型**: foreign_key

### 11. public.payment.rental_id → public.rental.rental_id
- **类型**: 单列
- **源列**: `rental_id`
- **目标列**: `rental_id`
- **关系类型**: foreign_key

### 12. public.payment.staff_id → public.staff.staff_id
- **类型**: 单列
- **源列**: `staff_id`
- **目标列**: `staff_id`
- **关系类型**: foreign_key

### 13. public.rental.customer_id → public.customer.customer_id
- **类型**: 单列
- **源列**: `customer_id`
- **目标列**: `customer_id`
- **关系类型**: foreign_key

### 14. public.rental.inventory_id → public.inventory.inventory_id
- **类型**: 单列
- **源列**: `inventory_id`
- **目标列**: `inventory_id`
- **关系类型**: foreign_key

### 15. public.rental.staff_id → public.staff.staff_id
- **类型**: 单列
- **源列**: `staff_id`
- **目标列**: `staff_id`
- **关系类型**: foreign_key

### 16. public.staff.address_id → public.address.address_id
- **类型**: 单列
- **源列**: `address_id`
- **目标列**: `address_id`
- **关系类型**: foreign_key

### 17. public.store.address_id → public.address.address_id
- **类型**: 单列
- **源列**: `address_id`
- **目标列**: `address_id`
- **关系类型**: foreign_key

### 18. public.store.manager_staff_id → public.staff.staff_id
- **类型**: 单列
- **源列**: `manager_staff_id`
- **目标列**: `staff_id`
- **关系类型**: foreign_key

### 19. public.customer.store_id → public.inventory.store_id
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

### 20. public.customer.store_id → public.store.store_id
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

### 21. public.film_actor.film_id → public.film_category.film_id
- **类型**: 单列
- **源列**: `film_id`
- **目标列**: `film_id`
- **关系类型**: inferred
- **置信度**: 0.961 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 0.614
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 22. public.film_category.film_id → public.film_actor.film_id
- **类型**: 单列
- **源列**: `film_id`
- **目标列**: `film_id`
- **关系类型**: inferred
- **置信度**: 0.749 (低)
- **评分明细**:
  - inclusion_rate: 0.614
  - jaccard_index: 0.614
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 23. public.inventory.store_id → public.staff.store_id
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

### 24. public.inventory.store_id → public.store.store_id
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

### 25. public.payment.customer_id → public.rental.customer_id
- **类型**: 单列
- **源列**: `customer_id`
- **目标列**: `customer_id`
- **关系类型**: inferred
- **置信度**: 0.833 (中)
- **评分明细**:
  - inclusion_rate: 0.806
  - jaccard_index: 0.395
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted

### 26. public.payment.staff_id → public.rental.staff_id
- **类型**: 单列
- **源列**: `staff_id`
- **目标列**: `staff_id`
- **关系类型**: inferred
- **置信度**: 1.000 (高)
- **评分明细**:
  - inclusion_rate: 1.000
  - jaccard_index: 1.000
  - name_similarity: 1.000
  - type_compatibility: 1.000
- **推断方法**: llm_assisted
