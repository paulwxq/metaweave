# 表间关系发现报告
database: dvdrental
生成方式: rel_llm
生成时间: 2026-03-17 08:21:14
关系总数: 18

## 统计摘要
- 外键直通: 18
- 推断关系: 0
- 复合键关系: 0
- 单列关系: 18
- 高置信度 (≥0.9): 0
- 中置信度 (0.8-0.9): 0

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
