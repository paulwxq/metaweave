# public.department（部门信息表，存储公司各部门的编码、名称及所在地）
## 字段列表：
- dept_id (integer(32)) - 部门唯一标识ID [示例: 1, 2]
- dept_code (character varying(20)) - 部门编码（如HR、FIN、IT等） [示例: HR, FIN]
- dept_name (character varying(100)) - 部门全称 [示例: 人力资源部, 财务部]
- location (character varying(100)) - 所在城市（如北京、上海、广州） [示例: 北京, 北京]
## 字段补充说明：
- 主键约束 department_pkey: dept_id
- 唯一约束 department_dept_code_key: dept_code