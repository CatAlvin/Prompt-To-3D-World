# Prompt-To-3D-World 开发需求与边界

> 文档状态：V1 基线草案  
> 产品定位：AI 驱动的可扩展 3D Scene Engine，而不是“由 AI 编写 Three.js 代码”的工具  
> 首版核心链路：Prompt → LLM → Scene JSON → Validation/Normalization → Scene Runtime → 3D World

## 1. 背景与产品愿景

用户输入一句自然语言描述，例如：

> A small cyberpunk Japanese alley at night with ramen shops and neon signs.

系统在数秒内生成一个可在网页中进入、观察并通过键盘和鼠标探索的 3D 场景。

首版不追求真实 3D 模型。建筑、道路、灯光、招牌等均可由 Box、Plane、Sphere、Cylinder、Text、PointLight 等基础元素组合完成，但必须在构图、光照、雾效、材质和配色上形成明确氛围。产品价值首先来自“描述即世界”的反馈速度与可探索性，而不是模型精度。

长期可演进为：

- AI 3D 场景生成器；
- AI Level Editor；
- AI Minecraft 式世界编辑体验；
- 接入纹理、模型资产、程序化生成、NPC、物理和多人协作的轻量游戏引擎。

## 2. 已知资源与前提

- 已有 MySQL，可用于用户、场景、版本、生成任务和审计信息的持久化；
- 已有 Kimi K3 API Token；Token 只能由服务端读取，不能进入前端包、Scene JSON、数据库明文字段或日志；
- Kimi 的 API 地址、模型名、超时、重试和采样参数均使用环境配置，不写死在业务代码中；
- 首版面向桌面端现代浏览器，优先 Chrome/Edge；移动端交互与性能适配不作为 V1 验收项；
- 首版默认单体仓库、前后端分离、模块化单体部署，不提前拆微服务。

## 3. 产品目标

### 3.1 V1 必须证明的事情

1. 用户输入一句场景描述后，可以稳定得到合法的 Scene JSON；
2. 合法 Scene JSON 可以被统一运行时渲染，而不依赖 LLM 生成任何前端代码；
3. 生成结果在视觉上具有基本空间层次、主题氛围和可辨识对象；
4. 用户可使用 WASD 与鼠标在场景中探索，并能随时退出指针锁定或重置位置；
5. 场景、Scene JSON 版本、生成状态和失败原因可追踪；
6. 替换 LLM Provider、增加对象类型或更换对象实现时，不需要重写完整生成链路。

### 3.2 V1 成功指标

- 合法场景生成成功率：在内部基准 Prompt 集上不低于 90%；
- 首次生成端到端耗时：P50 ≤ 8 秒、P95 ≤ 20 秒，超时后给出明确的重试入口；
- Scene JSON 经服务端验证后，前端渲染不得因单个未知或错误节点导致整页崩溃；
- 基准桌面设备上，默认场景 1080p 探索时目标帧率 ≥ 45 FPS；
- 用户可在一次会话内查看最近生成记录并重新打开场景；
- 同一 Scene JSON 在相同运行时版本和随机种子下应得到可重复的场景结构。

## 4. 用户与核心场景

### 4.1 V1 目标用户

- 想快速把文字概念变成空间原型的创作者；
- 游戏关卡、美术或产品概念验证人员；
- 希望体验 AI 生成可探索空间的普通用户。

### 4.2 核心用户路径

1. 用户进入生成页；
2. 输入 Prompt，也可使用示例 Prompt；
3. 点击“生成世界”；
4. 页面展示阶段化状态：理解描述、构建场景、验证场景、加载世界；
5. 生成完成后直接进入 3D 预览；
6. 用户点击进入探索，使用 WASD 移动、鼠标环视，Esc 退出；
7. 用户可查看场景信息、重新生成、复制 Scene JSON、恢复初始视角；
8. 生成记录被保存，可从历史列表再次打开。

## 5. V1 功能需求

### 5.1 Prompt 输入

- 支持中英文自然语言；
- 非空长度建议为 3～2,000 字符，前后端都进行限制；
- 支持取消尚未完成的生成任务；
- 防止重复点击创建大量相同任务；
- 提供示例 Prompt，但不把示例内容硬编码进生成逻辑；
- V1 允许“重新生成”，不要求多轮对话式局部修改。

### 5.2 生成任务

- 采用异步任务语义：创建任务后返回 `jobId`，前端通过轮询或 SSE 获取状态；
- 状态至少包括：`queued`、`generating`、`validating`、`succeeded`、`failed`、`cancelled`；
- 每次生成保留原始 Prompt、Provider、模型标识、耗时、Token 用量（若 Provider 返回）、场景版本和结构化失败码；
- LLM 返回非法 JSON 时允许有限修复，最多 2 次；不能无限重试；
- 失败必须区分：Provider 不可用、超时、限流、JSON 解析失败、Schema 校验失败、语义校验失败和内部错误；
- 日志中不保存 API Token，不默认保存完整 Provider 原始响应。

### 5.3 Scene JSON 编译管线

服务端必须按以下步骤处理，前端只接收经过验证与规范化的结果：

1. 输入清理与限制；
2. 拼装版本化系统提示词与 JSON Schema；
3. 调用 LLM Provider；
4. 提取结构化输出；
5. JSON Schema 校验；
6. 场景语义校验；
7. 有限自动修复；
8. 应用默认值和规范化；
9. 保存不可变场景版本；
10. 返回可渲染结果。

语义校验至少包含：

- ID 唯一；
- 数值均为有限数，位置、尺寸和灯光强度在允许范围内；
- 对象数量、灯光数量和 Scene JSON 大小不超过预算；
- 父子关系无环且父节点存在；
- 注册表中不存在的对象类型不能进入严格渲染路径；
- 资产 URL 只能来自后端允许的来源；
- 不允许脚本、HTML、着色器源码、事件处理器或任意可执行字段。

### 5.4 3D 场景运行时

- 使用统一 `SceneRuntime` 接收 Scene JSON；
- 使用对象注册表把 `kind + subtype` 映射到 React Three Fiber 组件；
- 运行时按环境、节点、灯光、相机和后处理分层；
- 单个节点渲染失败时显示降级占位或跳过，并报告可观察错误，不得拖垮整个场景；
- 支持基于 `seed` 的可重复程序化细节；
- 支持场景预算统计：节点数、灯光数、三角形估算、纹理内存和 draw calls；
- 未知扩展字段默认保留但不执行，未知核心字段由 Schema 拒绝。

### 5.5 V1 可渲染能力

V1 支持以下核心节点：

- `primitive/box`：建筑、箱体、墙面；
- `primitive/plane`：道路、地面、招牌底板；
- `primitive/sphere`：树冠、装饰体；
- `primitive/cylinder`：灯柱、管道、树干；
- `text`：店铺名与霓虹招牌；
- `light/ambient`、`light/directional`、`light/point`、`light/spot`；
- `group`：组合与父子层级。

V1 材质至少支持：

- 标准 PBR 材质基础参数；
- `color`、`roughness`、`metalness`、`opacity`；
- `emissive` 与 `emissiveIntensity`，用于霓虹效果；
- 受控的重复纹理引用接口可以预留，但 AI 纹理生成不进入 V1。

V1 环境至少支持：

- 天空/背景色；
- 环境光；
- 指数雾或线性雾；
- 色调映射与曝光；
- 可配置但有性能降级策略的 Bloom；
- 初始相机位置、朝向和移动参数。

### 5.6 探索控制

- WASD 移动，鼠标环视，Shift 加速，Esc 退出指针锁定；
- 提供屏幕内操作提示、进入探索按钮和重置视角按钮；
- 具有地面约束、重力感或等价的稳定移动体验；
- V1 只要求简单碰撞或阻挡体，不要求完整刚体物理；
- 尊重 `prefers-reduced-motion`，降低镜头与后处理动态效果；
- Canvas 获得焦点或指针锁定前，不劫持页面键盘操作。

### 5.7 历史与场景查看

- 保存场景标题、原始 Prompt、生成时间、缩略图状态、当前版本和生成状态；
- 场景版本不可变；重新生成会创建新版本或新场景，不能覆盖原始 JSON；
- 支持查看格式化 Scene JSON；
- V1 可先按匿名会话保存；正式多用户账号、分享权限和协作不进入 V1；
- 如果不做账号体系，必须明确数据保留周期和匿名会话归属方式。

## 6. Scene JSON V1 规范

### 6.1 设计原则

- **声明式**：描述“场景是什么”，不描述“如何执行代码”；
- **版本化**：每份文档必须包含 `schemaVersion`；
- **可验证**：正式 JSON Schema 是唯一结构事实来源；
- **可替换**：语义上的“建筑”可以先由 box 表示，未来替换为 procedural 或 glTF 资产；
- **可迁移**：版本升级通过明确的 migration 完成，禁止靠运行时猜测旧字段；
- **安全**：不携带任意 JS、HTML、Shader 或未经允许的远程资源；
- **有预算**：协议层直接包含并执行场景复杂度限制。

### 6.2 坐标与单位约定

- 使用 Three.js 右手坐标系；
- `Y` 轴向上；
- 1 个世界单位约等于 1 米；
- 旋转统一使用弧度和 Euler `[x, y, z]`，顺序固定为 `XYZ`；
- 颜色统一使用 `#RRGGBB` 或 `#RRGGBBAA`；
- 所有数组长度固定，所有数值必须为有限数；
- `position` 表示节点局部原点，primitive 几何默认以自身中心为原点。

### 6.3 推荐的 V1 示例

```json
{
  "schemaVersion": "1.0.0",
  "id": "scene_cyberpunk_alley_001",
  "title": "Neon Ramen Alley",
  "seed": 184726,
  "units": "meters",
  "environment": {
    "background": "#030712",
    "fog": {
      "type": "exponential",
      "color": "#090b18",
      "density": 0.035
    },
    "ambientLight": {
      "color": "#5b5bd6",
      "intensity": 0.25
    },
    "toneMapping": "acesFilmic",
    "exposure": 1.1,
    "postprocessing": {
      "bloom": {
        "enabled": true,
        "intensity": 0.7,
        "threshold": 0.75
      }
    }
  },
  "camera": {
    "mode": "firstPerson",
    "position": [0, 1.7, 7],
    "lookAt": [0, 1.5, 0],
    "fov": 65,
    "near": 0.1,
    "far": 150,
    "movement": {
      "speed": 3.5,
      "sprintMultiplier": 1.8,
      "eyeHeight": 1.7
    }
  },
  "nodes": [
    {
      "id": "road_001",
      "kind": "primitive",
      "subtype": "plane",
      "transform": {
        "position": [0, 0, -4],
        "rotation": [-1.570796, 0, 0],
        "scale": [5, 22, 1]
      },
      "material": {
        "type": "standard",
        "color": "#111827",
        "roughness": 0.72,
        "metalness": 0.15
      },
      "semantics": {
        "category": "road",
        "tags": ["wet", "alley"]
      },
      "collision": {
        "mode": "ground"
      }
    },
    {
      "id": "ramen_shop_001",
      "kind": "primitive",
      "subtype": "box",
      "transform": {
        "position": [2.8, 2.2, -5],
        "rotation": [0, 0, 0],
        "scale": [3.5, 4.4, 5]
      },
      "material": {
        "type": "standard",
        "color": "#27272a",
        "roughness": 0.82,
        "metalness": 0.05
      },
      "semantics": {
        "category": "building",
        "tags": ["ramen_shop", "japanese", "cyberpunk"]
      },
      "collision": {
        "mode": "solid"
      }
    },
    {
      "id": "ramen_sign_001",
      "kind": "text",
      "transform": {
        "position": [0.95, 2.5, -3.5],
        "rotation": [0, 1.570796, 0],
        "scale": [1, 1, 1]
      },
      "text": {
        "value": "RAMEN",
        "fontSize": 0.52,
        "align": "center"
      },
      "material": {
        "type": "standard",
        "color": "#ff2ca8",
        "emissive": "#ff2ca8",
        "emissiveIntensity": 3.2,
        "roughness": 0.35,
        "metalness": 0.05
      },
      "semantics": {
        "category": "sign",
        "tags": ["neon", "ramen"]
      }
    },
    {
      "id": "street_light_001",
      "kind": "light",
      "subtype": "point",
      "transform": {
        "position": [-1.7, 3.2, -2],
        "rotation": [0, 0, 0],
        "scale": [1, 1, 1]
      },
      "light": {
        "color": "#22d3ee",
        "intensity": 22,
        "range": 8,
        "decay": 2,
        "castShadow": false
      },
      "semantics": {
        "category": "street_light",
        "tags": ["cyan", "neon"]
      }
    }
  ],
  "metadata": {
    "generator": "prompt-compiler",
    "promptLanguage": "en"
  },
  "extensions": {}
}
```

### 6.4 协议边界

以下内容不得进入核心 Scene JSON：

- React、Three.js 或 React Three Fiber 组件代码；
- JavaScript 表达式、函数、事件回调或脚本；
- SQL、后端任务配置或 Provider 请求参数；
- 用户 Token、内部 Prompt、数据库主键和审计日志；
- 未经服务端白名单处理的远程 URL；
- 依赖渲染器隐式猜测的语义，例如仅写 `type: building` 却没有可渲染定义。

`semantics.category = building` 只表达语义；真正的 V1 渲染实现仍由 `kind = primitive` 与 `subtype = box` 决定。未来替换为 `kind = asset` 或 `kind = procedural` 时，上层场景、编辑器和分析能力仍可通过相同的 semantics 理解它。

### 6.5 扩展机制

- 核心字段由版本化 JSON Schema 管理；
- 非核心实验字段进入 `extensions`，键必须使用命名空间，例如 `com.example.weather`；
- 新增 `kind` 必须同时提供 Schema、后端语义校验、前端注册器、降级行为、预算计算和测试夹具；
- 核心协议只保存资产引用，不保存大型二进制、纹理 Base64 或模型数据；
- 每次协议破坏性变更必须升级主版本并提供数据迁移器。

## 7. 系统架构与模块边界

```text
Web UI
  ├─ Prompt & Job UI
  ├─ Scene Viewer
  └─ Scene Runtime / Object Registry
              │ validated Scene JSON only
              ▼
Backend API
  ├─ Generation Application Service
  ├─ Prompt Compiler
  ├─ Scene Validator / Normalizer / Migrator
  ├─ Scene & Version Repository
  └─ Provider Port
       ├─ Kimi Adapter
       └─ Future Providers
              │
              ├─ MySQL
              └─ LLM API
```

### 7.1 前端建议

- React + TypeScript + Vite；
- React Three Fiber + Drei；
- 状态分为服务器状态、生成任务状态、场景运行时状态，禁止混成单一全局 Store；
- Scene Runtime 与页面 UI 解耦，可独立接收 Scene JSON 渲染；
- `ObjectRegistry` 负责节点分发，避免页面中持续扩大的 `switch(type)`；
- Scene JSON 的 TypeScript 类型应由同一份 Schema 生成或校验，避免前后端各维护一份手写类型。

### 7.2 后端建议

- Python + FastAPI；
- Pydantic 负责请求、响应和领域 DTO 校验；
- SQLAlchemy + Alembic 管理 MySQL 与迁移；
- HTTP 路由只处理协议转换，生成流程位于 Application Service；
- Provider、持久化、任务执行器均通过接口隔离；
- V1 可使用进程内后台任务完成验证，但接口语义必须兼容后续迁移至 Redis/Celery、RQ 或其他队列；生产环境若要保证任务不因进程重启丢失，应尽早接入持久任务队列。

### 7.3 模块依赖规则

- 领域层不得导入 Kimi SDK、FastAPI、SQLAlchemy 或 Three.js；
- Kimi Adapter 只实现通用 `LLMProvider` 接口；
- Prompt 模板版本独立记录，不散落在路由和业务代码中；
- Renderer 不访问数据库，不调用 LLM；
- 数据库保存通过验证的 Scene JSON 和版本元数据，不负责解释渲染逻辑；
- 任何外部资产都通过 Asset Resolver，Renderer 不直接信任任意 URL；
- Scene JSON Schema 是前后端共享契约，必须有兼容性测试。

### 7.4 LLM Provider 接口

建议最小接口：

```text
generate_scene(request, schema, options) -> ProviderResult
```

`ProviderResult` 至少包含：

- 原始结构化内容或可提取内容；
- provider/model 标识；
- 请求耗时；
- Token/计费元数据（如可用）；
- finish reason；
- 可重试与不可重试错误分类。

业务层不得依赖 Kimi 特有字段。环境变量建议：

```text
LLM_PROVIDER=kimi
KIMI_API_KEY=...
KIMI_BASE_URL=...
KIMI_MODEL=...
LLM_TIMEOUT_SECONDS=...
```

真实变量名可在接入 Kimi 官方接口时确认；此文档只固定“配置化、服务端化、可替换”的边界，不假设某一版本 API 的具体地址。

## 8. API 边界草案

### 8.1 创建生成任务

`POST /api/v1/generations`

```json
{
  "prompt": "A small cyberpunk Japanese alley at night...",
  "preferences": {
    "quality": "balanced"
  }
}
```

返回 `202 Accepted`：

```json
{
  "jobId": "gen_...",
  "status": "queued"
}
```

### 8.2 获取任务状态

`GET /api/v1/generations/{jobId}`

成功后返回 `sceneId`、`sceneVersionId` 和经过验证的 Scene JSON 地址或内联结果。错误返回稳定的 `error.code`，不把 Provider 原始异常直接暴露给用户。

### 8.3 场景读取

- `GET /api/v1/scenes/{sceneId}`：场景元数据；
- `GET /api/v1/scenes/{sceneId}/versions/{versionId}`：不可变版本与 Scene JSON；
- `GET /api/v1/scenes?cursor=...`：游标分页历史记录；
- `POST /api/v1/generations/{jobId}/cancel`：尽力取消。

V1 不提供任意字段更新 Scene JSON 的通用 PATCH。后续编辑器应通过受约束命令或创建新版本，避免直接破坏场景不变量。

## 9. MySQL 数据边界

建议实体：

### `scenes`

- 场景稳定身份、标题、归属、当前版本引用、创建/更新时间、软删除状态；

### `scene_versions`

- 不可变版本；
- `scene_id`、版本号、`schema_version`、Scene JSON、原始 Prompt、seed、来源、创建时间；
- Scene JSON 使用 MySQL `JSON` 类型，同时保留常用检索字段为独立列；

### `generation_jobs`

- 状态机、请求参数摘要、Provider/模型、Prompt 模板版本、错误码、耗时、Token 元数据、重试次数、关联版本；

### `llm_call_audits`

- 只保留排障所需的安全元数据；原始请求/响应若未来确需保存，必须单独配置、脱敏并设保留期；

### `users` / `anonymous_sessions`

- V1 二选一或同时预留；不要为尚未决定的认证方案耦合具体 OAuth Provider。

关键约束：

- Token 不入库；
- 场景版本不可变；
- 生成任务状态转换需具备并发保护；
- 大型模型、纹理和缩略图存对象存储，MySQL 只存引用；
- 数据库迁移只能通过 Alembic 执行并纳入版本控制。

## 10. 非功能需求

### 10.1 可扩展性

- 新增 LLM：实现 Provider Adapter，无需修改生成用例；
- 新增节点：注册 Schema + Validator + Renderer + Fallback；
- 新增资产来源：实现 Asset Resolver；
- 新增编辑操作：创建新的不可变 Scene Version；
- 新增生成策略：通过 Prompt Compiler 策略或后处理器扩展；
- 未来拆服务时，Generation、Asset 和 Scene Version 边界已有明确所有权。

高扩展性不等于 V1 采用微服务、ECS 全套或插件市场。首版优先保持清晰接口、严格依赖方向、版本化协议和可靠测试。

### 10.2 性能预算

- V1 单场景建议节点数 20～120，硬上限 250；
- 动态灯光建议不超过 12，投射阴影灯光不超过 2；
- Scene JSON 请求体硬上限建议 256 KB；
- 默认设备像素比设上限，窗口失焦时降低或暂停渲染；
- 重复对象优先 InstancedMesh；
- Bloom、阴影、抗锯齿和高像素比必须具有质量档位；
- 开发环境提供性能统计，生产环境默认关闭调试面板。

### 10.3 可靠性

- 所有外部调用有超时；
- 只对明确可重试错误进行指数退避与抖动；
- 创建生成任务支持幂等键；
- Provider 失败不影响历史场景读取；
- JSON 校验和数据库写入失败不能产生“成功但不可打开”的半成品版本；
- 生成任务应支持进程异常后的超时回收或重试判定。

### 10.4 安全与隐私

- API Token 仅存在于服务端 secret/env；
- 日志与错误报告统一脱敏；
- Prompt 视为不可信输入，限制长度、频率和展示时转义；
- LLM 输出同样视为不可信输入，必须先验证再渲染；
- 禁止 Scene JSON 指定任意脚本、HTML、Shader 或跨域资源；
- API 需具备速率限制、请求体上限和成本保护；
- 若保存 Prompt，产品界面需提示保存行为并定义删除与保留策略；
- 依赖和容器不包含真实 `.env`，仓库只提交 `.env.example`。

### 10.5 可观察性

- 每次请求携带 `requestId`、每次生成有 `jobId`；
- 记录生成阶段耗时、Provider 延迟、验证失败类型、修复次数和前端加载耗时；
- 前端捕获 Renderer Error Boundary、WebGL 初始化失败和资源加载失败；
- 监控成功率、P50/P95 延迟、每次生成 Token/成本、Schema 失败率和前端 FPS 分布；
- 业务日志不得包含密钥和未经配置允许的完整 Prompt/响应。

### 10.6 可测试性

- JSON Schema 合同测试；
- Scene 语义校验单元测试；
- Provider Adapter 使用录制或伪造响应测试，不在常规测试中消耗真实 Token；
- 固定 Scene JSON 的渲染烟雾测试；
- Prompt 基准集测试：城市、自然、室内、极简、中文、英文和恶意输入；
- 关键用户路径 E2E：提交 → 状态 → 世界加载 → 进入探索 → 打开历史；
- Schema 迁移必须有旧版本夹具和可重复测试。

## 11. 明确不进入 V1 的范围

- AI 直接生成 Three.js/R3F 源代码；
- 真正的 AI 3D Mesh/模型生成；
- 自动 AI 纹理生成；
- 完整 glTF/FBX 资产市场与复杂资产检索；
- NPC、对话、行为树和寻路；
- 完整刚体物理、破坏系统、布料和流体；
- 多人联机、实时协作和版本合并；
- 无限世界、区块流式加载和 Minecraft 式体素编辑；
- VR/AR；
- 移动端完整适配；
- 对外插件市场；
- 完整可视化 Level Editor；
- 生产级计费、订阅和组织权限系统。

这些能力应有接口预留，但不得以“以后可能需要”为理由扩大 V1 的实现量。

## 12. 分期建议

### Phase 0：契约与骨架

- 建立前后端工程、配置管理与 MySQL 迁移；
- 定稿 Scene JSON 1.0 Schema；
- 用固定 JSON 渲染 cyberpunk alley；
- 完成对象注册表、错误边界和基础探索控制。

### Phase 1：Prompt 到世界闭环

- 接入 Kimi Provider Adapter；
- 实现 Prompt Compiler、验证、有限修复和规范化；
- 实现异步生成状态与失败展示；
- 保存 Scene、Scene Version 和 Generation Job；
- 完成基准 Prompt 集与成功率统计。

### Phase 2：体验与稳定性

- 历史记录、重新打开和重新生成；
- 缩略图、加载过渡、性能档位和降级策略；
- 简单碰撞、可访问性与 WebGL 失败提示；
- 监控、速率限制、成本保护和部署文档。

### Phase 3：受控扩展

- `asset` 与 `procedural` 节点；
- 纹理/模型 Asset Resolver；
- 局部编辑命令与新版本生成；
- 在真实需求出现后再评估持久任务队列、对象存储和服务拆分。

## 13. V1 验收标准

使用示例 Prompt：

> A small cyberpunk Japanese alley at night with ramen shops and neon signs.

必须同时满足：

1. 用户可以从网页提交 Prompt，无需手工编辑 JSON；
2. Kimi 调用只能从后端发起；
3. 返回内容通过 Scene JSON 1.0 结构与语义校验；
4. 场景至少包含道路、两侧体量、一个可读招牌、两类光源、夜间背景和雾效；
5. 视觉上可辨认出夜间 cyberpunk alley，而不是随机散落几何体；
6. 用户可进入第一人称探索，移动、环视、退出和重置均正常；
7. 单节点异常不会造成页面整体崩溃；
8. 刷新后可以从历史记录重新打开生成结果；
9. 生成失败时展示可理解提示，并保留可诊断错误码；
10. 仓库与前端构建产物中不存在真实 Kimi Token；
11. 自动化测试覆盖 Schema、语义校验、Provider Adapter 和关键生成路径；
12. 满足本文定义的对象、灯光和 Scene JSON 大小上限。

## 14. 决策记录

### 已固定

- 产品是 AI Scene Engine，不是 AI 代码生成器；
- Scene JSON 是系统核心协议；
- LLM 只生成声明式数据；
- React + TypeScript + React Three Fiber 负责前端运行时；
- Python + FastAPI 负责后端；
- MySQL 负责持久数据；
- Kimi 通过可替换 Provider Adapter 接入；
- V1 Primitive First；
- 模块化单体优先，暂不微服务化；
- 场景版本不可变。

### 开工前仍需由产品侧确认

这些问题不会改变总体架构，但会影响 V1 工作量：

1. V1 是匿名会话，还是必须有账号登录；
2. 生成记录默认保留多久，用户是否可删除；
3. 首发是否只供个人使用，还是直接面向公网；
4. 是否要求中文 UI 与英文 UI 同时上线；
5. 首版部署目标与预算，例如单机、Docker、云平台及并发量；
6. Kimi 当前可用的具体 API 地址、模型标识、结构化输出能力与限流配额；
7. 是否允许保存完整 Prompt 作为历史记录与调试数据。

## 15. 变更控制

- 本文是 V1 范围基线；新增需求先归类为 V1 必须、V1 可选或后续版本；
- 修改 Scene JSON 核心字段前，必须先更新 Schema、示例、迁移、验证器和前端合同测试；
- 任何需要执行 LLM 生成代码、允许任意远程资源或绕过服务端验证的方案，都视为突破安全与架构边界，需要单独评审；
- 每个迭代只引入能被验收、监控和回滚的能力。
