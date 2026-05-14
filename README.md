# Knowledge Blog

一个用于整理学习笔记、论文阅读和项目复盘的 Astro + MDX 个人博客骨架。

## 功能

- `Astro` + `MDX` 内容站点
- 三类内容集合：`notes`、`papers`、`projects`
- 首页仪表盘、分类列表、详情页、标签页
- `Pagefind` 构建后全文搜索
- `Decap CMS` 后台，用浏览器新增、编辑、删除内容，管理公开/未公开状态，并上传封面图与附件
- 示例内容与可替换首页视觉资产

## 本地运行

```bash
npm install
npm run dev
```

打开 Astro 输出的本地地址即可访问站点。

## 使用后台 CMS

后台入口是 `/admin/`。

本地编辑时建议开两个终端：

```bash
npm run dev
npm run cms
```

首次使用 Decap CMS 前，建议把当前目录初始化为 Git 仓库：

```bash
git init
git add .
git commit -m "Initial knowledge blog"
```

生产部署时，需要在 `public/admin/config.yml` 里把 `backend` 调整为你的 GitHub、GitLab 或 Netlify Git Gateway 配置。

## 内容目录

```txt
src/content/notes/       学习笔记
src/content/papers/      论文阅读
src/content/projects/    项目复盘
public/uploads/          图片、PDF、附件
```

在 CMS 中给条目选择“封面图”后，前台卡片和详情页会自动显示该图片。打开“未公开（不在前台显示）”开关后，条目会留在后台但不会进入前台列表、详情页和搜索索引。

## 构建

```bash
npm run build
npm run preview
```

`npm run build` 会先生成静态站点，再用 Pagefind 为 `dist/` 生成搜索索引。
