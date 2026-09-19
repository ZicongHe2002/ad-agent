# Windows + Docker：从启动到完成一次评论测试

本教程在 **Windows 的 PowerShell** 中操作，适用于 Windows PowerShell 5.1 和 PowerShell 7。安装 Docker Desktop 后，Python、Node.js、数据库和后台任务都在容器内运行，不需要另装这些开发工具，也不需要 `make`。

完成后，你可以在浏览器里测试：发现模拟作品 → 生成评论 → 人工审核 → 发送到模拟平台，以及不逐条审批的自动模式。

**目前小红书、抖音的真实自动发送还未接通。** 本教程使用 `MOCK` 模拟平台和本地规则生成内容，不需要平台账号或模型密钥，不会向真实平台发评论。

按顺序完成下面步骤。每个命令执行结束、没有报错，再执行下一条；初次下载镜像和构建需要联网。

## 1. 准备 Docker Desktop

如果 Docker Desktop 已正常运行，可直接执行本节最后的检查命令。

1. 使用满足 [Docker Desktop 官方系统要求](https://docs.docker.com/desktop/setup/install/windows-install/)的 Windows 电脑。建议本项目运行时至少有 6 GB 可用内存。
2. 尚未安装 WSL 时，右键开始菜单，打开“终端（管理员）”或“Windows PowerShell（管理员）”，执行：

   ```powershell
   wsl --install
   ```

   按提示重启电脑。已有 WSL 时执行 `wsl --update` 更新即可；检查命令是 `wsl --version`。详见 [Microsoft 的 WSL 安装说明](https://learn.microsoft.com/en-us/windows/wsl/install)。

3. 从 [Docker Desktop Windows 下载和安装页](https://docs.docker.com/desktop/setup/install/windows-install/)选择与你的电脑处理器匹配的安装包，安装时使用 WSL 2 后端。
4. 安装后，从开始菜单打开 **Docker Desktop**，等待引擎启动。本项目需要 **Linux containers** 模式；若托盘菜单显示“Switch to Linux containers”，点击切换。
5. 重新打开一个普通权限的 **PowerShell** 窗口。后面的项目操作都在这个窗口完成，不要切到 CMD、Git Bash 或 Ubuntu 终端。

依次检查：

```powershell
docker version
docker compose version
docker info --format '{{.OSType}}'
```

预期：第一条同时显示 Client 和 Server，第二条显示 Compose 版本，第三条输出 `linux`。如果只有 Client 或提示无法连接 Docker，先解决引擎启动问题，再继续。

## 2. 把整个项目放到 Windows

把整个项目文件夹复制或解压到一个固定位置。本教程使用 `C:\ad-agent`；如果你放在 D 盘，就把后面的路径替换为自己的实际路径。

请确认复制的是整个项目，包含 `.env.example`、根目录及 `frontend` 里的 `.dockerignore` 等以点开头的文件；只复制本 README 无法运行。已有的 `.venv`、`node_modules` 和 `.next` 不需要搬到 Windows，构建时也会被忽略。

进入目录：

```powershell
Set-Location 'C:\ad-agent'
Get-ChildItem -Force
```

应当能看到以下文件或目录：

```text
ad-agent/
  README.windows.md
  docker-compose.yml
  Dockerfile
  .env.example
  .dockerignore
  backend/
  frontend/
    Dockerfile
    .dockerignore
    public/
  scripts/
  docs/
```

接下来所有 `docker compose` 命令都必须在这个项目根目录执行。

## 3. 第一次创建本地配置

下面整块命令一起复制到 PowerShell。它从模板创建 `.env`，自动生成应用密钥、加密密钥和对象存储密码，不会在屏幕上打印这些值；如果已经存在 `.env`，则保留原文件。

```powershell
if (Test-Path '.env') {
    Write-Host 'Existing .env kept. Check its local test settings before continuing.'
} else {
    function New-AdAgentLocalSecret {
        $taskBytes = New-Object byte[] 32
        $taskRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $taskRng.GetBytes($taskBytes) } finally { $taskRng.Dispose() }
        return [Convert]::ToBase64String($taskBytes).Replace('+', '-').Replace('/', '_')
    }
    $taskTemplatePath = (Resolve-Path '.env.example').Path
    $taskEnvText = [System.IO.File]::ReadAllText($taskTemplatePath)
    $taskStorageSecret = New-AdAgentLocalSecret
    $taskSecrets = @{
        APP_SECRET_KEY = (New-AdAgentLocalSecret)
        TOKEN_ENCRYPTION_KEY = (New-AdAgentLocalSecret)
        MINIO_ROOT_PASSWORD = $taskStorageSecret
        OBJECT_STORAGE_SECRET_KEY = $taskStorageSecret
    }
    foreach ($taskName in $taskSecrets.Keys) {
        $taskPattern = '(?m)^' + $taskName + '=[ \t]*\r?$'
        $taskEnvText = [regex]::Replace($taskEnvText, $taskPattern, ($taskName + '=' + $taskSecrets[$taskName]))
    }
    $taskEnvPath = Join-Path (Get-Location).Path '.env'
    $taskUtf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($taskEnvPath, $taskEnvText, $taskUtf8)
    Write-Host 'Created .env for local testing.'
}
```

新模板已经设置好模拟测试参数，无需手工修改。如果保留的是之前的 `.env`，用下面命令打开并核对这些值：

```powershell
notepad .env
```

```dotenv
APP_ENV=development
LLM_PROVIDER=mock
AUTO_PUBLISH_DEFAULT=false
COMMENT_MODE=REVIEW
DATABASE_URL=postgresql+asyncpg://app:app@postgres:5432/firstcomment
REDIS_URL=redis://redis:6379/0
API_PORT=8000
FRONTEND_PORT=3000
FRONTEND_ORIGIN=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

这里的 `postgres` 和 `redis` 是容器之间的地址，保持原样；浏览器访问应用时使用 `localhost`。示例数据库地址对应模板的数据库名、用户名和密码；如已有自定义数据库配置，应成套保持一致。

保留 `.env` 中生成的密钥，后续重启或更新不需要重新生成。网页已经保存过的 REVIEW/AUTO 设置会覆盖环境变量里的初始模式，后面会在 Settings 页面明确选择测试模式。

## 4. 构建、初始化、启动

先检查配置，不展开显示密钥：

```powershell
docker compose config --quiet
```

正常时没有输出。接着构建镜像：

```powershell
docker compose build
```

出现红色错误或 `failed` 就先停下，看本文最后的排错部分。构建完成后启动数据库和队列：

```powershell
docker compose up -d postgres redis
docker compose ps
```

等待 `postgres`、`redis` 显示 `healthy`，再依次初始化数据库结构和演示数据：

```powershell
docker compose run --rm backend-api alembic upgrade head
docker compose run --rm backend-api python /workspace/scripts/seed_demo.py
```

第一条应正常结束；第二条应输出包含 `email`、`creator_id`、`brand_account_id` 等字段的演示信息。它只创建演示账号、品牌、活动和创作者，**还没有创建作品**。

最后启动所有服务：

```powershell
docker compose up -d
docker compose ps
```

检查后台任务是否已经就绪：

```powershell
Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/system/readiness' | ConvertTo-Json -Depth 5
```

预期返回 `"ready": true`，且 `postgresql`、`redis`、`workers` 为 `true`。刚启动时可能暂时返回 HTTP 503，稍等后再次执行；持续不就绪时查看第 10 节。`/health` 返回正常只代表 API 活着，不能替代这里的完整就绪检查。

## 5. 登录后台

在运行 Docker 的同一台 Windows 电脑上，用 Edge 或 Chrome 打开 [http://localhost:3000](http://localhost:3000)。

首次创建的默认演示账号：

| 字段 | 值 |
|---|---|
| 邮箱 | `admin@example.com` |
| 密码 | `firstcomment-demo` |

登录后确认：

- **Accounts** 中有 `云绒官方`，平台为 `MOCK`。
- **Campaigns** 中有 `秋冬羊绒穿搭`，状态为 `ACTIVE`。
- **Creators** 中有 `羊绒穿搭示例`。
- **Settings** 中 Mock 通道可用；小红书和抖音显示尚未接通是当前正常状态。

如果这个数据库已有演示用户，重新执行 seed 不会修改原密码或重置已有设置。

## 6. 测试“先人工审核，再发送”

### 6.1 选择人工审核模式

打开 **Settings**：

1. 在 **Mode for new opportunities** 选择 **Testing · human review for every comment**。
2. 点击 **Save publishing policy**；如果已经是这个值且保存按钮不可点，无需再保存。

### 6.2 创建一篇模拟作品

前端暂时没有创建 Mock 作品按钮。在 PowerShell 中整块执行下面命令。它显式使用 UTF-8，避免 Windows PowerShell 把中文请求内容编码错误。

```powershell
$taskPostJson = @{
    external_creator_id = 'mock-creator-yangrong'
    title = '奶油白羊绒大衣'
    caption = '深棕围巾配直筒裤，秋冬层次很清楚'
    hashtags = @('羊绒', '秋冬穿搭')
} | ConvertTo-Json -Depth 5
$taskPostBytes = [System.Text.Encoding]::UTF8.GetBytes($taskPostJson)
$taskCreatedPost = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/mock/posts' -ContentType 'application/json; charset=utf-8' -Body $taskPostBytes
$taskCreatedPost | ConvertTo-Json -Depth 5
```

预期返回新作品，包含自动生成的 `external_post_id`。这个开发环境的 Mock 接口无需登录凭据；它创建的是模拟数据。

### 6.3 发现作品并审核

1. 打开 **Creators**，找到 `羊绒穿搭示例`，点击 **Poll now**。如果创作者已暂停，先点击 **Monitor**。
2. 打开 **Review**，稍等后点击 **Refresh queue**，选中新出现的任务。
3. 点击右侧 **Claim review** 领取任务。
4. 查看原作品和候选评论，点击 **Edit**，保留原有具体正文，在最前面加上：

   ```text
   【云绒官方账号｜AI辅助生成】
   ```

5. 在 **Edit reason** 填写：`补充账号身份与AI说明`。
6. 在 **Verified disclosure outcome** 选择 **Disclosure included in the final comment**。
7. 在 **Evidence and policy reference** 填写：`已核对最终正文包含云绒官方账号和AI辅助生成说明，仅用于Mock测试`。
8. 点击 **Submit edit & approve**，在确认框点击 **Submit edit for checks**。
9. 等待后台任务处理，打开 **Comments**，点击 **Refresh**，在 **Published comments** 查看新记录。

**通过标准：** 能看到刚才批准的完整正文、平台 `MOCK` 和发布记录。仅看到“审核通过”还不算发送完成。

人工审核模式下，自动披露开关不会替你给候选添加正文说明，所以不要跳过编辑和披露步骤。Mock 支持发送时，审核批准后由后台任务发送，**Manual publishing queue 为空是正常的**，无需在里面补填一个虚假的人工发送结果。

## 7. 测试“自动模式，无需逐条审批”

先完成上一节，再按以下顺序打开三个开关：

| 页面 | 操作 | 保存方式 |
|---|---|---|
| **Accounts** | 编辑 `云绒官方`，勾选 **Allow this account to participate in automatic publishing** | 点击 **Save account** |
| **Campaigns** | 在 `秋冬羊绒穿搭` 点击 **Allow automatic mode** | 立即保存，按钮变为 **Require human review**；已是这个文字时无需再点 |
| **Settings** | 模式选择 **Promotion · automatic publishing when all checks pass**，勾选 **Include identity and AI disclosure automatically** | 点击 **Save publishing policy** |

同时确认账号 `Authorization = VALID`、`Kill switch = OFF`，活动仍为 `ACTIVE`。若 Mock 授权尚未验证，可在 Accounts 点击 **Verify mock auth**。

现在创建一篇**新的、内容不同的作品**：

```powershell
$taskPostJson = @{
    external_creator_id = 'mock-creator-yangrong'
    title = '海军蓝羊绒开衫的周末搭配'
    caption = '浅灰百褶裙配酒红色短靴，袖口露出细条纹衬衫'
    hashtags = @('羊绒', '周末穿搭')
} | ConvertTo-Json -Depth 5
$taskPostBytes = [System.Text.Encoding]::UTF8.GetBytes($taskPostJson)
$taskCreatedPost = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/mock/posts' -ContentType 'application/json; charset=utf-8' -Body $taskPostBytes
$taskCreatedPost | ConvertTo-Json -Depth 5
```

再去 **Creators → 羊绒穿搭示例 → Poll now**，等待后刷新 **Comments**。

**通过标准：** 新评论在通过全部检查后直接出现在 Published comments，正文包含身份和 `AI辅助生成`，来源为 `AI_GENERATED_AUTO_APPROVED`，无需你批准一条新的审核任务。

如果没有发送，到 **Posts → Inspect → Timeline** 或 **Live** 查看原因。自动模式仍会跳过或阻断检查未通过的内容，不保证每篇作品必发。切换 AUTO 不会自动处理之前的待审核任务，也不会启用真实平台发送。

## 8. 验证停止与持久保存

- **设置保存：** 刷新 Settings 页面，刚才保存的模式和披露开关应仍在。
- **回到人工审核：** 把 Settings 改回 Testing 并保存。之后新作品应走审核；已经成功发送的评论仍保留。
- **账号停止开关：** 在 Accounts 点击 **Stop publishing** 并确认，检查 Kill switch 变为 `ON`。新的发送应被阻止；恢复时点 **Clear kill switch** 并确认。

不要连续用完全相同的正文测试：即使作品 ID 不同，也可能被重复检测拦截。演示活动默认每个创作者每天最多 3 条、活动每天最多 20 条；达到限额后停止发送是预期行为。

## 9. 日常停止、重新启动与更新

停止项目并保留数据库和评论记录：

```powershell
docker compose down
```

下次先打开 Docker Desktop，在项目目录启动即可：

```powershell
Set-Location 'C:\ad-agent'
docker compose up -d
```

重新启动无需再创建 `.env` 或 seed。不要给 `down` 加 `-v`；该选项会删除本项目的数据卷。

拿到更新后的代码时，保留自己的 `.env`，在项目目录逐条执行：

```powershell
docker compose down
docker compose build
docker compose run --rm backend-api alembic upgrade head
docker compose up -d
```

迁移成功后才继续启动，并再次检查 readiness。

## 10. 常见问题

### 找不到 docker，或者无法连接 Docker

确认 Docker Desktop 已安装并打开；安装后重开 PowerShell。执行 `docker version`，必须同时有 Client 和 Server。若提示 WSL 或虚拟化问题，按 Docker 界面提示与第 1 节官方说明处理。

### 找不到配置文件或 .env.example

执行 `Get-Location`，确认位于包含 `docker-compose.yml` 的项目根目录；执行 `Get-ChildItem -Force` 检查文件。若看到 `.env.txt`，说明保存成了文本文件，需要改回 `.env`。如果缺模板或 Dockerfile，请重新复制完整项目。

### 构建下载失败、卡在拉取镜像或 npm/pip

首次构建会下载 Docker 镜像和项目依赖。先检查 Windows 网络及 Docker Desktop 的网络/代理设置，然后重试 `docker compose build`。这种错误发生在构建阶段，不是平台评论接口的问题。

### 内存不足或容器退出

关闭占用较多内存的应用，检查 WSL/Docker 的资源限制是否过低，保证项目有足够可用内存。然后查看服务状态和日志；不要通过删除数据库来处理构建或内存错误。

### 端口已经被占用

先查看占用端口的程序。例如：

```powershell
Get-NetTCPConnection -State Listen -LocalPort 3000,8000,5432,6379,9000,9001,9090 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

可以正常关闭占用端口的已知应用，或者修改 `.env` 中的宿主机端口。例如数据库端口冲突时，添加/修改 `POSTGRES_PORT=55432`；Redis 冲突时用 `REDIS_PORT=56379`。**容器内的 DATABASE_URL / REDIS_URL 保持原来的主机名和端口。**

对象存储或监控端口冲突时，可以设置 `MINIO_PORT=19000`、`MINIO_CONSOLE_PORT=19001`、`PROMETHEUS_PORT=19090`，然后重新执行 `docker compose up -d`；容器内的 `OBJECT_STORAGE_ENDPOINT` 保持不变。

如果要同时把网页改为 3001、API 改为 8001，下面四项需要一起修改：

```dotenv
FRONTEND_PORT=3001
API_PORT=8001
FRONTEND_ORIGIN=http://localhost:3001
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1
```

然后执行 `docker compose up -d --build`。前端 API 地址在构建时写入，只有 `restart` 不足以更新。浏览器改访问 `http://localhost:3001`，本文 readiness 和模拟作品请求里的 API 地址也改为 `http://localhost:8001`。

### 网页打开了，但登录失败

先检查 readiness，再核对 seed 是否成功。全新数据库的默认邮箱和密码见第 5 节；已有用户不会被 seed 重置。如果修改过 API 端口或前端 API 地址，按上一条重建前端。

### 没有审核任务，或审核后没有评论

先确认第 6.2 节确实创建了作品；seed 本身不会创建作品。再检查创作者已启用监控、活动为 ACTIVE、Settings 模式符合当前测试步骤。点击 Poll now 后，到 Posts 看是否发现了新作品，再查看 Timeline。

待披露候选需要明确填写披露结果和证据，不能保留 **Keep existing verified decision** 直接批准；默认品牌身份也不能选 **Not required**。AUTO 中被跳过的作品不会再创建审核任务，应查看 Timeline 原因。

### readiness 一直是 false / HTTP 503

在项目根目录依次执行：

```powershell
docker compose ps
docker compose logs --tail 100 backend-api postgres redis
docker compose logs --tail 100 worker-critical worker-default worker-low scheduler outbox-relay
```

若日志提示数据库表不存在，回到第 4 节执行迁移；若是连接拒绝，核对容器地址及数据库是否 healthy。需要协助时，提供报错文字、失败的步骤和上述相关日志，不要发送 `.env` 或密钥。

## 本教程的验证范围

命令已按当前 Compose 服务、后端接口、初始化脚本和前端按钮核对；PowerShell 请求使用显式 UTF-8 编码，构建忽略文件会排除其他系统的本地依赖和缓存。本轮没有可用的 Windows/Docker 运行环境，因此没有声称已经在 Windows 上完成实际启动验收。

项目已有后端自动化测试与前端构建结果见[本轮实现与验证记录](docs/implementation-update-2026-09-19.md)。真实小红书、抖音发送的进度和限制见[浏览器评论发送研究](docs/browser-publishing-research-2026-09-19.md)。
