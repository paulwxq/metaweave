# public.category（电影分类表，存储影片类别名称及最后更新时间）
## 字段列表：
- category_id (integer(32)) - 分类唯一标识ID [示例: 1, 2]
- name (character varying(25)) - 分类名称（如动作、动画、儿童等） [示例: Action, Animation]
- last_update (timestamp without time zone) - 最后更新时间戳 [示例: 2006-02-15 09:46:27, 2006-02-15 09:46:27]
## 字段补充说明：
- 主键约束 category_pkey: category_id