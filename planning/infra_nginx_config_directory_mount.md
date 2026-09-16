# 部署：nginx 配置改为目录挂载

- 编号：P-03
- 领域：部署与基础设施
- 优先级：中
- 状态：待实施
- 立项：2026-09-16
- 影响范围：`docker-compose.yml`、`nginx.conf`（将移动位置）、部署脚本；不涉及应用代码
- 预估工作量：半天（含验证）
- 依赖：无

## 1. 背景与证据

`nginx.conf` 目前以**单个文件**的方式绑定挂载进容器：

```yaml
volumes:
  - ./nginx.conf:/etc/nginx/nginx.conf:ro
```

Docker 的单文件绑定挂载绑定的是 inode 而不是路径。部署时 `git pull` 不会原地改写文件，而是写新文件再重命名覆盖，这会产生新的 inode，容器里的挂载点仍然指向旧 inode，于是**容器永远看不到更新后的配置**，`nginx -s reload` 也无效，只有重建或重启容器才会重新解析。

2026-09-16 实测到的现象（修复 `/media/` 缺 Host 头的那次部署）：

| 位置 | inode | 大小 | 说明 |
|---|---|---|---|
| 宿主机 `/home/agi7/testhub_platform/nginx.conf` | 31492139 | 2322 字节 | 已含修复，部署成功 |
| nginx 容器内 `/etc/nginx/nginx.conf` | 31472748 | 2063 字节 | 仍是旧版 |

结果是配置文件看起来完全正确、行为却是旧的，排查成本很高。这类问题会在每一次修改 nginx 配置时重现。

同样的隐患还存在于其他单文件挂载：`config.yaml` 同时挂给 backend 与 worker，`hermes_api_key` 挂给两者。目前没有暴露，只是因为部署恰好会重启这两个容器；一旦部署流程调整为只重启部分容器，就会出现同样的静默失效。

## 2. 目标

把 nginx 配置改为**目录挂载**，使配置更新后 `nginx -s reload` 即可生效，无需重启容器、无连接中断，并消除“文件已更新但容器看不到”的整类问题。

## 3. 目标结构

nginx 官方镜像的主配置已经包含 `include /etc/nginx/conf.d/*.conf;`，且已在 http 块里设置了 `include mime.types`、`default_type`、`sendfile on`、`keepalive_timeout`。因此只需把我们的 `server {}` 段放进 `conf.d`，不再自带 `http {}` 与 `events {}`。

```
deploy/nginx/testhub.conf      # 只含 server {} 段
```

```yaml
nginx:
  image: nginx:alpine
  volumes:
    - ./deploy/nginx/:/etc/nginx/conf.d/:ro
```

注意目录挂载会覆盖镜像自带的 `conf.d/default.conf`，这正是期望行为；但要确保我们的文件以 `.conf` 结尾，否则不会被 include。

## 4. 实施步骤

1. 新建 `deploy/nginx/testhub.conf`，内容为现有 `nginx.conf` 中的 `server {}` 段，去掉外层 `http {}` 与 `events {}`、`worker_processes`。
2. 把原本位于 http 块的 `client_max_body_size 160m;` 下沉到 `server` 级（`/api/` 段里已另有一份，可保留）。`sendfile`、`mime.types`、`default_type` 由镜像默认主配置提供，不需要再写。
3. 修改 `docker-compose.yml` 的 nginx 服务，把单文件挂载改为目录挂载。
4. 删除仓库根目录的 `nginx.conf`（或保留一次过渡期并在其中加注释说明已废弃）。
5. 检查是否有其他脚本、文档、部署流程写死了 `nginx.conf` 在仓库根目录这个路径，一并调整。
6. 顺带评估把 `config.yaml` 也改为目录挂载（例如 `./deploy/config/:/app/config/:ro` 并调整读取路径），消除 backend 与 worker 的同类隐患。这一项可以作为独立的第二阶段，避免一次改动面过大。

## 5. 风险与注意事项

- **切换那一次必须重建容器**。挂载定义变了，`docker restart` 不够，需要 `docker compose up -d nginx`。之后才享受到 reload 即生效的好处。
- **http 级指令的落位要逐条确认**。现有配置里 `client_max_body_size 160m` 与 `sendfile on` 在 http 块，拆分后要确认仍然生效，尤其是 160m 的上传上限，漏掉会导致大文件上传失败。
- **`/v1/` 段的转发目标本身就是坏的，改动时一并确认**。现配置是 `proxy_pass http://localhost:8080/v1/;`，但 `localhost` 指的是 nginx 容器自身，容器内无 8080 监听，实测连接被拒绝；宿主机上才有 8080。这一段目前应当是不可用的，需要确认它是否还有用途，若有则改为可达地址（例如 `host.docker.internal:8080` 并补 `extra_hosts`）。
- 目录挂载后，目录下任何 `.conf` 文件都会被加载，要避免误放备份文件（例如 `testhub.conf.bak` 不会被加载，但 `testhub.conf.old.conf` 会）。

## 6. 验证清单

在开发环境完成并验证后再走部署流程，不直接改动正式环境。

1. `docker compose up -d nginx` 后 `docker exec <实例>_testhub_nginx nginx -t` 通过。
2. 逐条复验路由：`/` 返回 200，`/api/` 返回 401，`/admin/` 返回 302，`/static/` 与 `/media/` 返回 200（用一张真实的 AI 测试截图 URL）。
3. 验证 reload 生效链路：改动 `deploy/nginx/testhub.conf`（例如加一个注释），`nginx -s reload`，确认容器内 `cat /etc/nginx/conf.d/testhub.conf` 能看到改动。这是本计划的核心验收点。
4. 上传一个超过 100 MB 的文件，确认 160m 上限仍然生效。

## 7. 回滚

保留原 `nginx.conf` 与原 compose 片段，回滚时恢复这两处并 `docker compose up -d nginx` 即可。切换前后各做一次上述验证清单，便于定位问题出在哪一步。

## 8. 与短期措施的关系

在本计划实施之前，部署脚本里应当保留 `docker restart <实例>_testhub_nginx` 作为止血措施，确保 nginx 配置改动能够生效。本计划完成后该重启可以去掉，改为 `nginx -s reload`。
