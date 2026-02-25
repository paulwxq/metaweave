# public.language（语言信息表，存储系统支持的语言名称及更新时间）
## 字段列表：
- language_id (integer(32)) - 语言唯一标识ID [示例: 1, 2]
- name (character(20)) - 语言名称 [示例: English             , Italian             ]
- last_update (timestamp without time zone) - 最后更新时间 [示例: 2006-02-15 10:02:19, 2006-02-15 10:02:19]
## 字段补充说明：
- 主键约束 language_pkey: language_id