# public.staff（员工信息表，存储门店员工的基本资料、联系方式、账户凭证及头像等信息）
## 字段列表：
- staff_id (integer(32)) - 员工唯一标识ID [示例: 1, 2]
- first_name (character varying(45)) - 员工名字（名） [示例: Mike, Jon]
- last_name (character varying(45)) - 员工姓氏（姓） [示例: Hillyer, Stephens]
- address_id (smallint(16)) - 员工地址信息ID [示例: 3, 4]
- email (character varying(50)) - 员工工作邮箱地址 [示例: Mike.Hillyer@sakilastaff.com, Jon.Stephens@sakilastaff.com]
- store_id (smallint(16)) - 所属门店ID [示例: 1, 2]
- active (boolean) - 员工启用状态（true-在职，false-离职） [示例: True, True]
- username (character varying(16)) - 员工系统登录用户名 [示例: Mike, Jon]
- password (character varying(40)) - 员工密码（SHA1哈希值） [示例: 8cb2237d0679ca88db6464eac60da96345513964, 8cb2237d0679ca88db6464eac60da96345513964]
- last_update (timestamp without time zone) - 最后更新时间戳 [示例: 2006-05-16 16:13:11.793280, 2006-05-16 16:13:11.793280]
- picture (bytea) - 员工照片二进制数据 [示例: b'\x89PNG\r\nZ\n']
## 字段补充说明：
- 主键约束 staff_pkey: staff_id
- 外键约束 address_id 关联 public.address.address_id