# 发票处理系统

这是一个用于处理电子发票的系统，支持PDF和OFD格式的发票文件处理。

## 功能特点

- 支持PDF和OFD格式的发票处理
- 提取发票信息（发票号码、金额等）
- 根据发票信息重命名文件
- Web界面上传和管理发票
- 发票汇总金额计算

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

1. 直接处理文件：
```bash
python main.py /path/to/your/invoice.pdf
```

2. 启动Web界面：
```bash
python web_app.py
```

## Web界面功能

- 上传发票文件
- 查看和下载处理后的发票
- 配置系统参数
- 管理员功能

## 配置选项

可以通过`config.json`文件配置系统参数：
- rename_with_amount: 是否使用金额重命名文件
- ui_port: Web界面端口
- log_level: 日志级别
- temp_dir: 临时文件目录
- supported_formats: 支持的文件格式

## Vercel部署

本项目已配置为可以通过GitHub Actions自动部署到Vercel。每次向主分支推送代码时，都会自动触发部署流程。

### 部署步骤

1. 在Vercel上创建一个新项目
2. 将项目关联到您的GitHub仓库
3. 在GitHub仓库的Settings -> Secrets -> Actions中添加以下secrets:
   - `VERCEL_TOKEN`: 您的Vercel API令牌
   - `VERCEL_ORG_ID`: 您的Vercel组织ID
   - `VERCEL_PROJECT_ID`: 您的Vercel项目ID

### 获取Vercel认证信息

1. 安装Vercel CLI: `npm i -g vercel`
2. 运行`vercel login`并按照提示操作
3. 在项目目录下运行`vercel link`关联您的Vercel项目
4. 项目关联后，将在项目目录中生成`.vercel`目录，其中包含`project.json`文件
5. 从该文件中获取`orgId`和`projectId`
6. 获取Vercel令牌：在Vercel网站上，进入Settings -> Tokens，创建并复制一个新令牌

### 环境变量

如需配置环境变量，可以在Vercel项目设置中添加以下环境变量：
- RENAME_WITH_AMOUNT: 是否使用金额重命名文件（true/false）
- UI_PORT: Web界面端口（此设置在Vercel环境中不生效）
- LOG_LEVEL: 日志级别（INFO/DEBUG/WARNING/ERROR） 