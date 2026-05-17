# Navicat 使用说明

网站后端默认连接 MySQL 8.0，不再依赖本地 SQLite 文件 `backend\hotel.db`。

## 当前数据库

在 Navicat 中连接 MySQL 后，刷新即可看到数据库：

```text
hotel_room_system
```

该数据库包含系统用户、客房、客户、预约、入住、消费、结算、审计日志等核心表，并包含视图、索引、外键约束和触发器。

## 后端连接配置

网站后端会优先读取下面这个本地配置文件：

```text
D:\酒店客房管理系统\backend\db_config.json
```

本文件不会上传到 GitHub。公开仓库中只保留模板文件：

```text
backend\db_config.example.json
```

如果重新下载项目，需要复制模板并填写自己的 MySQL 密码：

```powershell
copy backend\db_config.example.json backend\db_config.json
```

配置示例：

```json
{
  "host": "127.0.0.1",
  "port": 3306,
  "user": "root",
  "password": "你的MySQL密码",
  "database": "hotel_room_system"
}
```

## 重新导入数据库

如果需要重新建库或恢复演示数据，可以在 Navicat 的 MySQL 查询窗口中执行：

```text
D:\酒店客房管理系统\backend\navicat_mysql_import.sql
```

执行后会重建 `hotel_room_system` 数据库，并重新创建表、外键、索引、视图、触发器和演示数据。

## VSCode 运行网站

在 VSCode 终端执行：

```powershell
python backend\app.py
```

看到下面类似信息就说明网站已经连接到 MySQL：

```text
酒店客房管理系统已启动: http://127.0.0.1:8000
MySQL数据库: 127.0.0.1:3306/hotel_room_system
```
