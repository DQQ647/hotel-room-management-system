# 酒店客房管理系统

一个用于数据库课程设计/答辩演示的酒店客房管理系统。项目采用 B/S 架构：

- 前端：原生 HTML、CSS、JavaScript
- 后端：Python 标准库 HTTP Server + PyMySQL
- 数据库：MySQL 8.0，支持 Navicat 导入

## 功能模块

- 用户登录与角色权限
- 客房信息管理
- 客户档案管理
- 客房预约管理
- 入住登记
- 额外消费登记
- 退房结算
- 经营报表
- 审计日志

## 项目结构

```text
hotel-room-management-system
├─ backend
│  ├─ app.py
│  ├─ schema.sql
│  ├─ navicat_mysql_import.sql
│  ├─ example_queries.sql
│  ├─ db_config.example.json
│  └─ NAVICAT使用说明.md
├─ frontend
│  ├─ index.html
│  └─ assets
│     ├─ app.js
│     ├─ styles.css
│     ├─ hotel-mark.svg
│     └─ hutao-official.jpg
├─ requirements.txt
├─ 酒店客房管理系统_项目文档.docx
└─ 酒店客房管理系统答辩PPT.pptx
```

## 数据库说明

核心表包括：

- `users`：系统用户
- `rooms`：客房信息
- `customers`：客户档案
- `reservations`：预约记录
- `stays`：入住记录
- `extra_charges`：额外消费
- `settlements`：退房结算
- `audit_logs`：审计日志

数据库脚本包含主键、外键、唯一约束、CHECK 约束、索引、触发器和视图。触发器用于防止维修房预约、同一房间日期冲突预约、重复入住等问题。

## 运行步骤

1. 克隆项目。

```bash
git clone https://github.com/DQQ647/hotel-room-management-system.git
cd hotel-room-management-system
```

2. 安装依赖。

```bash
pip install -r requirements.txt
```

3. 在 Navicat 或 MySQL 客户端中执行：

```text
backend/navicat_mysql_import.sql
```

执行后会创建数据库 `hotel_room_system` 和演示数据。

4. 复制数据库配置模板。

```powershell
copy backend\db_config.example.json backend\db_config.json
```

然后把 `backend/db_config.json` 中的 `password` 改成你本机 MySQL 密码。

5. 启动后端。

```bash
python backend/app.py
```

6. 浏览器打开：

```text
http://127.0.0.1:8000
```

## 演示账号

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 管理员 | admin | admin123 |
| 前台 | front | front123 |
| 客房部 | house | house123 |
| 财务 | finance | finance123 |

## 说明

`backend/db_config.json` 是本地数据库配置文件，已被 `.gitignore` 忽略，不会上传到 GitHub。

答辩 PPT 已包含功能演示视频页，可在 PowerPoint 中直接播放。单独录制的 `.mp4` 文件属于本地素材，已被 `.gitignore` 忽略，不随代码仓库上传。
